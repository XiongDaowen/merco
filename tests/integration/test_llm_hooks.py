"""Integration tests for interceptable LLM hooks."""

import pytest

from merco.hooks import HookResult


@pytest.mark.asyncio
async def test_llm_before_chat_can_modify_messages_and_tools(test_agent):
    """llm.before_chat can replace messages and tools before LLM call."""
    agent = test_agent
    agent.llm.responses = [{"content": "done", "finish_reason": "stop"}]

    async def before_chat(messages, tools, **kwargs):
        modified_messages = list(messages)
        modified_messages.append({"role": "user", "content": "hook injected"})
        return HookResult(data={"messages": modified_messages, "tools": []})

    agent.hooks.on("llm.before_chat", before_chat)

    result = await agent.run("hello")

    assert result == "done"
    assert agent.llm.calls, "LLM should have been called"
    call = agent.llm.calls[-1]
    assert call["messages"][-1] == {"role": "user", "content": "hook injected"}
    assert call["tools"] is None


@pytest.mark.asyncio
async def test_llm_before_chat_can_short_circuit_with_response(test_agent):
    """llm.before_chat stop=True with response skips the LLM call."""
    agent = test_agent
    agent.llm.responses = [{"content": "should not be used", "finish_reason": "stop"}]

    async def before_chat(messages, tools, **kwargs):
        return HookResult(
            data={"response": {"content": "from hook", "finish_reason": "stop"}},
            stop=True,
        )

    agent.hooks.on("llm.before_chat", before_chat)

    result = await agent.run("hello")

    assert result == "from hook"
    assert agent.llm.calls == []
