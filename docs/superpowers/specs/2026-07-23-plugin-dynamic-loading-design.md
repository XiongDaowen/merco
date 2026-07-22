# 波1 设计：插件动态加载层 + 扩展点一致化

> 日期: 2026-07-23
> 状态: 已通过 brainstorming，待 writing-plans
> 路线: [plugin-dynamic-loading-plan.md](../../project-vision/references/plugin-dynamic-loading-plan.md) 波1

## 背景与目标

当前插件系统是**编译期硬编码**的：

- `agent.py:448-514` 显式 import + `register()` 7 个 builtin 插件
- 激活顺序硬编码于 `agent.py:534-545`（`_initialize_async_plugins`）
- `PluginManager.register()` 吃的是已 import 的实例，无发现机制
- 无 manifest 元数据 / 无依赖与优先级解析

**目标**：外部插件可动态安装（entry_points + 目录扫描），不动 agent.py 核心循环逻辑，7 个 builtin 运行时行为不变，架构清爽干净。

## 决策摘要（brainstorming 结论）

| 取舍 | 选择 | 理由 |
|---|---|---|
| builtin 与 discovery 关系 | A：builtin 也走 entry_points | 单一代码路径，agent.py 零硬编码 import |
| 目录扫描 manifest | A：plugin.toml 显式 manifest | 与 entry_points 对称、无歧义、元数据前置可读 |
| discover() 位置 | B：独立 PluginDiscovery 类 | SRP，"找插件"与"跑插件"分离，独立可测 |
| spec 加载 + boot 约束 | 方案1：lazy spec + 两阶段 boot | 行为不变（满足约束）+ 数据驱动 |

## §1 架构总览

**新增/改动的组件（每个单一职责）：**

| 组件 | 位置 | 职责 |
|---|---|---|
| `PluginSpec`（新增 dataclass） | `merco/plugins/base.py` | 承载已发现的元数据 + 懒加载 loader。discovery 产出、manager 消费 |
| `PluginDiscovery`（新增类） | `merco/plugins/discovery.py`（新文件） | 从 entry_points + 目录扫描发现 specs，解析 plugin.toml，去重，过滤 disabled。只负责"找" |
| `PluginManager`（扩展） | `merco/plugins/manager.py` | 加 `register_all(specs)`；`activate_all()` 改为拓扑+priority 排序；加 `activate_boot()`。只负责"跑" |
| `Plugin`（扩展） | `merco/plugins/base.py` | 加 `priority` + `depends_on` 类属性 |
| `PluginContext`（扩展） | `merco/plugins/base.py` | 暴露 `security_pipeline` + 4 个便捷方法 |
| `agent.py`（重写装配段） | `merco/core/agent.py:445-545` | 删 7 个硬编码 import/register，改走 discovery |

**数据流：**
```
Agent.__init__:
  构建 ctx（含 security_pipeline）
  plugin_manager = PluginManager(ctx)
  specs = PluginDiscovery(config).discover()   # entry_points + 目录扫描
  plugin_manager.register_all(specs)            # 存 spec（懒实例化）
Agent.create -> _initialize_async_plugins:
  await activate_boot()                         # priority≥100（observability）
  self.observer = ctx.observer; _restore_context()
  await activate_all()                          # 余下，拓扑+priority 排序激活
```

**隔离性：** Discovery 只产 spec 不碰 ctx；Manager 只跑生命周期不扫描；Spec 是两者间的纯数据契约。三者可独立单测。agent.py 装配段从 ~70 行硬编码收缩到 ~8 行。

## §2 元数据契约

**Plugin 类属性（扩展现有）：**
```python
class Plugin(ABC):
    name: str = ""
    version: str = ""
    description: str = ""
    priority: int = 50           # 新增，越大越早激活
    depends_on: list[str] = []   # 新增，必须先激活的插件名
```

builtin priority 赋值（保当前顺序）：`observability=100`（boot）、`skills=60`、`mcp=50`、`subagent=40`、`web=30`、`scheduler=20`、`superpower=10`。`BOOT_PRIORITY = 100` 为常量。

