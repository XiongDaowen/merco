"""ModelProvider ABC + ModelProviderInfo.

The ABC defines a normalized contract: chat/chat_stream take OpenAI-shaped
messages/tools and return/yield normalized response dicts:
    {role, content, reasoning, finish_reason,
     usage{prompt_tokens,completion_tokens,total,cached?},
     tool_calls[{id, type, function{name, arguments}}]}
Each provider populates `reasoning` its own way (OpenAI-compatible via
thinking.py; Anthropic via native thinking blocks).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


class ModelProvider(ABC):
    """Model transport ABC. Instance holds connection + sampling config."""

    name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Any = "auto",
    ) -> dict:
        """Non-streaming. Return a normalized response dict."""

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Any = "auto",
    ) -> AsyncIterator[dict]:
        """Streaming. Yield normalized chunk dicts."""


@dataclass
class ModelProviderInfo:
    """Provider metadata - the registry/wizard source of truth.

    Strict superset of the old ProviderInfo (drops the dict-compat __getitem__,
    which was debt). ``provider_class`` is what makes this a registry spec, not
    a static dict.
    """

    name: str                                  # id: "openai" / "anthropic" / third-party
    provider_class: type[ModelProvider]
    display_name: str = ""                     # wizard label: "OpenAI"
    base_url: str = ""
    key_env: str = ""                          # provider knows its own key env
    key_help: str = ""                         # URL to obtain a key (wizard)
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    description: str = ""