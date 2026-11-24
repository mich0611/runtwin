"""LLM provider boundary.

RunTwin talks to exactly one of two official APIs, chosen by ``RUNTWIN_AI_PROVIDER``:

- ``anthropic``: Claude via the official ``anthropic`` SDK and ``ANTHROPIC_API_KEY``.
- ``openai``: OpenAI via the official ``openai`` SDK (Responses API) and ``OPENAI_API_KEY``.

Both SDKs read their API key from the environment. Every caller only needs plain text back, so
each provider returns a ``str`` and raises ``AIGenerationError`` for refusals, truncation, or
empty output; callers then fall back to deterministic analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

SUPPORTED_PROVIDERS = ("anthropic", "openai")
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-6.2-astra",
}


class AIGenerationError(RuntimeError):
    pass


class AINotConfiguredError(AIGenerationError):
    pass


class TextGenerator(Protocol):
    name: str
    model: str

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> str: ...


@dataclass
class AnthropicTextGenerator:
    """Claude Messages API with adaptive thinking and server-side refusal fallback."""

    client: Any
    model: str
    effort: str = "medium"
    name: str = "anthropic"

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=max_output_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise AIGenerationError("模型拒絕產生內容（refusal）。")
        if response.stop_reason == "max_tokens":
            raise AIGenerationError("模型輸出超出長度限制（max_tokens）。")
        return "\n".join(block.text for block in response.content if block.type == "text").strip()


@dataclass
class OpenAITextGenerator:
    """OpenAI Responses API with reasoning effort; responses are not stored server-side."""

    client: Any
    model: str
    effort: str = "medium"
    name: str = "openai"

    def generate_text(self, *, system: str, user: str, max_output_tokens: int) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=user,
            reasoning={"effort": self.effort},
            max_output_tokens=max_output_tokens,
            store=False,
        )
        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None) or "unknown"
            if reason == "max_output_tokens":
                raise AIGenerationError("模型輸出超出長度限制（max_output_tokens）。")
            raise AIGenerationError(f"模型回應未完成（{reason}）。")
        if response.status != "completed":
            raise AIGenerationError(f"模型回應狀態異常（{response.status}）。")
        for item in response.output or []:
            for part in getattr(item, "content", None) or []:
                if getattr(part, "type", None) == "refusal":
                    raise AIGenerationError("模型拒絕產生內容（refusal）。")
        return (response.output_text or "").strip()


def configured_provider() -> str:
    provider = (settings.RUNTWIN_AI_PROVIDER or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise AINotConfiguredError(
            f"RUNTWIN_AI_PROVIDER 必須是 {' 或 '.join(SUPPORTED_PROVIDERS)}；目前為 {provider or '空白'}。"
        )
    return provider


def configured_model(provider: str) -> str:
    return (settings.RUNTWIN_AI_MODEL or "").strip() or DEFAULT_MODELS[provider]


def build_text_generator(provider: str | None = None, model: str | None = None) -> TextGenerator:
    provider = provider or configured_provider()
    model = model or configured_model(provider)
    effort = settings.RUNTWIN_AI_EFFORT or "medium"
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise AINotConfiguredError("使用 anthropic 需要設定 ANTHROPIC_API_KEY。")
        import anthropic

        return AnthropicTextGenerator(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY), model, effort)
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise AINotConfiguredError("使用 openai 需要設定 OPENAI_API_KEY。")
        import openai

        return OpenAITextGenerator(openai.OpenAI(api_key=settings.OPENAI_API_KEY), model, effort)
    raise AINotConfiguredError(f"不支援的 AI provider：{provider}")
