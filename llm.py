"""Gemini access through the google-genai SDK.

The single place that talks to an LLM, so callers don't each build their own
client and the provider can be swapped later without touching them.
"""
import json
import time
from functools import lru_cache
from typing import Any

from google import genai

import config


@lru_cache(maxsize=4)
def _client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


RETRY_DELAYS = (2.0, 5.0, 10.0)  # seconds; Gemini's free tier returns 503 "high demand" at busy times


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

    Transient errors are retried with backoff; anything else is raised immediately.
    """
    for delay in (*RETRY_DELAYS, None):
        try:
            response = _client(api_key).models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
            return (response.text or "").strip()
        except Exception as exc:
            if delay is None or not _is_transient(exc):
                raise
            time.sleep(delay)
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
