# 波2 设计：ModelProviderRegistry - 模型层插件化

> 日期: 2026-07-23
> 状态: 已通过 brainstorming（§1-§6 全部确认），待 writing-plans
> 路线: [plugin-dynamic-loading-plan.md](../../project-vision/references/plugin-dynamic-loading-plan.md) 波2 / [plugin-roadmap.md](../../project-vision/references/plugin-roadmap.md) P3
> 约束: 无历史债务（clean-slate，删除旧结构而非降级保留）

## 背景与目标

当前模型层是 **OpenAI 兼容硬编码**的：

- `merco/core/llm/_client.py` `LLMClient`（concrete，291-505）写死 `AsyncOpenAI`，`chat`/`chat_stream`/`_build_params`/`_parse_response`/`_parse_chunk` 全是 OpenAI 形状
- `merco/core/config.py` `PROVIDER_REGISTRY`（静态 dict，36-88）伪装成 registry 且带 `resolve()` 逻辑（104-117）——5 个 preset（openai/minimax/anthropic/openrouter/deepseek）即便 anthropic 也走 OpenAI 兼容通道
- `agent.py:318-330` 内联构造 `LLMClient`（读 8 字段 + 硬编码 `cooldown=0.3`）
- `agent.py:700-702` `switch_model` 只改 `self.llm.model` 字符串，跨 provider 断
- `agent.py:688` `from openai import APIStatusError` —— agent 核心循环耦合 OpenAI SDK
- `memory/strategy.py:96` `self.llm.chat` —— 另一个 LLMClient 消费者
- `_client.py:80-106` `_extract_usage` 已混入 Anthropic 字段（`cache_read_input_tokens`）—— OpenAI 客户端知道 Anthropic，债的气味

**目标**：`ModelProvider` ABC + `ModelRegistry`（唯一真相源）替换 OpenAI-only dispatch；一个真实 `AnthropicNativeProvider` 证明 ABC 非 OpenAI 形；第三方 provider 经波1插件发现注册；顺带修 `switch_model` 跨 provider + SubAgent 跨 provider。架构清爽，旧结构删尽。

## 决策摘要（brainstorming 结论）

| 取舍 | 选择 | 理由 |
|---|---|---|
| 范围 | C：ABC + Registry + 真实 Anthropic native | 真实非 OpenAI provider 证明抽象非 OpenAI 形；多模型 routing 延后（registry 留 `select()` 缝，零返工） |
| builtin 与第三方注册路径 | Approach 1（hybrid）：builtin 自 seed，第三方经波1发现 | builtin 急切可用（向导/测试随时 `ModelRegistry()`），第三方走已验证的 PluginDiscovery |
| `PROVIDER_REGISTRY` 去向 | 删除，数据进 `_BUILTIN_PROVIDERS`（声明式常量喂 registry） | 纯数据 + 运行时实例，非静态 dict + 逻辑（债） |
| `LLMClient` 去向 | 删除，传输逻辑迁入 `OpenAICompatibleProvider` + `thinking.py` | 不降级为 wrapper，clean-slate |
| `resolve()` 去向 | 删除，凭证解析归 `ModelRegistry.select()` | config 降回纯数据袋，registry 唯一真相源 |
| 错误模型 | merco 异常类型，provider 翻 SDK 错 | agent 不 import 任何 SDK；`error_ui.classify_error` 鸭子类型 `status_code` 已 SDK 无关 |
| streaming 旋钮 | 归组 `StreamingConfig` | 5 扁平字段 + `stream_options` 散落，归一处（schema 破一次） |

## §1 组件布局 + 删除清单

**`merco/core/llm/` 目标布局：**
```
merco/core/llm/
├── base.py               ModelProvider ABC + 归一化响应 dict 契约 + ModelProviderInfo
├── registry.py           ModelRegistry（唯一真相源）+ _BUILTIN_PROVIDERS 声明
├── openai_provider.py    OpenAICompatibleProvider - 吸收 LLMClient 全部传输逻辑
├── anthropic_provider.py AnthropicNativeProvider - 真实 Messages API
├── thinking.py           ThinkingExtractor + 3 策略 + think-tag 正则工具（从 _client.py 抽出）
├── response.py           ResponseProvider/Streaming/NonStreaming（从 agent.py 抽出）
├── errors.py             merco 异常类型（ProviderError 等）—— 重启用，非兼容 shim
├── error_ui.py           classify_error + 渲染 + llm_error（吸收旧 errors.py 的 wrapper）
└── __init__.py
```

