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


def _is_transient(exc: Exception) -> bool:
    """Overload (5xx) and rate limits (429) clear up; bad keys, bad requests and safety blocks don't."""
    code = getattr(exc, "code", None)
    return isinstance(code, int) and (code == 429 or code >= 500)


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