**entry_points 声明（pyproject.toml，builtin 也走这条）：**
```toml
[project.entry-points."merco.plugins"]
observability = "merco.plugins.builtin.observability.plugin:ObservabilityPlugin"
skills = "merco.plugins.builtin.skills.plugin:SkillPlugin"
mcp = "merco.plugins.builtin.mcp.plugin:MCPPlugin"
subagent = "merco.plugins.builtin.subagent.plugin:SubAgentPlugin"
web = "merco.plugins.builtin.web.plugin:WebPlugin"
scheduler = "merco.plugins.builtin.scheduler.plugin:SchedulerPlugin"
superpower = "merco.plugins.builtin.superpower.plugin:SuperpowerPlugin"
```
- EP 名 = 插件运行时名（约定，加载后校验一致）
- priority/depends_on 从类属性读（EP 不带这些字段）

**plugin.toml 格式（目录扫描专用，等价于 pyproject 的 EP 声明）：**
```toml
[plugin]
name = "my-plugin"
version = "0.1.0"
description = "does X"
priority = 50
depends_on = []
entry = "main:MyPlugin"   # 本目录内 module:Class
```
- priority/depends_on 可省（默认 50/[]），其余必填
- 用 `importlib.util.spec_from_file_location` 按 `entry` 加载，**不污染 sys.path**
- name 必须与 `Plugin.name` 类属性一致（不一致 warn）

**PluginSpec dataclass（discovery -> manager 的纯数据契约）：**
```python
@dataclass
class PluginSpec:
    name: str
    entry: str                  # "module:Class"
    source: str                 # "entrypoint" | "dir"
    version: str = ""
    description: str = ""
    priority: int = 50
    depends_on: list[str] = field(default_factory=list)
    _cls: type | None = None    # 懒加载的类
    _dir: Path | None = None    # dir-scan 的目录上下文

    def load_cls(self) -> type[Plugin]: ...   # import+getattr，缓存到 _cls
    def instantiate(self) -> Plugin: ...      # load_cls()()
```

**discovery 解析规则：** entry_points 的 priority/depends_on 需 `load_cls` 读类属性；dir-scan 从 toml 直读。discover() 会对所有 **enabled** spec `load_cls` 以拿到完整排序元数据（类加载廉价，实例化才在 activate 时发生）。

**校验规则（fail-soft，不崩启动）：**
- name 非空、去重后唯一
- entry 可解析为 `Plugin` 子类
- `depends_on` 中的名字不在已发现集合 -> warn + 跳过该插件
- 循环依赖 -> 检测到 warn + 跳过涉及插件

## §3 Discovery 流程

**PluginDiscovery.discover() 流程：**
```
1. 收集 entry_points(group="merco.plugins")  -> PluginSpec(name=ep.name, entry, source="entrypoint")
2. 扫描 plugins_paths 下子目录               -> 有 plugin.toml 的产 PluginSpec(source="dir")
3. 去重：同名 dir-scan 覆盖 entry_points（本地 drop-in 可覆盖已安装，方便开发覆盖）
4. 过滤 disabled：config.plugins[name].enabled 默认 True；disabled 的在此步跳过，不 load_cls（代码不导入）
5. 对 enabled spec load_cls + 校验（§2 规则）；失败 warn + 跳过，不崩启动
6. 返回 list[PluginSpec]
```

**扫描路径（新增 config 字段，对齐 skills_paths 约定）：**
```python
# config.py 新增
plugins_paths: list = field(default_factory=lambda: ["./.merco/plugins", "~/.config/merco/plugins"])
```
- 与 `skills_paths`（`["./.merco/skills", "~/.config/merco/skills"]`）完全对称
- 路径不存在就跳过，不报错