**删除清单（clean-slate，每条都删尽，不留 adapter/fallback）：**

| 删除项 | 位置 | 去向 |
|---|---|---|
| `LLMClient` class + `_client.py` | `merco/core/llm/_client.py` | 传输逻辑迁 `openai_provider.py`；thinking 迁 `thinking.py`；`_clean_surrogates` 迁 `openai_provider.py`；`_extract_usage` 拆分（OpenAI 部分 → `openai_provider.py`） |
| `PROVIDER_REGISTRY` 静态 dict | `config.py:36-88` | 数据进 `registry.py::_BUILTIN_PROVIDERS` |
| `ProviderInfo` dataclass + `__getitem__` dict 兼容 | `config.py:15-33` | 并入 `ModelProviderInfo`（strict 超集，删 dict 兼容） |
| `ModelConfig.resolve()` | `config.py:104-117` | 凭证解析归 `ModelRegistry.select()` |
| `ModelConfig.stream_options` | `config.py:102` | `OpenAICompatibleProvider` 内部设 `include_usage`（传输关注点） |
| `MercoConfig` 5 扁平 streaming 字段 | `config.py:136-140` | 归组 `StreamingConfig`（嵌 MercoConfig） |
| `Agent._get_api_key` | `agent.py:1129-1137` | key_env 在 `ModelProviderInfo`，`select()` 读 |
| `agent.py` 内联 `LLMClient` 构造 + `cooldown=0.3` | `agent.py:318-330` | `ModelRegistry()` + 懒 `provider` property；`cooldown` → `ModelConfig.request_cooldown` |
| `agent.py` `from openai import APIStatusError` | `agent.py:688` | provider 抛 merco 错（带 `status_code`），agent catch merco 错 |
| `errors.py` 兼容 shim（re-export error_ui） | `llm/errors.py` | 重启用为 merco 异常类型宿主；`llm_error` 迁 `error_ui.py` |
| `MockLLMClient` | `tests/conftest.py:100-120` | `MockModelProvider`（实现 ABC） |
| `ProgrammableLLMClient` | `tests/integration/core/programmable_mock.py` | `ProgrammableModelProvider`（同 DSL，实现 ABC） |
| `agent.llm` 属性 + 全部 `.llm.` 引用 | `agent.py` / `memory/strategy.py` / ~40 测试文件 | `agent.provider`（settable property） |

**保留（非债）：** `error_ui.classify_error`（鸭子类型 `status_code`，已 SDK 无关）、`ThinkingExtractor` 策略链（OpenAI-compatible 私有）、`RecoveryContext.switch_model` 标志位（波2 启用它）、`error_ui` 渲染函数群。

## §2 ModelProvider ABC + 归一化契约 + ModelRegistry

**`ModelProvider` ABC**（`base.py`，纯传输，实例持连接+采样配置）：
```python
class ModelProvider(ABC):
    name: str
    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   tool_choice=None) -> dict: ...
    @abstractmethod
    def chat_stream(self, messages, tools=None, tool_choice=None) -> AsyncIterator[dict]: ...
```
- 实例构造持 `api_key/base_url/model/temperature/max_tokens/request_cooldown/extra_params/headers`（吸收 `LLMClient.__init__` 字段）。`chat`/`chat_stream` 只收 per-request 参数（messages/tools/tool_choice）。
- **归一化响应 dict 契约**（`chat` 返回 / `chat_stream` 末 chunk）：
  `{role, content, reasoning, finish_reason, usage{prompt,completion,total,cached?}, tool_calls[{id,type,function{name,arguments}}]}`
  正式化 `_parse_response`/`_parse_chunk` 已产出的形状为 ABC 契约；`MockModelProvider`/`ProgrammableModelProvider` 实现它即可静态校验。
  > 注（实现订正）：实际实现的内部契约是**扁平** `tool_calls[{id,name,arguments,index?}]`（`arguments` 非流式为 dict、流式为 JSON 字符串），非 OpenAI 外层 nested 形状；`_dispatch_tool_calls` 存入 context 时才重新 nested 化。`base.py` docstring 以实现为准。

