"""The optional OpenAI and Anthropic providers, with fake SDK modules: the request each one sends,
which reply text is read, and refusals or truncation recorded as a failed planner turn. No network."""
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import agent
import agent_llm
from tests.test_agent_tools import no_model  # noqa: F401  (fixture)
from tests.test_recruiting_agent import env  # noqa: F401  (fixture)

FINISH = '{"action": "finish", "message": "Done."}'


class FakeAnthropic:
    """Stands in for the anthropic module; records the kwargs of each beta.messages.create call."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        create = self._create
        self.Anthropic = lambda api_key: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def anthropic_reply(stop_reason="end_turn", *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def block(kind, text=""):
    return SimpleNamespace(type=kind, text=text)


class FakeOpenAI:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        create = self._create
        self.OpenAI = lambda api_key: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def openai_reply(content, finish_reason="stop", refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason, message=message)])


@pytest.fixture
def sdk(monkeypatch):
    def install(module):
        monkeypatch.setattr(agent_llm.importlib, "import_module", lambda name: module)
        return module
    return install


def test_anthropic_request_uses_the_fallback_beta_and_reads_only_text_blocks(sdk, monkeypatch):
    monkeypatch.delenv("AGENT_ANTHROPIC_MODEL", raising=False)
    fake = sdk(FakeAnthropic(anthropic_reply("end_turn", block("thinking"), block("text", FINISH),
                                             block("server_tool_use", "ignored"))))
    assert agent_llm.AnthropicProvider("key").generate("prompt") == FINISH
    (call,) = fake.calls
    assert call["model"] == "claude-opus-5-5" and call["max_tokens"] == 16000
    assert (call["betas"], call["fallbacks"]) == (["server-side-fallback-2026-07-01"], "default")
    assert "thinking" not in call and "budget_tokens" not in call
    assert call["messages"] == [{"role": "user", "content": "prompt"}]


def test_anthropic_model_can_be_overridden(sdk, monkeypatch):
    monkeypatch.setenv("AGENT_ANTHROPIC_MODEL", "claude-sonnet-5-5")
    fake = sdk(FakeAnthropic(anthropic_reply("end_turn", block("text", FINISH))))
    agent_llm.AnthropicProvider("key").generate("prompt")
    assert fake.calls[0]["model"] == "claude-sonnet-5-5"


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_anthropic_refusal_or_truncation_is_not_read(sdk, stop_reason):
    sdk(FakeAnthropic(anthropic_reply(stop_reason, block("text", FINISH))))
    with pytest.raises(agent_llm.ProviderRefusal):
        agent_llm.AnthropicProvider("key").generate("prompt")


def test_openai_request_uses_a_current_model_and_max_completion_tokens(sdk, monkeypatch):
    monkeypatch.delenv("AGENT_OPENAI_MODEL", raising=False)
    fake = sdk(FakeOpenAI(openai_reply(FINISH)))
    assert agent_llm.OpenAIProvider("key").generate("prompt") == FINISH
    (call,) = fake.calls
    assert (call["model"], call["max_completion_tokens"]) == ("gpt-5.4-mini", 16000)
    assert "max_tokens" not in call


@pytest.mark.parametrize("reply", [openai_reply(FINISH, finish_reason="length"),
                                   openai_reply(FINISH, finish_reason="content_filter"),
                                   openai_reply(None, refusal="I can't help with that.")])
def test_openai_refusal_or_truncation_is_not_read(sdk, reply):
    sdk(FakeOpenAI(reply))
    with pytest.raises(agent_llm.ProviderRefusal):
        agent_llm.OpenAIProvider("key").generate("prompt")


def test_a_refused_turn_is_recorded_and_the_planner_is_asked_again(env, sdk):  # noqa: F811
    ctx, _, _ = env
    sdk(FakeAnthropic(anthropic_reply("refusal", block("text", "partial")),
                      anthropic_reply("end_turn", block("text", FINISH))))
    result = agent.start_run(ctx, "Who knows Python?", agent.LLMPlanner(agent_llm.AnthropicProvider("key")),
                             InMemorySaver())
    assert result["status"] == "answered" and result["message"] == "Done."
    assert result["steps"] == [{"type": "refused", "error": "the model declined or was cut off"}]
    assert "partial" not in repr(result)
