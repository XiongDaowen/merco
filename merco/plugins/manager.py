"""PluginManager - plugin lifecycle management"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Plugin, PluginContext, PluginSpec

logger = logging.getLogger("merco.plugins.manager")


class PluginManager:
    """Plugin discovery, loading, activation, and deactivation"""

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

    async def activate(self, name: str) -> None:
        """Activate a single plugin"""
        if name in self._active:
            return
        plugin = self._plugins.get(name)
        if not plugin:
            logger.warning("Plugin '%s' not registered", name)
            return
        try:
            if name not in self._ever_activated:
                await plugin.activate(self._ctx)
                self._ever_activated.add(name)
            self._active.add(name)
            await self._ctx.hooks.emit("plugin.activated", plugin_name=name, version=plugin.version)
        except Exception as e:
            logger.warning("Plugin '%s' activation failed: %s", name, e)
            try:
                await self._ctx.hooks.emit("plugin.error", plugin_name=name, error=str(e))
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
        """Activate all enabled plugins at startup"""
        plugins_config = getattr(self._ctx.config, "plugins", {})
        for name in self._plugins:
            plugin_cfg = plugins_config.get(name, {})
            if plugin_cfg.get("enabled", True):
                await self.activate(name)

    async def deactivate_all(self) -> None:
        """Deactivate all active plugins"""
        for name in list(self._active):
            await self.deactivate(name)

    @property
    def active_plugins(self) -> list[str]:
        """Return list of active plugin names"""
        return list(self._active)