**`ModelProviderInfo`**（dataclass，替代 `ProviderInfo`，strict 超集）：
```python
@dataclass
class ModelProviderInfo:
    name: str                       # id: "openai"/"minimax"/"anthropic"
    provider_class: type[ModelProvider]
    display_name: str = ""          # 向导显示名: "OpenAI"（吸收 ProviderInfo.name）
    base_url: str = ""
    key_env: str = ""               # provider 自知 key env（_get_api_key 删除后归这）
    key_help: str = ""              # 获取 key 的链接（向导用）
    default_model: str = ""
    models: list[str] = field(default_factory=list)
    description: str = ""
```

**`ModelRegistry`**（`registry.py`，唯一真相源）：
```python
class ModelRegistry:
    def __init__(self): self._providers = {p.name: p for p in _BUILTIN_PROVIDERS}
    def register(self, info: ModelProviderInfo) -> None
    def get(self, name: str) -> ModelProviderInfo
    def list(self) -> list[ModelProviderInfo]            # setup 向导用
    def select(self, model_config: ModelConfig) -> ModelProvider:
        info = self.get(model_config.provider)
        api_key = model_config.api_key or os.environ.get(info.key_env, "")
        base_url = model_config.base_url or info.base_url
        return info.provider_class(api_key=api_key, base_url=base_url,
            model=model_config.model, temperature=model_config.temperature,
            max_tokens=model_config.max_tokens, cooldown=model_config.request_cooldown,
            extra_params=model_config.extra_params, headers=model_config.headers)
```

**`_BUILTIN_PROVIDERS`**（`registry.py` 模块常量，声明式数据喂 registry）：
```python
_BUILTIN_PROVIDERS = [
    ModelProviderInfo("openai",     OpenAICompatibleProvider, "OpenAI",
        "https://api.openai.com/v1", "OPENAI_API_KEY",
        "https://platform.openai.com/api-keys", "gpt-4o",
        ["gpt-4o","gpt-4o-mini","gpt-4-turbo","o3-mini","o1"], "最通用的平台"),
    ModelProviderInfo("minimax",    OpenAICompatibleProvider, "MiniMax",
        "https://api.minimaxi.com/v1", "MINIMAX_API_KEY",
        "https://platform.minimaxi.com/user-center/basic-information", "MiniMax-M2.7",
        ["MiniMax-M2.7","MiniMax-Text-01","abab7-chat"], "国产平台"),
    ModelProviderInfo("anthropic",  AnthropicNativeProvider, "Anthropic",
        "https://api.anthropic.com", "ANTHROPIC_API_KEY",
        "https://console.anthropic.com/settings/keys", "claude-sonnet-4-20250514",
        ["claude-sonnet-4-20250514","claude-3-5-haiku-20241022","claude-3-opus-20240229"], "Claude 系列"),
    ModelProviderInfo("openrouter", OpenAICompatibleProvider, "OpenRouter",
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
        "https://openrouter.ai/keys", "anthropic/claude-sonnet-4", [], "模型聚合平台"),
    ModelProviderInfo("deepseek",   OpenAICompatibleProvider, "DeepSeek",
        "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
        "https://platform.deepseek.com/api_keys", "deepseek-chat",
        ["deepseek-chat","deepseek-reasoner"], "国产平台"),
]
```

## §3 Builtin providers + thinking.py 抽出

**`OpenAICompatibleProvider`**（`openai_provider.py`，吸收 `LLMClient` 全部传输逻辑）：
- 构造持连接+采样配置 + `ThinkingExtractor`（`make_thinking_extractor(model)` 选策略）。
- `chat()` → `client.chat.completions.create(stream=False)` → `_parse_response()` → 归一化 dict。
- `chat_stream()` → `create(stream=True)`（内部设 `stream_options={"include_usage": True}`）→ 逐 chunk `_parse_chunk()` → yield 归一化 chunk。
- `_build_params/_parse_response/_parse_chunk/_normalize_tool_calls` + OpenAI 部分 `_extract_usage` + `_clean_surrogates` 原样迁入。`AsyncOpenAI` 延迟 import + httpx timeout + `max_retries=0` 保留。
- 覆盖 openai/minimax/openrouter/deepseek（同一 class，不同 `ModelProviderInfo` 连接元数据）。

