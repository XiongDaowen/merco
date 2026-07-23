"""PluginManager - plugin lifecycle management"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Plugin, PluginContext, PluginSpec

logger = logging.getLogger("merco.plugins.manager")


class PluginManager:
    """Plugin discovery, loading, activation, and deactivation"""

    BOOT_PRIORITY = 100

    def __init__(self, ctx: "PluginContext"):
        self._ctx = ctx
        self._plugins: dict[str, "Plugin"] = {}
        self._specs: dict[str, "PluginSpec"] = {}
        self._active: set[str] = set()
        self._ever_activated: set[str] = set()

    def register(self, plugin: "Plugin") -> None:
        """Register a plugin instance"""
        self._plugins[plugin.name] = plugin

    def register_all(self, specs: list) -> None:
        """注册一批 PluginSpec（discovery 产出）"""
        for spec in specs:
            self._specs[spec.name] = spec

    def _all_names(self) -> list[str]:
        """_plugins 与 _specs 键的并集"""
        return list(set(self._plugins.keys()) | set(self._specs.keys()))

    def _meta(self, name: str) -> tuple[int, list[str]]:
        """返回 (priority, depends_on)；无 spec 则默认 (50, [])"""
        spec = self._specs.get(name)
        if spec is None:
            return (50, [])
        return (spec.priority, list(spec.depends_on))

    def _resolve_order(self, names: list[str], boot_only: bool = False) -> list[str]:
        """返回激活顺序：拓扑(depends_on) + priority 降序 + name 升序。循环/缺依赖排除。"""
        pool = set(names)
        if boot_only:
            pool = {n for n in pool if self._meta(n)[0] >= self.BOOT_PRIORITY}

        # 存在性剪枝（迭代到稳定：移除依赖不在池内的，级联）
        pruned: set[str] = set()
        changed = True
        while changed:
            changed = False
            for n in pool - pruned:
                deps = self._meta(n)[1]
                if any(d not in (pool - pruned) for d in deps):
                    logger.warning("plugin '%s' skipped: dependency not present", n)
                    pruned.add(n)
                    changed = True
        active_pool = pool - pruned

        # Kahn 拓扑排序，同层按 priority 降序、name 升序
        result: list[str] = []
        remaining = set(active_pool)
        while remaining:
            ready = [n for n in remaining if all(d in result for d in self._meta(n)[1])]
            if not ready:
                logger.warning("circular dependency among: %s", sorted(remaining))
                break  # 剩余为循环依赖，排除
            ready.sort(key=lambda n: (-self._meta(n)[0], n))
            result.extend(ready)
            remaining -= set(ready)
        return result

    async def activate(self, name: str) -> None:
        """Activate a single plugin (lazy-instantiate from spec if needed)."""
        if name in self._active:
            return
        plugin = self._plugins.get(name)
        if plugin is None:
            spec = self._specs.get(name)
            if spec is None:
                logger.warning("Plugin '%s' not registered", name)
                return
            try:
                plugin = spec.instantiate()
            except Exception as e:
                logger.warning("Plugin '%s' instantiation failed: %s", name, e)
                await self._emit_error(name, str(e))
                return
            self._plugins[name] = plugin
        # dep-active 检查
        for dep in self._meta(name)[1]:
            if dep not in self._active:
                logger.warning("Plugin '%s' skipped: dependency '%s' not active", name, dep)
                return
        try:
            if name not in self._ever_activated:
                await plugin.activate(self._ctx)
                self._ever_activated.add(name)
            self._active.add(name)
            await self._ctx.hooks.emit("plugin.activated", plugin_name=name, version=plugin.version)
        except Exception as e:
            logger.warning("Plugin '%s' activation failed: %s", name, e)
            await self._emit_error(name, str(e))

    async def _emit_error(self, name: str, error: str) -> None:
        try:
            await self._ctx.hooks.emit("plugin.error", plugin_name=name, error=error)
        except Exception:
            pass

    async def deactivate(self, name: str) -> None:
        """Deactivate a single plugin"""
        plugin = self._plugins.get(name)
        if not plugin:
            return
        try:
            await plugin.deactivate()
        except Exception as e:
            logger.warning("Plugin '%s' deactivation failed: %s", name, e)
        self._active.discard(name)
        try:
            await self._ctx.hooks.emit("plugin.deactivated", plugin_name=name)
        except Exception:
            pass

    async def activate_all(self) -> None:
        """Activate all enabled plugins in topo+priority order."""
        plugins_config = getattr(self._ctx.config, "plugins", {})
        for name in self._resolve_order(self._all_names()):
            if not plugins_config.get(name, {}).get("enabled", True):
                continue
            await self.activate(name)

    async def activate_boot(self) -> None:
        """Activate boot-phase plugins (priority >= BOOT_PRIORITY) before context restore."""
        for name in self._resolve_order(self._all_names(), boot_only=True):
            await self.activate(name)

    async def deactivate_all(self) -> None:
        """Deactivate all active plugins"""
        for name in list(self._active):
            await self.deactivate(name)

    @property
    def active_plugins(self) -> list[str]:
        """Return list of active plugin names"""
        return list(self._active)
