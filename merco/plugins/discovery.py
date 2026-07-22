"""PluginDiscovery - 从 entry_points + 目录扫描发现插件，产 PluginSpec 列表。"""
from __future__ import annotations

import logging
import tomllib
import importlib.util
from importlib.metadata import entry_points
from pathlib import Path

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
            if spec.name in specs:
                logger.warning("duplicate plugin name '%s': entry_point overwritten", spec.name)
            specs[spec.name] = spec
        # 2. 目录扫描（覆盖同名 entry_point）
        for spec in self._discover_dirs():
            if spec.name in specs:
                logger.info("plugin '%s': dir-scan overrides entry_point", spec.name)
            specs[spec.name] = spec
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

    def _discover_dirs(self) -> list[PluginSpec]:
        out = []
        for raw in self._config.plugins_paths:
            base = Path(raw).expanduser()
            if not base.is_dir():
                continue
            for pdir in sorted(base.iterdir()):
                if not pdir.is_dir():
                    continue
                spec = self._spec_from_dir(pdir)
                if spec is not None:
                    out.append(spec)
        return out

    def _spec_from_dir(self, pdir: Path) -> PluginSpec | None:
        toml = pdir / "plugin.toml"
        if not toml.is_file():
            return None  # 不是插件，静默跳过
        try:
            with open(toml, "rb") as f:
                data = tomllib.load(f)
            p = data["plugin"]
            name = p["name"]
            entry = p["entry"]
        except Exception as e:
            logger.warning("plugin dir '%s' manifest parse failed: %s", pdir.name, e)
            return None
        if not self._is_enabled(name):
            return None
        loader = (lambda pd=pdir, en=entry: _load_class_from_dir(pd, en))
        spec = PluginSpec(
            name=name,
            source="dir",
            loader=loader,
            version=p.get("version", ""),
            description=p.get("description", ""),
            priority=p.get("priority", 50),
            depends_on=list(p.get("depends_on", [])),
        )
        if not self._load_and_validate(spec, read_meta=False):
            return None
        return spec

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
        """校验 depends_on 存在性 + 循环依赖检测。"""
        names = set(specs.keys())
        # 存在性剪枝
        pruned = set()
        for name, spec in specs.items():
            missing = [d for d in spec.depends_on if d not in names]
            if missing:
                logger.warning("plugin '%s' skipped: missing deps %s", name, missing)
                pruned.add(name)
        # 循环检测：在剩余插件里做 DFS 找环
        remaining = {n: s for n, s in specs.items() if n not in pruned}
        cyclic = self._find_cycles(remaining)
        for name in cyclic:
            logger.warning("plugin '%s' skipped: circular dependency", name)
        # 二次存在性闭包：循环移除后可能有 dangling 依赖（DFS 可能漏节点），级联剪枝
        bad = pruned | cyclic
        changed = True
        while changed:
            changed = False
            for name, spec in specs.items():
                if name in bad:
                    continue
                if any(d in bad for d in spec.depends_on):
                    logger.warning("plugin '%s' skipped: dependency removed", name)
                    bad.add(name)
                    changed = True
        return [s for n, s in specs.items() if n not in bad]

    def _find_cycles(self, specs: dict[str, PluginSpec]) -> set[str]:
        """DFS 检测参与循环的节点名集合。"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in specs}
        cyclic: set[str] = set()

        def visit(n, stack):
            color[n] = GRAY
            stack.append(n)
            for dep in specs[n].depends_on:
                if dep not in specs:
                    continue  # 已被存在性剪枝处理
                if color[dep] == GRAY:
                    # 找到环：stack 中从 dep 起的部分
                    idx = stack.index(dep)
                    cyclic.update(stack[idx:])
                elif color[dep] == WHITE:
                    visit(dep, stack)
            stack.pop()
            color[n] = BLACK

        for n in specs:
            if color[n] == WHITE:
                visit(n, [])
        return cyclic


def _load_class_from_dir(pdir: Path, entry: str) -> type:
    """从目录加载 module:Class，不污染 sys.path。"""
    module_name, _, class_name = entry.partition(":")
    if not class_name:
        raise ImportError(f"entry '{entry}' must be 'module:Class'")
    module_path = pdir / f"{module_name}.py"
    if not module_path.is_file():
        raise ImportError(f"module file not found: {module_path}")
    full = f"merco_plugin_{pdir.name}_{module_name}"
    spec = importlib.util.spec_from_file_location(full, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 可能抛异常
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ImportError(f"class {class_name} not found in {module_path}")
    return cls
