"""The agent's LLM provider, chosen by AGENT_LLM_PROVIDER: gemini (default), openai, anthropic, ollama or none.

Gemini goes through llm.py (google-genai, with its retry logic). The other SDKs are optional
and not in requirements.txt; they are imported only when selected, and a missing SDK is a
clear ProviderError. Every provider returns plain text for one prompt; the agent parses it.

No provider is used unless AGENT_LLM_ENABLED=true, because the planner sees resume passages:
like ASK_LLM_ENABLED, it is meant for synthetic or sample resumes only. With the flag off,
provider "none", or no API key, get_provider returns None and the agent uses its rule-based
router instead.
"""
import importlib
import json
import logging
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import config
import llm

logger = logging.getLogger(__name__)

PROVIDERS = ("gemini", "openai", "anthropic", "ollama", "none")
# Defaults for the optional providers; each is overridable, e.g. AGENT_OPENAI_MODEL. Neither the
# OpenAI nor the Anthropic default has been run live in this project; both are mocked in tests.
DEFAULT_MODELS = {"openai": "gpt-5.4-mini", "anthropic": "claude-opus-5-5", "ollama": "llama3.1"}
# Reasoning and thinking tokens count toward these limits, so they are far above the JSON reply's size.
OPENAI_MAX_COMPLETION_TOKENS = 16000
ANTHROPIC_MAX_TOKENS = 16000
# Anthropic's server-side refusal fallback (beta), on by default; the installed SDK (anthropic 1.11)
# accepts `betas` and `fallbacks` on client.beta.messages.create.
ANTHROPIC_BETAS = ["server-side-fallback-2026-07-01"]


class ProviderError(RuntimeError):
    """The configured provider can't be used: unknown name or SDK not installed."""


class ProviderRefusal(RuntimeError):
    """The model declined the request or was cut off at its token limit. The agent records a
    failed planner turn and asks again (within its caps) instead of reading partial output."""


class ChatProvider(Protocol):
    name: str

    def generate(self, prompt: str) -> str: ...


def enabled() -> bool:
    return os.getenv("AGENT_LLM_ENABLED", "false").strip().lower() == "true"


def provider_name() -> str:
    name = (os.getenv("AGENT_LLM_PROVIDER") or "gemini").strip().lower()
    if name not in PROVIDERS:
        raise ProviderError(f"AGENT_LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {name!r}")
    return name


def _model(name: str) -> str:
    return os.getenv(f"AGENT_{name.upper()}_MODEL") or DEFAULT_MODELS[name]


def _sdk(module: str, provider: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ProviderError(f"AGENT_LLM_PROVIDER={provider} needs the optional '{module}' package: "
                            f"pip install {module}") from exc


@dataclass
class GeminiProvider:
    api_key: str
    name: str = "gemini"

    def generate(self, prompt: str) -> str:
        # Looked up at call time so the test suite's fence on llm.generate_text applies.
        return llm.generate_text(prompt, self.api_key)


@dataclass
class OpenAIProvider:
    api_key: str
    name: str = "openai"

    def generate(self, prompt: str) -> str:
        client = _sdk("openai", self.name).OpenAI(api_key=self.api_key)
        # gpt-5 models reject max_tokens; max_completion_tokens is the current parameter.
        response = client.chat.completions.create(model=_model(self.name),
                                                  max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
                                                  messages=[{"role": "user", "content": prompt}])
        choice = response.choices[0]
        if choice.finish_reason in ("length", "content_filter") or getattr(choice.message, "refusal", None):
            raise ProviderRefusal(f"openai finish_reason={choice.finish_reason}")
        return str(choice.message.content or "").strip()


@dataclass
class AnthropicProvider:
    api_key: str
    name: str = "anthropic"

    def generate(self, prompt: str) -> str:
        client = _sdk("anthropic", self.name).Anthropic(api_key=self.api_key)
        # No thinking parameter: the default model always thinks, within max_tokens.
        response = client.beta.messages.create(model=_model(self.name), max_tokens=ANTHROPIC_MAX_TOKENS,
                                               messages=[{"role": "user", "content": prompt}],
                                               betas=ANTHROPIC_BETAS, fallbacks="default")
        if response.stop_reason in ("refusal", "max_tokens"):
            raise ProviderRefusal(f"anthropic stop_reason={response.stop_reason}")  # content is not read
        return "".join(block.text for block in response.content if block.type == "text").strip()


@dataclass
class OllamaProvider:
    """A local Ollama server over its HTTP API (no SDK needed); OLLAMA_HOST defaults to localhost."""
    host: str
    name: str = "ollama"

    def generate(self, prompt: str) -> str:
        body = json.dumps({"model": _model(self.name), "prompt": prompt, "stream": False}).encode()
        request = urllib.request.Request(f"{self.host.rstrip('/')}/api/generate", data=body,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            return str(json.loads(response.read()).get("response", "")).strip()


def _key(variable: str) -> str | None:
    return os.getenv(variable) or None


_FACTORIES: dict[str, Callable[[], ChatProvider | None]] = {
    "gemini": lambda: GeminiProvider(key) if (key := config.get_api_key()) else None,
    "openai": lambda: OpenAIProvider(key) if (key := _key("OPENAI_API_KEY")) else None,
    "anthropic": lambda: AnthropicProvider(key) if (key := _key("ANTHROPIC_API_KEY")) else None,
    "ollama": lambda: OllamaProvider(os.getenv("OLLAMA_HOST") or "http://localhost:11434"),
    "none": lambda: None,
}


def get_provider() -> ChatProvider | None:
    """The configured provider, or None for the rule-based router (flag off, "none", or no key).

    Raises ProviderError for an unknown provider name or a selected SDK that isn't installed.
    """
    if not enabled():
        return None
    name = provider_name()
    if name == "openai":
        _sdk("openai", name)
    elif name == "anthropic":
        _sdk("anthropic", name)
    provider = _FACTORIES[name]()
    if provider is None and name != "none":
        logger.info("No API key for AGENT_LLM_PROVIDER=%s; the agent uses its rule-based router", name)
    return provider
