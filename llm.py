"""Gemini access through the google-genai SDK.

The single place that talks to an LLM, so callers don't each build their own
client and the provider can be swapped later without touching them.
"""
import json
import time
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from google import genai

import config


@lru_cache(maxsize=4)
def _client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


RETRY_DELAYS = (2.0, 5.0, 10.0)  # seconds of backoff before each retry
# Gemini's free tier returns 503 "high demand" at busy times, and each retry is another request
# against the daily quota (20 a day), so a server error is retried at most this many times.
MAX_SERVER_ERROR_RETRIES = 1


def _server_retry_delay(exc: Exception) -> float | None:
    """The delay Gemini asks for in a google.rpc.RetryInfo detail (e.g. "52936s"), if any."""
    details = getattr(exc, "details", None)
    items = details.get("error", {}).get("details", []) if isinstance(details, dict) else []
    for item in items if isinstance(items, list) else []:
        delay = item.get("retryDelay") if isinstance(item, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None


def _is_transient(exc: Exception) -> bool:
    """Overload (5xx) and per-minute rate limits (429) clear up; bad keys, bad requests, safety
    blocks and an exhausted daily quota (a 429 asking us to wait longer than our backoff) don't."""
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        return False
    if code == 429:
        wait = _server_retry_delay(exc)
        return wait is None or wait <= max(RETRY_DELAYS)
    return code >= 500


def generate_text(prompt: str, api_key: str) -> str:
    """Send a prompt to the configured Gemini model and return the stripped text.

    Transient errors are retried with backoff (server errors at most MAX_SERVER_ERROR_RETRIES
    times); anything else is raised immediately. The SDK itself doesn't retry (no retry_options),
    so each attempt here is exactly one HTTP request.
    """
    server_retries = 0
    for delay in (*RETRY_DELAYS, None):
        try:
            response = _client(api_key).models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
            return (response.text or "").strip()
        except Exception as exc:
            if delay is None or not _is_transient(exc):
                raise
            if getattr(exc, "code", 0) >= 500:
                if server_retries >= MAX_SERVER_ERROR_RETRIES:
                    raise
                server_retries += 1
            time.sleep(delay)
    raise AssertionError("unreachable")


class IncompleteResponse(RuntimeError):
    """The model stopped early (token limit, safety block): the streamed text is partial."""


def _finish_reason(chunk: Any) -> str | None:
    candidates = getattr(chunk, "candidates", None) or []
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    return None if reason is None else str(getattr(reason, "name", reason))


def generate_text_stream(prompt: str, api_key: str) -> Iterator[str]:
    """Stream the configured Gemini model's answer as pieces of text.

    Until the first piece is yielded, errors follow generate_text's retry rules (transient only, server
    errors at most MAX_SERVER_ERROR_RETRIES times, an exhausted daily quota fails fast). After that nothing
    is retried, since the caller has already shown the text: any error is raised. A stream that ends with
    a finish reason other than STOP raises IncompleteResponse, so a cut-off answer is never taken as whole.
    """
    server_retries = 0
    for delay in (*RETRY_DELAYS, None):
        started = False
        chunks: Iterator[Any] = iter(())
        try:
            chunks = iter(_client(api_key).models.generate_content_stream(model=config.GEMINI_MODEL,
                                                                           contents=prompt))
            last: Any = None
            for chunk in chunks:
                last = chunk
                text = getattr(chunk, "text", None)
                if text:
                    started = True
                    yield text
            reason = _finish_reason(last)
            if reason not in (None, "STOP", "FINISH_REASON_UNSPECIFIED"):
                raise IncompleteResponse(f"Gemini stopped early: {reason}")
            return
        except Exception as exc:
            if started or delay is None or not _is_transient(exc):
                raise
            if getattr(exc, "code", 0) >= 500:
                if server_retries >= MAX_SERVER_ERROR_RETRIES:
                    raise
                server_retries += 1
            time.sleep(delay)
        finally:
            close = getattr(chunks, "close", None)
            if callable(close):
                close()
    raise AssertionError("unreachable")


def parse_json_response(text: str) -> Any:
    """Parse JSON from a model response, removing a surrounding markdown code fence if present."""
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