**enabled 过滤（复用现有 config.plugins）：**
```python
def _is_enabled(self, name: str) -> bool:
    return self._config.plugins.get(name, {}).get("enabled", True)
```
- `config.plugins` 是现有字段（`activate_all` 已在用 `getattr(ctx.config, "plugins", {})`）
- disabled 插件在第 4 步被剔除，**永不导入**

**dir-scan 加载隔离：**
- 用 `importlib.util.spec_from_file_location(dir/"main.py")` 加载模块，`getattr` 取类
- 不动 `sys.path`，插件之间命名空间隔离

**错误处理（全部 fail-soft）：**

| 情况 | 处理 |
|---|---|
| 目录无 plugin.toml | 静默跳过（不是插件） |
| plugin.toml 解析失败/缺必填字段 | warn + 跳过该目录 |
| entry point / 模块 import 失败 | warn + 跳过该 spec |
| depends_on 引用不存在的插件 | warn + 跳过该 spec |
| 循环依赖 | 检测 warn + 跳过涉及插件 |

**关键性质：** discovery 完全无副作用（不实例化、不激活、不碰 ctx），只产 spec 列表。可纯单测。

## §4 激活排序 + 两阶段 boot

**PluginManager 扩展（双存储，低改动）：**
- `_plugins: dict[name, Plugin]`（现有，实例缓存）+ `_specs: dict[name, PluginSpec]`（新增，discovery 元数据）
- `register(plugin)` 不变（存实例到 `_plugins`，现有测试全绿）
- `register_all(specs)` 新增（存到 `_specs`）
- `activate(name)`：`_plugins` 有就用，否则从 `_specs` 懒实例化并入 `_plugins`

**排序算法 `_resolve_order(names, boot_only) -> list[str]`：**
```
1. 输入：_plugins 与 _specs 键的并集（名字列表）
2. boot_only=True 时，先筛 priority >= BOOT_PRIORITY(100)
3. 剪枝：depends_on 中有不在池内的名字 -> warn + 移除该插件
4. Kahn 拓扑排序（depends_on）；同一拓扑层内按 priority 降序、name 升序
5. 剩余未解析节点 = 循环依赖 -> warn + 跳过
```
返回有序名字列表；`activate_boot`/`activate_all` 据此逐个 `activate(name)`。手动注册的插件（仅在 `_plugins`、无 spec）用默认 priority 50 / depends_on [] 参与排序。确定性：拓扑层 + priority + name 三级排序，结果稳定可复现。

**两阶段 boot：**
```python
async def activate_boot(self): ...   # 激活 priority>=100
async def activate_all(self): ...    # 全部，topo+priority 序；对已激活的 boot 插件幂等
```

**agent.py 装配重写：**

`__init__`（原 445-514，~70 行 -> ~8 行）：
```python
from merco.plugins.base import PluginContext
from merco.plugins.manager import PluginManager
from merco.plugins.discovery import PluginDiscovery

self._plugin_ctx = PluginContext(..., security_pipeline=self._security_pipeline)  # 暴露 security
self._plugin_ctx.agent = self
self.plugin_manager = PluginManager(self._plugin_ctx)
self.plugin_manager.register_all(PluginDiscovery(config).discover())  # 取代 7 个 import+register
```

`_initialize_async_plugins`（原 534-545）：
```python
async def _initialize_async_plugins(self) -> None:
    await self.plugin_manager.activate_boot()        # observability（priority=100）
    self.observer = self._plugin_ctx.observer
    assert self.observer is not None
    self._restore_context()
    await self.plugin_manager.activate_all()         # 余下，topo+priority 序；boot 插件幂等跳过
```

**语义完全保留：** observability 先激活 -> readback observer -> restore -> 余下激活。**不硬编码任何插件名**，boot 由 priority 驱动。

**核实纠偏：** agent.py 实际注册 **7** 个 builtin（observability/skills/mcp/subagent/web/scheduler/superpower）。architecture.md 画的"8 个"含一个不存在的 `PermissionPolicyPlugin`--security 实际由 `agent.__init__` 的 `_security_pipeline`/ToolGuard 直接装配，不是插件。本次走 7 个 entry_points，security 仅暴露到 ctx（§5），不做成插件（避免行为变更）。

