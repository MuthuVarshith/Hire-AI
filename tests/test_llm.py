"""Tests for the Gemini wrapper, API-key lookup and LLM-backed rationale text."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
import llm
import ranker
from config import CandidateScore

# Captured at import, before the autouse conftest fixture swaps them out.
REAL_GENERATE_TEXT = llm.generate_text
REAL_GET_API_KEY = config.get_api_key
REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("text", ['{"a": 1}', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', '  {"a": 1}  '])
def test_parse_json_response_strips_code_fences(text):
    assert llm.parse_json_response(text.strip()) == {"a": 1}


def test_parse_json_response_rejects_non_json():
    with pytest.raises(json.JSONDecodeError):
        llm.parse_json_response("not json")


class _FakeModels:
    def __init__(self, text):
        self.text, self.calls = text, []

    def generate_content(self, *, model, contents):
        self.calls.append((model, contents))
        return SimpleNamespace(text=self.text)


@pytest.mark.parametrize("returned, expected", [("  hello  ", "hello"), (None, "")])
def test_generate_text_uses_configured_model(monkeypatch, returned, expected):
    models = _FakeModels(returned)
    monkeypatch.setattr(llm, "_client", lambda api_key: SimpleNamespace(models=models))
    monkeypatch.setattr(llm, "generate_text", REAL_GENERATE_TEXT)
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-test-model")

    assert llm.generate_text("prompt text", "key") == expected
    assert models.calls == [("gemini-test-model", "prompt text")]


def test_gemini_model_is_configurable_via_environment():
    code = "import config; print(config.GEMINI_MODEL)"
    def run(env):
        return subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                              capture_output=True, text=True, check=True).stdout.strip()

    base = {k: v for k, v in os.environ.items() if k != "GEMINI_MODEL"}
    assert run({**base, "GEMINI_MODEL": "gemini-custom"}) == "gemini-custom"
    assert run({**base, "GEMINI_MODEL": ""}) == "gemini-3.8-flash"  # empty means unset, not ""


def test_default_gemini_model_without_override(monkeypatch, tmp_path):
    code = "import config; print(config.GEMINI_MODEL)"
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_MODEL"}
    # Run from a copy of config.py in an empty folder so a local .env can't override the default.
    (tmp_path / "config.py").write_text((REPO / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "gemini-3.8-flash"


@pytest.mark.parametrize("env_value, file_line, expected", [
    ("real-key", None, "real-key"),
    ("your_api_key_here", None, None),          # template placeholder is not a key
    ("", "GOOGLE_API_KEY=file-key", "file-key"),
    ("", "GOOGLE_API_KEY=your_api_key_here", None),
    ("", None, None),
])
def test_get_api_key(monkeypatch, tmp_path, env_value, file_line, expected):
    monkeypatch.setenv("GOOGLE_API_KEY", env_value)
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))  # look for .env in tmp_path
    if file_line:
        (tmp_path / ".env").write_text(file_line + "\n", encoding="utf-8")
    assert REAL_GET_API_KEY() == expected


def _score():
    return CandidateScore(name="Ada", composite_score=81.5, semantic_score=70.0, skill_match_score=90.0,
                          experience_score=100.0, education_score=70.0,
                          matched_skills=["python", "docker"], missing_skills=["kubernetes"])


def test_rank_candidates_without_llm_uses_template():
    results = ranker.rank_candidates([_score()], api_key=None)
    assert results[0]["reasoning"] == (
        "Ranked #1 with a composite score of 81.5/100. Matched 2/3 required skills (python, docker). "
        "Key gaps: missing kubernetes. Meets experience requirements."
    )


def test_rank_candidates_with_llm(monkeypatch):
    monkeypatch.setattr(llm, "generate_text", lambda prompt, key: "LLM rationale")
    assert ranker.rank_candidates([_score()], api_key="k")[0]["reasoning"] == "LLM rationale"


def test_rank_candidates_llm_failure_falls_back_to_template(monkeypatch):
    def boom(prompt, key):
        raise RuntimeError("quota")

    monkeypatch.setattr(llm, "generate_text", boom)
    reasoning = ranker.rank_candidates([_score()], api_key="k")[0]["reasoning"]
    assert reasoning.startswith("Ranked #1 with a composite score")


class _FlakyModels:
    def __init__(self, failures):
        self.failures, self.calls = list(failures), 0

    def generate_content(self, *, model, contents):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(text="fine")


def _api_error(code):
    error = RuntimeError(f"HTTP {code}")
    error.code = code
    return error


def test_transient_errors_are_retried_with_backoff(monkeypatch):
    models = _FlakyModels([_api_error(503), _api_error(429)])
    sleeps = []
    monkeypatch.setattr(llm, "_client", lambda key: SimpleNamespace(models=models))
    monkeypatch.setattr(llm, "generate_text", REAL_GENERATE_TEXT)
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    assert llm.generate_text("p", "k") == "fine"
    assert models.calls == 3 and sleeps == [2.0, 5.0]


def test_permanent_errors_are_not_retried(monkeypatch):
    models = _FlakyModels([_api_error(403)])
    monkeypatch.setattr(llm, "_client", lambda key: SimpleNamespace(models=models))
    monkeypatch.setattr(llm, "generate_text", REAL_GENERATE_TEXT)
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("must not sleep"))
    with pytest.raises(RuntimeError, match="403"):
        llm.generate_text("p", "k")
    assert models.calls == 1


def test_gives_up_after_the_last_retry(monkeypatch):
    models = _FlakyModels([_api_error(503)] * 10)
    monkeypatch.setattr(llm, "_client", lambda key: SimpleNamespace(models=models))
    monkeypatch.setattr(llm, "generate_text", REAL_GENERATE_TEXT)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="503"):
        llm.generate_text("p", "k")
    assert models.calls == 4  # first try + 3 retries
