"""Shared test setup.

Environment variables are set before any project module is imported: app.py
creates its database engine at import time, and config.py loads .env, which
must never point tests at a real database or a real API key.
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="hireai-tests-"))
# TEST_DATABASE_URL runs the suite on another database, e.g. PostgreSQL. Tests drop and
# recreate every table, so only a database whose name says it is for tests is accepted.
_TEST_DB = os.getenv("TEST_DATABASE_URL")
if _TEST_DB:
    from sqlalchemy.engine import make_url

    if "test" not in (make_url(_TEST_DB).database or "").lower():
        raise RuntimeError("TEST_DATABASE_URL must name a disposable database containing 'test'; "
                           "tests drop all tables.")
os.environ["DATABASE_URL"] = _TEST_DB or f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["GOOGLE_API_KEY"] = ""
# Load Hugging Face models from the local cache only. Online, every model load waits on Hub
# metadata checks, which made the suite take 10+ minutes on a slow network. setdefault lets a
# first run (or a CI step that fills the cache) opt out with HF_HUB_OFFLINE=0.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import config  # noqa: E402
import interview_generator  # noqa: E402
import jd_parser  # noqa: E402
import llm  # noqa: E402
import resume_parser  # noqa: E402


def _no_network_llm(*args, **kwargs):
    raise AssertionError("A test reached the real LLM; mock llm.generate_text or pass a fake client instead.")


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """Every test runs with no API key and with the LLM call fenced off.

    Tests that exercise an LLM path opt in by patching both get_api_key and
    llm.generate_text themselves.
    """
    for module in (config, resume_parser, jd_parser, interview_generator):
        monkeypatch.setattr(module, "get_api_key", lambda: None)
    monkeypatch.setattr(llm, "generate_text", _no_network_llm)
    # Every Gemini call (generation and embeddings) goes through llm._client; block it too.
    monkeypatch.setattr(llm, "_client", _no_network_llm)