## §5 PluginContext 便捷方法

**PluginContext.__init__ 加参数：**
```python
security_pipeline: "PolicyPipeline" = None,   # 新增
...
self.security_pipeline = security_pipeline
```
agent.py 装配时传 `security_pipeline=self._security_pipeline`。

**4 个便捷方法：**
```python
def register_agent_profile(self, profile) -> None:
    self.agent_profiles.register(profile)

def register_loop_policy(self, policy) -> None:
    self.loop_policies.register(policy)

def add_memory_backend(self, backend) -> None:
    self.memory_backends.register(backend)

def add_security_policy(self, policy: "PermissionPolicy") -> None:
    if self.security_pipeline is None:
        raise RuntimeError("security_pipeline not available")
    self.security_pipeline.use(policy)
```
底层 API 均已核实存在（`agent_profiles.register` / `loop_policies.register` / `memory_backends.register` / `PolicyPipeline.use`）。

## §6 错误处理（汇总）

| 边界 | 策略 | 已述于 |
|---|---|---|
| discovery：坏 manifest / import 失败 / 缺依赖 / 循环 | warn + 跳过，不崩启动 | §2 §3 |
| activation：插件 `activate()` 抛异常 | 现有逻辑保留：warn + emit `plugin.error` + 不标记 active | 现有 |
| **新增：dep-active 检查** | `_activate_spec` 前检查 `depends_on` 是否都在 `_active`；有未激活 dep -> warn + 跳过该插件。与 discovery 的存在性检查互补：discovery 保证 dep **存在**，dep-active 保证 dep **激活成功** | §6 |

**原则：** 任何插件失败都不崩启动；Observer 计 `plugin.error`；失败插件不进 `_active`，其依赖被 dep-active 检查级联跳过。discovery 无副作用、activation fail-soft，两层独立。

## §7 测试（TDD）

| 文件 | 覆盖 |
|---|---|
| `test_discovery.py`（新） | entry_points 发现 / dir-scan 建临时目录+plugin.toml / dir 覆盖 entry_point / disabled 不加载 / 坏 toml warn+跳过 / 缺依赖剪枝 / 循环跳过 / 全失败不崩 |
| `test_spec.py`（新） | `PluginSpec.load_cls`/`instantiate` / 懒缓存 |
| `test_manager.py`（扩） | `register_all` / `_resolve_order` 拓扑+priority+name 确定性 / `activate_boot` 只激活 priority≥100 / `activate_all` 对 boot 幂等 / dep-active 级联跳过 / 循环跳过 |
| `test_plugin_base.py`（扩） | 4 个便捷方法 / security_pipeline 暴露 |
| 集成测试（扩） | 造假外部插件（entry_point 或 dir）经 discover->register_all->activate 端到端注册 tool/profile/policy；**回归**：7 个 builtin 仍按序激活，observer 在 restore 前就绪 |

**回归关键点：** builtin 激活顺序 + observer-before-restore 必须有测试钉住，否则"行为不变"无保障。

## 范围边界

- 本波只做动态加载 + 便捷方法，不动 ModelProvider/Gateway（波2/3）
- security 不做成插件（仅暴露 pipeline 到 ctx）
- 不动 agent.py 核心循环逻辑（仅装配段 `__init__` 445-514 + `_initialize_async_plugins` 534-545）
- 不重构 ObservabilityPlugin 的 observer 创建逻辑（保留 readback 语义）

## 验收标准

- 外部插件（entry_points 或 dir+plugin.toml）能被发现、按序激活、注册 tool/profile/policy
- agent.py 不再硬编码任何插件 import/register
- 7 个 builtin 激活顺序与现状一致，observer 在 restore 前就绪（回归测试钉住）
- disabled 插件代码不导入
- 任何插件失败不崩启动
- discovery / manager / spec 各自可独立单测
