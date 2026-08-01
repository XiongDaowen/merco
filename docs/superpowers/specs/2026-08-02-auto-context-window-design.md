# 自动上下文窗口（Auto Context Window）设计

> 日期：2026-08-02
> 分支：`feat/auto-context-window`
> 状态：设计定稿，待实现

## 1. 背景与目标

Merco 的上下文窗口大小 `MercoConfig.max_input_tokens` 是**固定值（默认 64000）**，不随模型变化。这导致：

- 用 200K 窗口的 Claude/GPT 模型只用到 64K，浪费 2/3 上下文。
- 用大窗口的 MiniMax（1M）模型浪费更多。
- 用 32K 窗口的模型会溢出（进度条显示超限，LLM 调用失败）。

**目标**：按当前模型自动确定上下文窗口大小，用户无需手动配置。默认开启，未知模型回退到现有 64000。

**参照**：OpenCode / Hermes 等工具的机制是"API 查询 + 表回退"混合——能通过 `GET /v1/models` 拿到 `context_length` 的就自动获取（OpenRouter / vLLM / LiteLLM proxy），取不到的（OpenAI / Anthropic API 不暴露 context_length）回退到维护的表。

## 2. 范围

**做**：

- `ModelProvider` ABC 增加 `async fetch_context_window() -> int | None` 虚方法（默认 None）。**插件 provider 子类可 override**（扩展路径 A）。
- `OpenAICompatibleProvider` 实现 `fetch_context_window()`：`GET {base_url}/models`，找当前模型，读 `context_length`。
- `ModelProviderInfo` 增加 `context_windows: dict[str, int]` 静态表字段。**插件 `register_model_provider` 时可携带**（扩展路径 B，无需写子类）。
- `ModelRegistry.get_context_window(provider, model) -> int | None`：查 `info.context_windows`。
- `MercoConfig.auto_context_window: bool = True`（默认开；用户可设 `false` 手动锁 `max_input_tokens`）。
- `Agent._maybe_auto_context_window()`（在 `_initialize_async_plugins` 的 `activate_all` 之后调用）：按 **provider.fetch_context_window() → registry.get_context_window() → config.max_input_tokens** 三级回退，设置 `config.max_input_tokens` + `context.max_tokens`。
- 内置 provider 填 `context_windows`（openai / anthropic / deepseek / minimax 已知模型）。
- MiniMax 插件注册 `context_windows`（M2.7 / M3 暂填 1M，用户可改）。

**不做（显式排除）**：

- 不做跨 provider 的统一模型目录 / 远程模型目录（Pi 那种）——超出范围。
- 不做按 token 价格 / 成本推断窗口。
- 不缓存 API 查询结果（每次启动查询一次，开销可接受；后续可加缓存）。
- 不改 `compression_threshold` / `max_tool_calls` 等其他配置。

## 3. 设计

### 3.1 查询方法（扩展路径 A：provider 子类 override）

`merco/core/llm/base.py`：

```python
class ModelProvider(ABC):
    name: str

    @abstractmethod
    async def chat(...): ...

    @abstractmethod
    def chat_stream(...): ...

    async def fetch_context_window(self) -> int | None:
        """按模型自动获取上下文窗口大小。返回 None 表示无法获取（走表/配置回退）。

        插件 provider 子类可 override 实现自定义查询（如特殊 API）。
        """
        return None
```

`merco/core/llm/openai_provider.py`（`OpenAICompatibleProvider`）：

```python
    async def fetch_context_window(self) -> int | None:
        """查询 OpenAI 兼容 /models 端点，读当前模型的 context_length。

        OpenRouter / vLLM / LiteLLM proxy 等返回 context_length；OpenAI 官方
        不返回 -> None，回退到表/配置。
        """
        try:
            resp = await self._client.get(
                f"{self.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            for m in data.get("data", []):
                if m.get("id") == self.model:
                    cl = m.get("context_length")
                    if isinstance(cl, int) and cl > 0:
                        return cl
                    break
            return None
        except Exception:
            return None
```

> 注：`OpenAICompatibleProvider` 的 HTTP 客户端依赖需确认——若用 openai SDK 则走 `self.client.models.list()`（不返回 context_length），需直接 `httpx`/`aiohttp` 裸请求。实现时按现有客户端模式选。

`AnthropicNativeProvider`：不实现（返回 None），走表回退（Anthropic 无公开 /models 端点）。

### 3.2 静态表（扩展路径 B：ModelProviderInfo.context_windows）

`merco/core/llm/base.py`：

```python
@dataclass
class ModelProviderInfo:
    ...
    models: list[str] = field(default_factory=list)
    context_windows: dict[str, int] = field(default_factory=dict)  # 模型名 -> 上下文窗口
    description: str = ""
```

`merco/core/llm/registry.py` 内置 provider 填表：

```python
ModelProviderInfo(
    name="openai",
    ...
    models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini", "o1"],
    context_windows={
        "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
        "o3-mini": 200000, "o1": 200000,
    },
)
# anthropic: claude-sonnet-4-20250514 / 3.5-sonnet / 3.5-haiku / 3-opus 均 200000
# deepseek: deepseek-chat / deepseek-reasoner 均 64000
# minimax: MiniMax-Text-01 1000000；M2.7/M3 待确认（暂 1000000，用户可改）
```