**`thinking.py`**（从 `_client.py` 抽出，仅 OpenAI-compatible 用）：
- 迁入：`THINK_TAG_PAIRS` + `_build_think_block_re` + `_strip_think_tags` + `_clean_content` + `ThinkingStrategy` ABC + `DirectFieldStrategy`/`ModelExtraStrategy`/`ThinkTagStrategy` + `ThinkingExtractor`（`register()` 保留）。
- 新增 `make_thinking_extractor(model) -> ThinkingExtractor` 工厂：deepseek 系 → ThinkTag，o 系 → ModelExtra，其余 → DirectField。

**`AnthropicNativeProvider`**（`anthropic_provider.py`，真实 Messages API，证明 ABC 非 OpenAI 形）：
- `AsyncAnthropic` 延迟 import（**新增 `anthropic` 依赖**到 `pyproject.toml`）。
- `_translate_tools`：OpenAI 函数工具 `{type:"function",function:{name,description,parameters}}` → Anthropic `{name,description,input_schema:parameters}`（传输层负责自家 wire 格式）。
- `_translate_messages`：`system` role → 顶层 `system` 参数；assistant `tool_calls` → `tool_use` block；`tool` role → `tool_result` block。
- `chat()` → `messages.create()` → 解析 `content` blocks（`text`/`thinking`/`tool_use`）→ 归一化 dict；`reasoning` 取自 `thinking` block（原生，不走 thinking.py）。
- `chat_stream()` → `messages.stream()` 上下文管理器 → `text_delta`/`thinking_delta`/`input_json_delta` → yield 归一化 chunk。
- `stop_reason` → `finish_reason` 映射（`end_turn`→`stop`，`tool_use`→`tool_calls`）。
- usage：`input_tokens`/`output_tokens` → `prompt_tokens`/`completion_tokens`；`cache_read_input_tokens` → `cached_tokens`。

**契约归属：** `reasoning` 字段是 ABC 契约；每 provider 各自填（OpenAI-compatible 走 thinking.py，Anthropic 读原生 block）。thinking.py 不假装通用，它是 OpenAI-compatible 私有提取器。

## §4 Config 解耦 + 生命周期

**`ModelConfig` = 纯数据袋：**
- `resolve()` 删除；`stream_options` 字段删除。
- 剩余：`provider/model/api_key/base_url/temperature/max_tokens/extra_params/headers`。
- **新增 `request_cooldown: float = 0.3`**（吸收 agent.py 硬编码 `cooldown=0.3`，保行为，无 magic number）。
- **新增 `fallbacks: list[ModelConfig] = field(default_factory=list)`**（驱动 `ModelFallbackRecovery`，见 §5）。

**`StreamingConfig` 归组**（嵌 MercoConfig，替 5 扁平字段）：
```python
@dataclass
class StreamingConfig:
    enabled: bool = False            # 原 MercoConfig.streaming（默认 False 保行为）
    think: bool = True               # 原 stream_thinking
    content: bool = True             # 原 stream_content
    think_transient: bool = False    # 原 stream_thinking_transient
    render_interval: float = 0.05    # 原 stream_render_interval（修 0.3/0.05 不一致）
```
- `MercoConfig.streaming: StreamingConfig`。配置文件 schema 变 `streaming: true` → `streaming: {enabled: true}`（一次性，无债）。
- `_to_dict`/`_from_dict` 同步改；`MercoConfig.load()` 不再调 `cfg.model.resolve()`（168 行删除）。

**`_BUILTIN_PROVIDERS` = registry.py 模块常量**（声明式数据，非可变静态 registry）：
- `ModelRegistry.__init__` 从它 seed，随时 `ModelRegistry()` 即得 builtin 全集。
- 区别：`PROVIDER_REGISTRY` 是伪装成 registry 的静态 dict 且带 resolve 逻辑（债）；`_BUILTIN_PROVIDERS` 是喂给 registry 的声明式 spec（类比 `MemoryBackendRegistry` 认 `JSONBackend` 为已知 builtin）。

**生命周期：**
- `Agent.__init__`：`self.model_registry = ModelRegistry()`（自 seed builtin）。
- `PluginContext.model_registry = self.model_registry`（第 21 扩展点）+ `register_model_provider(info)` 便捷方法。
- 第三方 provider 在 `activate_all` 阶段经 `ctx.register_model_provider(info)` 注册。
- setup 向导读 `ModelRegistry().list()`（builtin 全集）。

