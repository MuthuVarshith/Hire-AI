"""The injected resumes are exact twins of clean.txt plus the injected lines, and are up to date."""
import difflib

import pytest

from tests.injection.conftest import CLEAN, FIXTURES, NAMES, injected_text, payload
from tests.injection.fixtures._generate import build


@pytest.mark.parametrize("name", NAMES)
def test_injected_resume_differs_from_its_clean_twin_only_by_the_injection(name):
    text = injected_text(name)
    assert text == build(name)  # regenerate with fixtures/_generate.py if this fails
    diff = [line for line in difflib.ndiff(CLEAN.split("\n"), text.split("\n")) if line[:1] in "+-"]
    assert diff == [f"+ {line}" for line in payload(name)]


def test_fixtures_stay_out_of_the_benchmark_corpus():
    assert "sample_resumes" not in FIXTURES.parts
    assert len(list(FIXTURES.glob("injected_*.txt"))) == len(NAMES) >= 7
