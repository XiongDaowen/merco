# merco LoopPolicy 设计

> 最后更新: 2026-06-27
> Phase 2.1: Agent Loop 开放扩展点

## 目标

把 Agent Loop 的退出条件从硬编码逻辑改为可拔插的 LoopPolicy。默认策略完全复刻当前行为，插件可注册自定义 loop 策略（如反思、自我检查、继续迭代）。

## 现状

`Agent._agent_loop` 当前逻辑中：

- 有 tool_calls → 执行工具并继续 loop
- 无 tool_calls → 返回 content，退出
- max_tool_calls 达到上限 → wrap up

退出条件硬编码在 Agent Loop 内，插件无法影响。

## 设计

### 数据模型

```python
@dataclass
class LoopState:
    """Loop 当前状态"""
    iteration: int
    tool_calls_count: int
    max_tool_calls: int
    has_tool_calls: bool
    finish_reason: str | None = None


@dataclass
class LoopDecision:
    """Loop 策略决策"""
    action: str  # "continue" | "exit"
    reason: str = ""
```

### LoopPolicy ABC

```python
class LoopPolicy(ABC):
    """Agent Loop 策略基类"""
    name: str = ""

    @abstractmethod
    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        """根据 LLM response 和当前 state 决定继续或退出"""
        ...
```

### DefaultLoopPolicy

```python
class DefaultLoopPolicy(LoopPolicy):
    """默认策略：完全复刻当前行为"""
    name = "default"

    async def decide(self, response: dict, state: LoopState) -> LoopDecision:
        if state.has_tool_calls:
            return LoopDecision(action="continue", reason="tool_calls present")
        return LoopDecision(action="exit", reason="no tool_calls")
```

### LoopPolicyRegistry

```python
class LoopPolicyRegistry:
    """LoopPolicy 注册表"""

    def __init__(self):
        self._policies: dict[str, LoopPolicy] = {}
        self._active: str = "default"

    def register(self, policy: LoopPolicy) -> None:
        self._policies[policy.name] = policy

    def get(self, name: str) -> LoopPolicy | None:
        return self._policies.get(name)

    def set_active(self, name: str) -> None:
        if name not in self._policies:
            raise KeyError(name)
        self._active = name

    @property
    def active(self) -> LoopPolicy:
        return self._policies[self._active]
```

## Agent 集成

### 装配

```python
# Agent.__init__
from merco.core.loop_policy import LoopPolicyRegistry, DefaultLoopPolicy

self.loop_policies = LoopPolicyRegistry()
self.loop_policies.register(DefaultLoopPolicy())
self.loop_policies.set_active("default")
self._plugin_ctx.loop_policies = self.loop_policies
```

### _agent_loop 改动

```python
state = LoopState(
    iteration=iteration,
    tool_calls_count=self._tool_calls_count,
    max_tool_calls=self._max_tool_calls,
    has_tool_calls=bool(api_tool_calls),
    finish_reason=response.get("finish_reason"),
)
decision = await self.loop_policies.active.decide(response, state)

if decision.action == "exit":
    return content
# continue 保持现有执行工具逻辑
```

## PluginContext 扩展

```python
class PluginContext:
    loop_policies: LoopPolicyRegistry
```

插件示例：

```python
class ReflectionLoopPlugin(Plugin):
    async def activate(self, ctx):
        ctx.loop_policies.register(ReflectionLoopPolicy())
        ctx.loop_policies.set_active("reflection")
```

## 风险控制

1. 默认策略行为等价于当前逻辑
2. max_tool_calls 保留硬上限，防止无限循环
3. 未注册策略不能 set_active
4. 插件不启用自定义策略时无行为变化

## 文件结构

```
merco/core/loop_policy.py       # LoopState / LoopDecision / LoopPolicy / Registry / DefaultLoopPolicy
merco/core/agent.py             # 装配 + _agent_loop 调用 policy
merco/plugins/base.py           # PluginContext 新增 loop_policies
tests/core/test_loop_policy.py  # 单元测试
tests/integration/test_loop_policy.py # 行为等价集成测试
```

## 测试计划

| 测试 | 目标 |
|------|------|
| DefaultLoopPolicy 有 tool_calls → continue | 复刻当前行为 |
| DefaultLoopPolicy 无 tool_calls → exit | 复刻当前行为 |
| Registry register/get/set_active | 注册表行为 |
| Agent simple conversation 仍退出 | 行为不变 |
| Agent tool_call chain 仍继续 | 行为不变 |
| 自定义 policy 可注册并生效 | 插件扩展点验证 |

## 非目标

- 不实现 ReflectionLoopPolicy
- 不修改 max_tool_calls 逻辑
- 不引入 HookResult
- 不做 Command 对象模式
