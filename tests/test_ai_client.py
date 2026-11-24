from types import SimpleNamespace

import pytest

from runtwin.ai.client import (
    DEFAULT_MODELS,
    AIGenerationError,
    AINotConfiguredError,
    AnthropicTextGenerator,
    OpenAITextGenerator,
    build_text_generator,
)


class RecordingCreate:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def anthropic_client(stop_reason="end_turn", text="分析"):
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    messages = RecordingCreate(SimpleNamespace(stop_reason=stop_reason, content=content))
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def openai_client(status="completed", text="分析", incomplete_reason=None, output=None):
    response = SimpleNamespace(
        status=status,
        output_text=text,
        incomplete_details=SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None,
        output=output or [],
    )
    responses = RecordingCreate(response)
    return SimpleNamespace(responses=responses), responses


def test_anthropic_generator_uses_official_messages_api_features():
    client, messages = anthropic_client()

    text = AnthropicTextGenerator(client, "claude-opus-5-5", "high").generate_text(system="sys", user="u", max_output_tokens=100)

    assert text == "分析"
    assert messages.kwargs == {
        "model": "claude-opus-5-5",
        "max_tokens": 100,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
        "system": "sys",
        "messages": [{"role": "user", "content": "u"}],
    }


@pytest.mark.parametrize(("stop_reason", "match"), [("refusal", "refusal"), ("max_tokens", "max_tokens")])
def test_anthropic_generator_rejects_refusal_and_truncation(stop_reason, match):
    client, _ = anthropic_client(stop_reason=stop_reason)

    with pytest.raises(AIGenerationError, match=match):
        AnthropicTextGenerator(client, "m").generate_text(system="s", user="u", max_output_tokens=10)


def test_openai_generator_uses_responses_api_without_storing():
    client, responses = openai_client(text="  分析  ")

    text = OpenAITextGenerator(client, "gpt-6.2-astra", "low").generate_text(system="sys", user="u", max_output_tokens=100)

    assert text == "分析"
    assert responses.kwargs == {
        "model": "gpt-6.2-astra",
        "instructions": "sys",
        "input": "u",
        "reasoning": {"effort": "low"},
        "max_output_tokens": 100,
        "store": False,
    }


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"status": "incomplete", "incomplete_reason": "max_output_tokens"}, "max_output_tokens"),
        ({"status": "incomplete", "incomplete_reason": "content_filter"}, "content_filter"),
        ({"status": "failed"}, "failed"),
        ({"output": [SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="no")])]}, "refusal"),
    ],
)
def test_openai_generator_rejects_incomplete_failed_and_refused(kwargs, match):
    client, _ = openai_client(**kwargs)

    with pytest.raises(AIGenerationError, match=match):
        OpenAITextGenerator(client, "m").generate_text(system="s", user="u", max_output_tokens=10)


@pytest.mark.parametrize("provider", ["", "gateway", "  "])
def test_build_requires_supported_provider(settings, provider):
    settings.RUNTWIN_AI_PROVIDER = provider

    with pytest.raises(AINotConfiguredError, match="RUNTWIN_AI_PROVIDER"):
        build_text_generator()


@pytest.mark.parametrize(("provider", "key"), [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")])
def test_build_requires_provider_api_key(settings, provider, key):
    settings.RUNTWIN_AI_PROVIDER = provider

    with pytest.raises(AINotConfiguredError, match=key):
        build_text_generator()


def test_build_anthropic_uses_official_endpoint_and_default_model(settings, monkeypatch):
    captured = {}
    monkeypatch.setattr("anthropic.Anthropic", lambda **kwargs: captured.update(kwargs) or "client")
    settings.RUNTWIN_AI_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "test-key"
    settings.RUNTWIN_AI_MODEL = ""

    generator = build_text_generator()

    assert captured == {"api_key": "test-key"}
    assert isinstance(generator, AnthropicTextGenerator)
    assert generator.model == DEFAULT_MODELS["anthropic"]


def test_build_openai_uses_official_endpoint_and_model_override(settings, monkeypatch):
    captured = {}
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: captured.update(kwargs) or "client")
    settings.RUNTWIN_AI_PROVIDER = "openai"
    settings.OPENAI_API_KEY = "test-key"
    settings.RUNTWIN_AI_MODEL = "gpt-6.2-sol"
    settings.RUNTWIN_AI_EFFORT = "high"

    generator = build_text_generator()

    assert captured == {"api_key": "test-key"}
    assert isinstance(generator, OpenAITextGenerator)
    assert (generator.model, generator.effort) == ("gpt-6.2-sol", "high")