## §5 Agent rewiring（集成层）

**1. LLMClient 内联构造删除**（agent.py:318-330）：
- `self.model_registry = ModelRegistry()` + 懒 `provider` property。`self.llm` 属性删除。

**2. 懒 + 可设置 `provider` property（命名避撞）：**
- agent.py:372-375 原 `self._provider`（ResponseProvider 槽）**重命名 `self._response_provider`**，腾出 `provider` 给 ModelProvider。
- `self._model_provider: ModelProvider | None`（缓存）。
```python
@property
def provider(self) -> ModelProvider:
    if self._model_provider is None:
        self._model_provider = self.model_registry.select(self.config.model)
    return self._model_provider

@provider.setter
def provider(self, value: ModelProvider) -> None:
    self._model_provider = value
```
- 懒：第三方 provider 在 `activate_all`（post-`__init__`）注册，`__init__` 阶段 select 会失败；懒到首次 chat（boot 后）。
- **可设置**：支撑测试 `agent.provider = MockModelProvider(...)`（镜像现有 `agent.llm = MockLLMClient(...)` 模式）。

**3. switch_model 修复**（agent.py:700-702 只改字符串，跨 provider 断）：
- `RecoveryContext.switch_model: str` → `ModelConfig`（provider+model 全 spec）。
- `ModelFallbackRecovery` 升级：`__init__(fallbacks: list[ModelConfig])` + 内部 cursor；`attempt()` 设 `ctx.switch_model = fallbacks[cursor]`，cursor++。
- agent handler（700-702）：`self.config.model = ctx.switch_model; self._model_provider = None` → 下次访问 `provider` property re-select，`select()` 重解凭证（新 provider 的 key_env/base_url）。跨 provider fallback 通。
- `ModelFallbackRecovery` 接入 recovery 链（agent.py:387-389，当前只接 Wait/ContextCompress），fallbacks 来自 `config.model.fallbacks`（空则 no-op，安全）。

**4. SubAgent 修复**（subagent.py:64-69 改 provider/model 不 resolve，跨 provider 半断）：
- SubAgent 覆写 `config.model.provider/model`；`resolve()` 已删，懒 `provider` property 首次 chat 时 re-select + 重解凭证。跨 provider SubAgent 通（修复是懒选择的自然结果，零额外代码）。

**5. ResponseProvider 抽出**（agent.py:108-303，ABC + NonStreaming + Streaming ~175 行 Rich Live/Panel/cancel）：
- 迁入 `core/llm/response.py`。**保留 `get_response(agent, messages, tools)` 签名**（它用 `agent.config`/`agent.context`/`agent.session`/`agent._render_reasoning`，是 agent 编排器，非纯渲染）。
- 唯一改动：`agent.llm.chat`/`agent.llm.chat_stream` → `agent.provider.chat`/`agent.provider.chat_stream`（121/182 行）。provider 切换由 `agent.provider` property 处理（switch 后 re-resolve）。
- mode 选择（streaming/non-streaming）仍按 `config.streaming.enabled` 在 `__init__` 定（372-375，`self._response_provider`）。
- StreamingProvider 内部 `_content_update_interval=0.3`/`refresh_per_second=4`/`sleep(0.5)` 保留为 response.py 内部渲染默认（非用户配置）。

**6. 调用点迁移（生产）：**
- `agent.py:644` `self.llm.chat` / `agent.py:1010` `self.llm.chat` → `self.provider.chat`。
- `memory/strategy.py:65-69,96` `SessionEndExtractStrategy(pipeline, llm)` / `self.llm.chat` → `(pipeline, provider)` / `self.provider.chat`；构造方传 `agent.provider`。
- `agent.py:688` `from openai import APIStatusError` 删除；`isinstance(e, APIStatusError)` → `isinstance(e, ProviderError)`（merco 类型，见 §6）。

**7. 测试调用点：** `agent.llm` 全部 → `agent.provider`（~40 文件，见 §6）。

## §6 插件复用 + 错误处理 + 测试

