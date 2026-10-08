"""Gemini access through the google-genai SDK.

The single place that talks to an LLM, so callers don't each build their own
client and the provider can be swapped later without touching them.
"""
import json
from functools import lru_cache
from typing import Any

from google import genai

import config


@lru_cache(maxsize=4)
def _client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def generate_text(prompt: str, api_key: str) -> str:
    """Send a prompt to the configured Gemini model and return the stripped text."""
    response = _client(api_key).models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
    return (response.text or "").strip()


def parse_json_response(text: str) -> Any:
    """Parse JSON from a model response, removing a surrounding markdown code fence if present."""
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())
