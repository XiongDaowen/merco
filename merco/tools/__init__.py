"""工具系统 — 自动发现、toolset 过滤、动态描述"""

import importlib.util
import logging
import os
from pathlib import Path

from .registry import ToolRegistry, tool_registry
from .base import BaseTool

logger = logging.getLogger("merco.tools")

# 内置工具模块列表
_BUILTIN_MODULES = [
    "merco.tools.file_tools",
    "merco.tools.bash_tools",
    "merco.tools.web_tools",
    "merco.tools.task_tools",
    "merco.tools.skill_tools",
    "merco.tools.edit",
]


def discover_tools(tool_paths: list[str] | None = None):
    """导入内置工具 + 扫描外部路径，触发各模块的自注册。

    内置工具：导入 _BUILTIN_MODULES 列表中的所有模块。
    外部工具：扫描 tool_paths 中的每个目录，importlib 动态加载 *.py 文件。

    每个工具模块在 import 时会调用 tool_registry.register() 完成注册。
    外部工具与内置工具写法完全一致：继承 BaseTool，末尾调用 register()。
    """
    # 1. 内置工具
    for mod_name in _BUILTIN_MODULES:
        try:
            importlib.import_module(mod_name)
        except Exception:
            logger.warning("加载内置工具模块失败: %s", mod_name, exc_info=True)

    # 2. 外部工具路径
    if tool_paths:
        for base_path in tool_paths:
            expanded = os.path.expanduser(base_path)
            if not os.path.isdir(expanded):
                logger.debug("工具路径不存在，跳过: %s", expanded)
                continue

            for pyfile in sorted(Path(expanded).glob("*.py")):
                mod_name = f"_ext_tool_{pyfile.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, str(pyfile))
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        logger.debug("已加载外部工具: %s", pyfile)
                except Exception:
                    logger.warning("加载外部工具失败: %s", pyfile, exc_info=True)


__all__ = ["ToolRegistry", "BaseTool", "tool_registry", "discover_tools"]