**1. 插件发现复用（波1，无新机制）：**
- 第三方 provider 经波1 `PluginDiscovery`（entry_points + dir-scan plugin.toml）加载。插件 `activate(ctx)` 调 `ctx.register_model_provider(ModelProviderInfo(...))`：
```python
class GeminiPlugin(Plugin):
    def activate(self, ctx):
        ctx.register_model_provider(ModelProviderInfo(
            name="gemini", provider_class=GeminiProvider,
            display_name="Gemini", base_url=..., key_env="GEMINI_API_KEY", ...))
```
- provider class 由插件自带（插件包内），merco 不认 SDK。`registry.select` 遇 `"gemini"` 命中插件注册项。

**2. 错误处理（SDK 知识封在 provider 内）：**
- `errors.py` **重启用**为 merco 异常类型宿主：`ProviderError(Exception)`（带 `status_code` 属性）+ `RateLimitError`/`AuthError`/`ConnectionError`（子类）。
- 每 provider catch 自家 SDK 异常 → 翻成 merco 错：`OpenAICompatibleProvider` 翻 `openai.APIStatusError` 系（按 status_code 分子类），`AnthropicNativeProvider` 翻 `anthropic.APIStatusError` 系。
- `error_ui.classify_error` **不改**（鸭子类型 `status_code`，对 `ProviderError` 同样生效）。`llm_error` wrapper 从旧 `errors.py` 迁入 `error_ui.py`。
- agent catch `ProviderError`（merco 类型），不 import 任何 SDK。`tools/errors.py`/`self_healing.py` 注释更新（doc-only）。

**3. 测试（含大规模 mock 迁移）：**

*Unit：*
- `OpenAICompatibleProvider`（mock `AsyncOpenAI`，断言归一化 dict + cooldown + stream_options）。
- `AnthropicNativeProvider`（mock `AsyncAnthropic`，断言消息翻译/tool_use block/thinking block → 归一化）。
- `ModelRegistry`（register/get/list/select + 凭证解析优先级：config > env > info；未知 provider 抛错）。
- `thinking.py`（3 策略 + `make_thinking_extractor` 选 model + 跨 chunk think 标签状态机）。
- `response.py`（Streaming/NonStreaming 渲染 + cancel 保存 partial）。
- `errors.py`（`ProviderError` status_code 传播 + provider 翻译）。

*Mock 迁移（机械但量大）：*
- `MockLLMClient` → `MockModelProvider`（实现 `ModelProvider` ABC，保 `responses`/`calls` API）。
- `ProgrammableLLMClient` → `ProgrammableModelProvider`（保 Response DSL：`expect`/`expect_sequence`/`when`）。
- `tests/conftest.py:131` `monkeypatch merco.core.agent.LLMClient` → 删除（agent 不再构造 LLMClient）；fixture 默认 `agent.provider = MockModelProvider()` 或 patch `ModelRegistry.select`。
- ~40 测试文件 `agent.llm = MockLLMClient(...)` / `scenario.llm.expect(...)` → `agent.provider = MockModelProvider(...)` / `scenario.provider.expect(...)`。
- `tests/core/test_llm.py` + `tests/core/llm/test_client.py`（LLMClient unit）→ 重写为 `OpenAICompatibleProvider` + `thinking.py` + `anthropic_provider.py` unit。
- `tests/cli/test_repl_errors.py:326` `fake_agent.llm.chat_stream` → `fake_agent.provider.chat_stream`。

*Integration：*
- agent 启动 builtin 全注册（registry.list 含 5）。
- `switch_model` 跨 provider（openai→anthropic，凭证重解，`_model_provider` invalidate）。
- SubAgent 跨 provider（profile 指定 anthropic，子 agent re-select）。
- 插件注册的 provider 可 select（dir-scan 插件带 `register_model_provider`）。
- `ModelFallbackRecovery` fallback 链触发跨 provider 切换。

*Regression：* 现有 agent/stream/scenario/observer/memory/hook 测试全过（用 `MockModelProvider`/`ProgrammableModelProvider`）。

## 完整删除/迁移清单（无债校验表）

