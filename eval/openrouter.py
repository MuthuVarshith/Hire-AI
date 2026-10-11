"""OpenRouter's OpenAI-compatible chat completions API over plain HTTP (urllib), for the answer judge.

No SDK: one POST to {base}/chat/completions per attempt. The caller passes `before_request`, which
runs before every HTTP request (retries included) and may raise to stop it being sent; eval/judge.py
uses it to count requests against --max-requests. Retries mirror llm.py: a 5xx or network error is
retried at most MAX_SERVER_ERROR_RETRIES times, a short rate limit (429) up to len(RETRY_DELAYS)
times with backoff, and a daily limit (a 429 that names a per-day limit or asks to wait longer than
the backoff) not at all.

Free model IDs and their limits change often; check https://openrouter.ai/models?max_price=0 and
https://openrouter.ai/docs/api-reference/limits before a run. Only synthetic resumes are sent.
"""
import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 120.0
RETRY_DELAYS = (2.0, 5.0, 10.0)   # seconds of backoff before each retry, as in llm.py
MAX_SERVER_ERROR_RETRIES = 1      # each retry is another request against the free daily limit
APP_TITLE = "Hire AI answer evaluation"


class OpenRouterError(RuntimeError):
    """An HTTP or API error from OpenRouter. `code` is the HTTP status (or the error object's code);
    None for a network failure."""

    def __init__(self, code: int | None, message: str, retry_after: float | None = None) -> None:
        super().__init__(f"OpenRouter {code if code is not None else 'network'} error: {message}")
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class Completion:
    text: str
    model: str | None     # the model OpenRouter says served the request
    provider: str | None  # the upstream provider, when OpenRouter reports it


Transport = Callable[[urllib.request.Request, float], tuple[int, dict[str, str], bytes]]


def urllib_transport(request: urllib.request.Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """Send one HTTP request. Returns (status, headers, body) for any HTTP status; raises
    OpenRouterError(None, ...) for a network failure."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), dict(exc.headers.items()) if exc.headers else {}, exc.read()
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
        raise OpenRouterError(None, f"{type(exc).__name__}: {str(exc)[:200]}") from exc


def _retry_after(headers: dict[str, str]) -> float | None:
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _error_from(status: int, headers: dict[str, str], body: bytes) -> OpenRouterError:
    message = body.decode("utf-8", "replace")[:300]
    code: int | None = status
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or message)[:300]
        if isinstance(error.get("code"), int) and status < 400:
            code = int(error["code"])
    return OpenRouterError(code, message, _retry_after(headers))


def is_transient(exc: OpenRouterError) -> bool:
    """Network failures, 5xx and short rate limits clear up; bad keys, bad requests, unknown models
    and a used-up daily limit don't."""
    if exc.code is None or exc.code >= 500:
        return True
    if exc.code == 429:
        if "per-day" in exc.message.lower() or "per day" in exc.message.lower():
            return False
        return exc.retry_after is None or exc.retry_after <= max(RETRY_DELAYS)
    return False


def parse_completion(body: bytes) -> Completion:
    """The first choice's message text. Raises OpenRouterError when the body carries an error or no text."""
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise OpenRouterError(502, f"response is not JSON: {body[:200]!r}") from exc
    if not isinstance(data, dict):
        raise OpenRouterError(502, "response is not a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        error = data.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            raise OpenRouterError(code if isinstance(code, int) else 502, str(error.get("message"))[:300])
        raise OpenRouterError(502, "response has no choices")
    choice: dict[str, Any] = choices[0]
    if isinstance(choice.get("error"), dict):  # an upstream provider failed mid-request
        code = choice["error"].get("code")
        raise OpenRouterError(code if isinstance(code, int) else 502, str(choice["error"].get("message"))[:300])
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise OpenRouterError(502, "the first choice has no text content")
    model, provider = data.get("model"), data.get("provider")
    return Completion(content.strip(), model if isinstance(model, str) else None,
                      provider if isinstance(provider, str) else None)


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, before_request: Callable[[], None] | None = None,
                 base_url: str = BASE_URL, transport: Transport = urllib_transport,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = TIMEOUT_SECONDS) -> None:
        if not api_key:
            raise ValueError("no OpenRouter API key")
        self._api_key = api_key
        self.model = model
        self._before_request = before_request
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._transport = transport
        self._sleep = sleep
        self._timeout = timeout

    def _request(self, prompt: str) -> urllib.request.Request:
        # No temperature is set: the model's default, as for Gemini (protocol section 5).
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        return urllib.request.Request(
            self._url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json",
                     "X-Title": APP_TITLE})

    def complete(self, prompt: str) -> Completion:
        """One chat completion; each attempt is exactly one HTTP request, announced to before_request."""
        server_retries = 0
        for delay in (*RETRY_DELAYS, None):
            if self._before_request is not None:
                self._before_request()  # may raise (budget); nothing is sent then
            try:
                status, headers, body = self._transport(self._request(prompt), self._timeout)
                if status >= 400:
                    raise _error_from(status, headers, body)
                return parse_completion(body)
            except OpenRouterError as exc:
                if delay is None or not is_transient(exc):
                    raise
                if exc.code is None or exc.code >= 500:
                    if server_retries >= MAX_SERVER_ERROR_RETRIES:
                        raise
                    server_retries += 1
                self._sleep(delay)
        raise AssertionError("unreachable")
