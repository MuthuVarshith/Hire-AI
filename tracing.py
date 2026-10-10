"""Optional Langfuse tracing of /api/ask and recruiting-agent runs: retrieval, LLM calls, citations, guards.

Off unless LANGFUSE_ENABLED=true and LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST are all
set. The langfuse package (requirements-eval.txt) is imported only then, so the app runs without it.
When tracing is off, or the package or service is unavailable, every function here is a no-op, and an
error inside tracing is logged and swallowed: tracing never changes a result or fails a request.

SYNTHETIC DATA ONLY. Traces carry questions, prompts and resume excerpts to a third-party service
(Langfuse Cloud), so enable tracing only for sample or synthetic resumes, the same rule as for Gemini.

Spans are linked to their parent explicitly (start_span/start_generation on the parent), not through
context variables, so nesting holds when LangGraph runs a node on another thread. Tests pass a fake
client to set_client(); it needs start_span() returning objects with start_span, start_generation,
update, update_trace and end.
"""
import logging
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
T = TypeVar("T")

_lock = threading.Lock()
_client: Any = None
_resolved = False      # the client was built, or building it failed; don't try again
_override: Any = None  # a client set with set_client (tests)


def enabled() -> bool:
    """True when tracing is switched on and fully configured (or a client was set with set_client)."""
    if _override is not None:
        return True
    flag = os.getenv("LANGFUSE_ENABLED", "false").strip().lower() == "true"
    return flag and all(os.getenv(name, "").strip() for name in REQUIRED_SETTINGS)


def set_client(client: Any) -> None:
    """Trace to this client instead of Langfuse (tests pass a fake); None goes back to the configuration."""
    global _override
    _override = client


def _safe(call: Callable[[], T]) -> T | None:
    try:
        return call()
    except Exception:
        logger.debug("Langfuse tracing call failed; continuing without it", exc_info=True)
        return None


def _get_client() -> Any:
    global _client, _resolved
    if _override is not None:
        return _override
    if not enabled():
        return None
    with _lock:
        if not _resolved:
            _resolved = True
            try:
                from langfuse import Langfuse  # optional: requirements-eval.txt

                _client = Langfuse(public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                                   secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                                   host=os.environ["LANGFUSE_HOST"])
            except Exception:
                logger.warning("Langfuse tracing is configured but unavailable, so it is off", exc_info=True)
                _client = None
        return _client


class Span:
    """A Langfuse observation, or a no-op when tracing is off. No method ever raises."""

    def __init__(self, observation: Any = None, root: bool = False) -> None:
        self._obs = observation
        self._root = root
        self._ended = False

    @property
    def active(self) -> bool:
        return self._obs is not None

    def span(self, name: str, *, input: Any = None, metadata: Any = None) -> "Span":
        if self._obs is None:
            return NOOP
        obs = self._obs
        return Span(_safe(lambda: obs.start_span(name=name, input=input, metadata=metadata)))

    def generation(self, name: str, *, model: str | None, input: Any = None, metadata: Any = None) -> "Span":
        if self._obs is None:
            return NOOP
        obs = self._obs
        return Span(_safe(lambda: obs.start_generation(name=name, model=model, input=input, metadata=metadata)))

    def event(self, name: str, *, metadata: Any = None, level: str | None = None) -> None:
        """A zero-length child span, e.g. a guard that fired."""
        self.span(name, metadata=metadata).end(level=level)

    def end(self, *, output: Any = None, metadata: Any = None, level: str | None = None,
            status_message: str | None = None) -> None:
        """Record the outcome and close the observation; later calls do nothing."""
        if self._obs is None or self._ended:
            return
        self._ended = True
        obs = self._obs
        fields = {key: value for key, value in (("output", output), ("metadata", metadata), ("level", level),
                                                ("status_message", status_message)) if value is not None}
        if fields:
            _safe(lambda: obs.update(**fields))
        if self._root and output is not None:
            _safe(lambda: obs.update_trace(output=output))
        _safe(lambda: obs.end())


NOOP = Span()


def start_trace(name: str, *, input: Any = None, metadata: Any = None) -> Span:
    """A new trace's root span, or NOOP when tracing is off or unavailable."""
    client = _safe(_get_client)
    if client is None:
        return NOOP
    root = _safe(lambda: client.start_span(name=name, input=input, metadata=metadata))
    if root is None:
        return NOOP
    _safe(lambda: root.update_trace(name=name, input=input, metadata=metadata))
    return Span(root, root=True)


@contextmanager
def trace(name: str, *, input: Any = None, metadata: Any = None) -> Iterator[Span]:
    """Trace a block. An exception from the block is recorded on the trace and re-raised unchanged."""
    span = start_trace(name, input=input, metadata=metadata)
    try:
        yield span
    except BaseException as exc:
        span.end(level="ERROR", status_message=type(exc).__name__)
        raise
    span.end()


def flush() -> None:
    """Send buffered traces now (scripts call this before exiting; the app relies on Langfuse's own flushing)."""
    client = _safe(_get_client)
    if client is not None:
        _safe(lambda: client.flush())