| 旧符号 | 位置 | 新去向 | 状态 |
|---|---|---|---|
| `LLMClient` | `_client.py:291` | 删；传输 → `OpenAICompatibleProvider` |  |
| `_client.py` 文件 | `core/llm/` | 删 |  |
| `PROVIDER_REGISTRY` | `config.py:36-88` | 删；数据 → `_BUILTIN_PROVIDERS` |  |
| `ProviderInfo` + `__getitem__` | `config.py:15-33` | 删；并入 `ModelProviderInfo` |  |
| `ModelConfig.resolve()` | `config.py:104-117` | 删；归 `select()` |  |
| `ModelConfig.stream_options` | `config.py:102` | 删；归 provider |  |
| `MercoConfig.streaming` 等 5 字段 | `config.py:136-140` | 删；归 `StreamingConfig` |  |
| `MercoConfig.load` 调 resolve | `config.py:168` | 删 |  |
| `Agent._get_api_key` | `agent.py:1129-1137` | 删 |  |
| agent 内联 `LLMClient` + `cooldown=0.3` | `agent.py:318-330` | 删；registry + 懒 property + `request_cooldown` |  |
| `agent.py` `from openai import APIStatusError` | `agent.py:688` | 删；catch `ProviderError` |  |
| `self._provider`（ResponseProvider 槽） | `agent.py:372-375` | 重命名 `_response_provider` |  |
| `agent.llm` 属性 | `agent.py` | 删；`agent.provider` property |  |
| `self.llm.chat/chat_stream/model` | `agent.py:121,182,644,702,1010` | `self.provider.chat/...` |  |
| `RecoveryContext.switch_model: str` | `pipeline.py` | `ModelConfig` |  |
| `ModelFallbackRecovery(fallback_model: str)` | `recovery/model_fallback.py` | `(fallbacks: list[ModelConfig])` + cursor + 接入链 |  |
| `SessionEndExtractStrategy(pipeline, llm)` | `memory/strategy.py:65-69,96` | `(pipeline, provider)` + `self.provider.chat` |  |
| `errors.py` 兼容 shim | `llm/errors.py` | 重启用为异常类型宿主；`llm_error` → `error_ui` |  |
| `from ...errors import llm_error` / `errors as errors_mod` | `agent.py:686,704`、`test_self_healing.py:88,94`、`test_recovery_wait.py:159,166,173` | `from ...error_ui import llm_error`；`errors_mod` 改用 `error_ui`/`ProviderError` |  |
| setup 向导 `PROVIDER_REGISTRY`/`ProviderInfo` | `setup.py:19,32,47,78,80,86,93,117,146,161` | `ModelRegistry().list()`/`ModelProviderInfo` |  |
| `MockLLMClient` | `conftest.py:100-120` | `MockModelProvider` |  |
| `ProgrammableLLMClient` | `programmable_mock.py` | `ProgrammableModelProvider` |  |
| `core/__init__.py` 导出 `LLMClient` | `core/__init__.py:8,19` | 导出 `ModelProvider`/`ModelRegistry` |  |
| `llm/__init__.py` 导出 `LLMClient` | `llm/__init__.py:3,5` | 导出新模块 |  |
| ~40 测试文件 `agent.llm`/`scenario.llm` | `tests/` | `agent.provider`/`scenario.provider` |  |

## 非目标 / 范围边界

- **多模型路由（routing）延后**：`ModelRegistry.select(config)` 是缝，未来 `ModelRouter` 策略插入零返工。波2 只做单 provider 选择。
- **不做** provider 健康检查/负载均衡/自动 failover 策略（fallback 是手动配置链，非智能路由）。
- **不做** OpenAI-compatible 之外的 native provider（如 Gemini native）——Anthropic native 足够证明抽象；其余走 OpenAI-compatible。
- **不破** 现有 agent 循环/工具调度/recovery/observability 行为（除 switch_model 变可用）。

## 风险

- **测试迁移量大**（~40 文件 + 2 个 mock DSL）：机械但易漏。writing-plans 需拆成多个独立 task，每 task 跑 `uv run pytest` 守底。
- **`anthropic` 新依赖**：增加安装体积；延迟 import 保证不装也能 import merco（仅用时报错）。
- **streaming schema 破坏**：现有 `merco.json` 的 `streaming: true` 需迁移。setup 向导 + 文档说明；提供一次性迁移（旧 bool 自动包成 `{enabled: ...}`）。
- **`StreamingConfig.render_interval` 默认值**（0.3→0.05）：thinking 面板更流畅，但渲染频率变化；可接受。
