"""PluginDiscovery - 从 entry_points + 目录扫描发现插件，产 PluginSpec 列表。"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points

from merco.plugins.base import Plugin, PluginSpec

logger = logging.getLogger("merco.plugins.discovery")

ENTRY_POINT_GROUP = "merco.plugins"


class PluginDiscovery:
    """发现插件，无副作用（不实例化、不激活、不碰 ctx）。"""

    def __init__(self, config):
        self._config = config

    def discover(self) -> list[PluginSpec]:
        specs: dict[str, PluginSpec] = {}
        # 1. entry_points
        for spec in self._discover_entrypoints():
            specs[spec.name] = spec
        # 2. 目录扫描（覆盖同名 entry_point）— Task 6 补
        return self._finalize(specs)

    def _discover_entrypoints(self) -> list[PluginSpec]:
        out = []
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            if not self._is_enabled(ep.name):
                continue
            spec = PluginSpec(name=ep.name, source="entrypoint", loader=ep.load)
            if not self._load_and_validate(spec, read_meta=True):
                continue
            out.append(spec)
        return out

    def _is_enabled(self, name: str) -> bool:
        return self._config.plugins.get(name, {}).get("enabled", True)

    def _load_and_validate(self, spec: PluginSpec, read_meta: bool) -> bool:
        """load_cls 校验 Plugin 子类 + name 一致。read_meta=True 从类属性读元数据（entrypoint）；
        read_meta=False 保留 spec 已有元数据（dir-scan 从 toml 读）。失败 warn 返回 False。"""
        try:
            cls = spec.load_cls()
        except Exception as e:
            logger.warning("plugin '%s' load failed: %s", spec.name, e)
            return False
        if not (isinstance(cls, type) and issubclass(cls, Plugin)):
            logger.warning("plugin '%s' is not a Plugin subclass", spec.name)
            return False
        if cls.name and cls.name != spec.name:
            logger.warning("plugin '%s' class.name '%s' mismatch", spec.name, cls.name)
        if read_meta:
            spec.version = getattr(cls, "version", "") or spec.version
            spec.description = getattr(cls, "description", "") or spec.description
            spec.priority = getattr(cls, "priority", 50)
            spec.depends_on = list(getattr(cls, "depends_on", []))
        return True

    def _finalize(self, specs: dict[str, PluginSpec]) -> list[PluginSpec]:
        """校验 depends_on 存在性，剪枝。"""
        names = set(specs.keys())
        result = []
        for name, spec in specs.items():
            missing = [d for d in spec.depends_on if d not in names]
            if missing:
                logger.warning("plugin '%s' skipped: missing deps %s", name, missing)
                continue
            result.append(spec)
        return result
