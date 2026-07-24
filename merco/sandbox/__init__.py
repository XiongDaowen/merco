"""沙箱系统"""

from .guard import _DEFAULT_RULES, GuardRule, ToolGuard


def create_tool_guard(config=None) -> ToolGuard:
    """从 MercoConfig 加载 sandbox_rules 创建 ToolGuard"""
    if config is None:
        from merco.core.config import MercoConfig
        config = MercoConfig.load()

    mode = getattr(config, 'sandbox_mode', 'ask')
    user_rules = getattr(config, 'sandbox_rules', []) or []
    return ToolGuard(mode=mode, user_rules=user_rules)


# 模块级单例（默认配置）
try:
    tool_guard = create_tool_guard()
except Exception:
    # 配置未初始化时用默认值
    tool_guard = ToolGuard(mode='ask', user_rules=[])

__all__ = [
    "ToolGuard",
    "GuardRule",
    "_DEFAULT_RULES",
    "tool_guard",
    "create_tool_guard",
]
