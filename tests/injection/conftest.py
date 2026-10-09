"""Shared data for the prompt-injection tests: the synthetic twins and the sample job description.

The root tests/conftest.py still applies: every test starts with no API key and with
llm.generate_text fenced off. Tests here opt in by patching both with a mocked LLM; no
test reaches Gemini.
"""
from pathlib import Path

from tests.injection.fixtures._generate import INJECTIONS

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = FIXTURES.parent.parent.parent
SAMPLE_JD = (REPO / "sample_jd" / "jd.txt").read_text(encoding="utf-8")
CLEAN = (FIXTURES / "clean.txt").read_text(encoding="utf-8")
NAMES = sorted(INJECTIONS)


def injected_text(name: str) -> str:
    return (FIXTURES / f"injected_{name}.txt").read_text(encoding="utf-8")


def payload(name: str) -> list[str]:
    """The injected lines, i.e. exactly what the injected resume adds to its clean twin."""
    return INJECTIONS[name][1]
