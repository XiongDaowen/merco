"""HookRegistry interception behavior tests."""

import pytest

from merco.hooks import HookRegistry, HookResult


@pytest.mark.asyncio
async def test_hook_result_data_visible_to_later_handlers():
    """HookResult.data updates kwargs for later handlers and final result."""
    hooks = HookRegistry()
    seen = []

    def first(value: str):
        seen.append(("first", value))
        return HookResult(data={"value": "changed"})

    def second(value: str):
        seen.append(("second", value))

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="original")

    assert seen == [("first", "original"), ("second", "changed")]
    assert isinstance(result, HookResult)
    assert result.stop is False
    assert result.data == {"value": "changed"}


@pytest.mark.asyncio
async def test_hook_result_stop_stops_later_handlers():
    """HookResult(stop=True) stops the remaining handler chain."""
    hooks = HookRegistry()
    called = []

    def first(value: str):
        called.append("first")
        return HookResult(data={"value": "stopped"}, stop=True)

    def second(value: str):
        called.append("second")

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="original")

    assert called == ["first"]
    assert isinstance(result, HookResult)
    assert result.stop is True
    assert result.data == {"value": "stopped"}


@pytest.mark.asyncio
async def test_emit_returns_none_for_no_handlers_or_no_changes():
    """emit returns None when nothing changed."""
    hooks = HookRegistry()

    no_handler_result = await hooks.emit("missing", value="original")
    assert no_handler_result is None

    called = []

    def observer(value: str):
        called.append(value)

    hooks.on("example", observer)
    observer_result = await hooks.emit("example", value="original")

    assert called == ["original"]
    assert observer_result is None


@pytest.mark.asyncio
async def test_hook_result_backward_compatible_none_handlers():
    """Existing None-return handlers still run in registration order."""
    hooks = HookRegistry()
    called = []

    def first(**kwargs):
        called.append(("first", kwargs["value"]))

    async def second(**kwargs):
        called.append(("second", kwargs["value"]))

    hooks.on("example", first)
    hooks.on("example", second)

    result = await hooks.emit("example", value="unchanged")

    assert called == [("first", "unchanged"), ("second", "unchanged")]
    assert result is None


@pytest.mark.asyncio
async def test_emit_handler_error_isolated():
    """A failing handler does not prevent later handlers from running."""
    hooks = HookRegistry()
    called = []

    def failing(**kwargs):
        called.append("failing")
        raise RuntimeError("boom")

    def working(value: str):
        called.append(("working", value))
        return HookResult(data={"value": "recovered"})

    hooks.on("example", failing)
    hooks.on("example", working)

    result = await hooks.emit("example", value="original")

    assert called == ["failing", ("working", "original")]
    assert isinstance(result, HookResult)
    assert result.data == {"value": "recovered"}


@pytest.mark.asyncio
async def test_emit_awaits_callable_returning_coroutine():
    """Callable objects returning coroutine objects are awaited."""
    hooks = HookRegistry()

    class CallableHandler:
        def __call__(self, value: str):
            async def inner():
                return HookResult(data={"value": f"{value}-awaited"})

            return inner()

    hooks.on("example", CallableHandler())

    result = await hooks.emit("example", value="original")

    assert isinstance(result, HookResult)
    assert result.data == {"value": "original-awaited"}