`ModelRegistry`：

```python
    def get_context_window(self, provider: str, model: str) -> int | None:
        info = self._providers.get(provider)
        if not info:
            return None
        return info.context_windows.get(model)
```

`merco/plugins/builtin/minimax/plugin.py`：注册 `context_windows`（覆盖内置 minimax 的 M2.7/M3 值，便于用户改一处）。

### 3.3 配置 + 应用点

`merco/core/config.py`：

```python
    max_input_tokens: int = 64000
    auto_context_window: bool = True  # 按模型自动确定上下文窗口
```

`_to_dict` / `_from_dict` 增加 `auto_context_window` 字段。

`merco/core/agent.py`：

```python
    async def _maybe_auto_context_window(self) -> None:
        """按模型自动设置上下文窗口。三级回退：provider 查询 -> 静态表 -> 配置值。

        插件扩展：provider 子类 override fetch_context_window()（动态），或
        register_model_provider 携带 context_windows（静态）。
        """
        if not getattr(self.config, "auto_context_window", True):
            return
        cw = None
        try:
            cw = await self.provider.fetch_context_window()
        except Exception:
            cw = None
        if not cw:
            cw = self.model_registry.get_context_window(self.config.model.provider, self.config.model.model)
        if cw and cw > 0:
            self.config.max_input_tokens = cw
            self.context.max_tokens = cw
            logger.debug("上下文窗口按模型设置: %s/%s -> %d", self.config.model.provider, self.config.model.model, cw)
```

`_initialize_async_plugins`（`activate_all` 之后、`_maybe_compress_on_restore` 之前）：

```python
        await self.plugin_manager.activate_all()
        await self._maybe_auto_context_window()
        await self._maybe_compress_on_restore()
```

> 顺序：先 auto context window（更新 max_tokens），再判断压缩（压缩阈值依赖 max_tokens）。provider 懒解析在 `self.provider` 首次访问时发生。

### 3.4 时序与上下文

- `_initialize_async_plugins` 在 `Agent.create()` 内、REPL 渲染 dashboard 前执行，所以进度条在启动时就显示正确的窗口大小。
- `ContextManager.max_tokens` 用新的 `max_input_tokens` 更新，压缩阈值（`max_input_tokens * compression_threshold`）自动跟随。

## 4. 插件扩展文档（写进设计，供实现参考）

```python
# 扩展路径 A：动态查询（provider 子类 override）
class MyProvider(OpenAICompatibleProvider):
    async def fetch_context_window(self) -> int | None:
        # 自定义 API 查询
        ...

# 扩展路径 B：静态表（无需写子类）
info = ModelProviderInfo(
    name="mymodel",
    provider_class=MyProvider,
    models=["my-model"],
    context_windows={"my-model": 200000},  # 携带静态表
)
ctx.register_model_provider(info)
```

## 5. 改动文件清单

| 文件 | 改动 |
|------|------|
| `merco/core/llm/base.py` | `ModelProvider` + `fetch_context_window` 虚方法；`ModelProviderInfo` + `context_windows` 字段 |
| `merco/core/llm/openai_provider.py` | `OpenAICompatibleProvider.fetch_context_window()` 实现（GET /models） |
| `merco/core/llm/registry.py` | 内置 provider 填 `context_windows`；`get_context_window()` |
| `merco/core/config.py` | `auto_context_window: bool = True` + 序列化 |
| `merco/core/agent.py` | `_maybe_auto_context_window()` + 在 `_initialize_async_plugins` 调用 |
| `merco/plugins/builtin/minimax/plugin.py` | 注册 `context_windows`（M2.7/M3 暂 1M） |
| `tests/` | provider fetch 测试、registry 表测试、config roundtrip、agent 应用测试 |

## 6. 测试策略

- **ModelProvider.fetch_context_window 默认 None**：ABC 默认返回 None。
- **OpenAICompatibleProvider.fetch_context_window**：mock HTTP（httpx/aiohttp）返回含 context_length 的 /models 响应 -> 返回正确值；无 context_length / 非 200 / 异常 -> None。
- **ModelProviderInfo.context_windows**：默认空 dict；可携带。
- **ModelRegistry.get_context_window**：已知 provider+model -> 值；未知 -> None。
- **Agent._maybe_auto_context_window**：auto 开 + provider 返回值 -> config/context.max_tokens 更新；provider None + 表有值 -> 用表；都 None -> 不变；auto 关 -> 不变。
- **config roundtrip**：auto_context_window 默认 True + 序列化往返。
- 运行方式：`uv run pytest`。

## 7. 向后兼容

- `auto_context_window` 默认 `True`，未知模型回退 `max_input_tokens`（64000），行为与现在一致。
- `fetch_context_window` 默认 None，现有 provider 不受影响（OpenAICompatible 增加实现是增强）。
- `context_windows` 默认空 dict，现有插件不受影响。
- 用户可 `auto_context_window: false` + 显式 `max_input_tokens` 手动锁。
