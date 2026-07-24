"""PermissionPolicy end-to-end integration tests"""
from merco.sandbox.guard import (
    BuiltinDefaultPolicy,
    GuardAction,
    GuardResult,
    PermissionPolicy,
    PolicyPipeline,
    ToolGuard,
)


class CustomPolicy(PermissionPolicy):
    name = "custom"

    async def check(self, tool_name, arguments):
        cmd = arguments.get("command", "")
        if "secret" in cmd:
            return GuardResult(action=GuardAction.DENY, command=cmd, reason="contains sensitive keyword")
        return None


async def test_plugin_registers_policy():
    """CustomPolicy catches sensitive keywords, Builtin catches dangerous commands."""
    pipeline = PolicyPipeline()
    # CustomPolicy goes first so it can intercept before Builtin's default-allow fallback
    pipeline.use(CustomPolicy())
    pipeline.use(BuiltinDefaultPolicy(mode="ask"))

    guard = ToolGuard(pipeline=pipeline)

    # Command matched by default rule (not SecurityChecker), returns ASK
    result = await guard.check("bash", {"command": "pip install requests"})
    assert result.action == GuardAction.ASK

    # Sensitive keyword intercepted by CustomPolicy (runs before Builtin)
    result = await guard.check("bash", {"command": "grep secret file"})
    assert result.action == GuardAction.DENY
    assert "sensitive keyword" in result.reason


async def test_auto_mode_skips_all():
    """auto mode: Builtin returns ALLOW immediately, but CustomPolicy still runs first."""
    pipeline = PolicyPipeline()
    # CustomPolicy goes first — catches sensitive keywords regardless of mode
    pipeline.use(CustomPolicy())
    pipeline.use(BuiltinDefaultPolicy(mode="auto"))

    guard = ToolGuard(pipeline=pipeline)

    # auto mode: Builtin would allow, but it never runs because chain stops before it
    # Actually "rm -rf /" doesn't contain "secret", so Custom returns None → Builtin allows
    result = await guard.check("bash", {"command": "rm -rf /"})
    assert result.action == GuardAction.ALLOW

    # CustomPolicy still intercepts sensitive keywords (runs before Builtin)
    result = await guard.check("bash", {"command": "cat secret.txt"})
    assert result.action == GuardAction.DENY
    assert "sensitive keyword" in result.reason
