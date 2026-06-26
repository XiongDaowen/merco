"""PermissionPolicy + PolicyPipeline 单测"""
import pytest
from merco.sandbox.guard import (
    PermissionPolicy, PolicyPipeline, GuardResult, GuardAction
)


class DenyAllPolicy(PermissionPolicy):
    name = "deny_all"

    async def check(self, tool_name, arguments):
        return GuardResult(action=GuardAction.DENY, command="", reason="禁止一切")


class AllowAllPolicy(PermissionPolicy):
    name = "allow_all"

    async def check(self, tool_name, arguments):
        return GuardResult(action=GuardAction.ALLOW, command="")


class PassPolicy(PermissionPolicy):
    """返回 None — 无意见"""
    name = "pass"

    async def check(self, tool_name, arguments):
        return None


class TestPermissionPolicyABC:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            PermissionPolicy()  # noqa


class TestPolicyPipeline:
    async def test_first_match_wins(self):
        p = PolicyPipeline()
        p.use(DenyAllPolicy())
        p.use(AllowAllPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.DENY

    async def test_pass_to_next(self):
        p = PolicyPipeline()
        p.use(PassPolicy())
        p.use(DenyAllPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.DENY

    async def test_default_allow(self):
        p = PolicyPipeline()
        p.use(PassPolicy())
        result = await p.check("bash", {"command": "ls"})
        assert result.action == GuardAction.ALLOW
