# Memory → Sessions 打通设计

> 最后更新: 2026-06-15

## 目标

让 Agent 能够在会话中**主动存记忆**（用户显式）和**自动抽记忆**（session 结束时 LLM 抽取），并在下次会话**召回注入 system prompt**。召回链路已经通了，本 spec 解决"存"和"什么时候存"。

## 现状

- `MemoryStore`（`merco/memory/store.py`）：JSON 文件持久化，API 完整（`save/load/list/search/delete`），但 `save()` 在 Agent loop 中**从未被调用**
- `HybridRecaller` + `FTS5Recaller` + `MemoryRecaller`：召回链路完整，`_build_system_prompt` 已注入
- `HookRegistry`：完整事件系统（`agent.start`/`agent.stop`/`session.create`/`session.destroy`/`message.send`/...）
- `Pipeline` 模式已在 `merco/core/pipeline.py` 成熟应用（`ResultPipeline`/`RecoveryPipeline`/`EmptyResponsePipeline`）

**空缺**：`MemoryStore.save()` 无触发点 → 记忆永远是空的 → 召回永远是空。

## 解决方案

### 架构总览

```
┌────────────────────────────────────────────────────────────┐
│  Agent 业务代码 (零感知)                                    │
│  • /remember <text>  →  emit("command.remember", text)    │
│  • session.destroy  →  emit("session.destroy", session_id) │
└────────────────────────────────────────────────────────────┘
                          ↓ events
┌────────────────────────────────────────────────────────────┐
│  HookRegistry (merco/hooks/registry.py)                    │
└────────────────────────────────────────────────────────────┘
        ↓ subscribe                  ↓ subscribe
┌──────────────────────┐    ┌──────────────────────────────┐
│ ExplicitRemember     │    │ SessionEndExtract             │
│ Strategy             │    │ Strategy (opt-in)             │
│ sync save            │    │ async LLM extract             │
└──────────────────────┘    └──────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  MemorySavePipeline (统一保存链)                            │
│  SourceEnricher → DedupProcessor → Store                   │
│  emit("memory.saved"|"memory.failed") on terminal          │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  MemoryStore (已有，不改)                                    │
└────────────────────────────────────────────────────────────┘
                          ↓ emit("memory.saved")
┌────────────────────────────────────────────────────────────┐
│  Observer (已有) — 订阅 memory.saved → /report 统计        │
└────────────────────────────────────────────────────────────┘
```

**核心约束**：
- Agent 业务代码不改 `MemoryStore.save()` 调用
- `MemoryStore` 自身不改
- 复用 `Pipeline` + `HookRegistry` 模式（团队熟悉）

### 1. 触发策略（MemorySaveStrategy）

**抽象**（`merco/memory/strategy.py`）：

```python
class MemorySaveStrategy(ABC):
    """监听事件，构造 SaveItem 喂给 Pipeline"""
    name: str = ""

    def __init__(self, pipeline: "MemorySavePipeline"):
        self.pipeline = pipeline

    @abstractmethod
    async def on_event(self, event: str, **kwargs) -> None: ...
```

**两个实现**：

| Strategy | 监听事件 | 来源 | 时机 |
|----------|---------|------|------|
| `ExplicitRememberStrategy` | `command.remember` | user | 同步，CLI 输入即存 |
| `SessionEndExtractStrategy` | `session.destroy` | extracted (LLM) | 异步，opt-in |

**LLM 抽取策略细节**（`SessionEndExtractStrategy`）：
- 触发条件：消息数 ≥ `memory_extract_min_messages`（默认 5）
- 调 LLM 一次，prompt 让其返回 1-3 条 insight（最多 `memory_extract_max_per_session`）
- 失败处理：网络/5xx → log warning + return（不阻塞 session.destroy）
- 输出解析：JSON 数组（每条 `{key, value, tags}`），解析失败丢弃整批
- 来源：`source="extracted"`，自动 tag 前缀 `[extracted]`

### 2. 保存链（MemorySavePipeline）

**文件**：`merco/memory/save_pipeline.py`

**入口**：

```python
class MemorySavePipeline:
    def __init__(self, store: MemoryStore, hooks: HookRegistry):
        self.store = store
        self.hooks = hooks
        self._processors: list[MemorySaveProcessor] = [
            SourceEnricher(),
            DedupProcessor(store),
        ]

    def use(self, processor) -> "MemorySavePipeline": ...

    async def save(self, item: SaveItem) -> bool:
        """True=写入成功，False=被 dedup skip 或失败"""
```

**SaveItem 数据结构**：

```python
@dataclass
class SaveItem:
    key: str
    value: str
    source: MemorySource  # Literal["user", "extracted", "system"]
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    metadata: dict = field(default_factory=dict)
```

**Processor 链**：

| Processor | 职责 | 失败处理 |
|-----------|------|---------|
| `SourceEnricher` | 自动补 `[source]` 前缀到 tags | 不失败 |
| `DedupProcessor` | 按 source 优先级 skip 已有 key | return None = skip |
| `SecretFilterProcessor`（预留） | 检测 API key / 密码 / 身份证号 | return None = skip |

**Dedup 规则**（你已确认的"按 source 优先级 skip"）：

```python
SOURCE_PRIORITY = {"user": 3, "extracted": 2, "system": 1}

# 已有 key 存在时：
#   新 source 优先级 > 已有 source 优先级 → 覆盖
#   否则 → skip
# 例：user 已有，extracted 来 → skip（保护 user）
#     extracted 已有，user 来 → 覆盖
```

### 3. CLI 命令

**新增**（`merco/cli/commands.py`）：

| 命令 | 行为 |
|------|------|
| `/remember <text...>` | emit `command.remember(text)` |
| `/memories [tag]` | `store.list_keys(tag)` + 格式化输出 |
| `/forget <key>` | `store.delete(key)`，不存在静默 no-op |
| `/recall <query>` | 已存在，不改 |

**`/remember` key 解析**：
- `/remember 我喜欢用中文交流` → 自动派生 `user_<前20字>_<hash8>`
- `/remember key=my_pref 我偏好...` → 显式 key
- `/remember 生日=1990-01-01` → 解析为 key=生日, value=1990-01-01

**`/memories` 输出**：
```
📚 已存记忆 (N 条)
─────────────────────────────────────────
[user]      2026-06-15  user_我喜欢用中文_d4e9
  我喜欢用中文交流
[extracted] 2026-06-14  extracted_sess_xxx_3f8e
  用户偏好简洁回复
```

### 4. Config 新增

`merco/core/config.py`：dataclass 字段，序列化到 `merco.json` 时自动归入 `memory.*` 嵌套对象（与现有 recall 配置保持一致）。

```python
# 已有（不删）
memory_enabled: bool = True
memory_path: str = "~/.merco/memory"
memory_recall_enabled: bool = True
memory_recall_limit: int = 3
memory_recall_max_chars: int = 300
memory_recall_threshold: float = 0.0

# 新增
memory_auto_extract_on_session_end: bool = False   # 默认关
memory_extract_max_per_session: int = 3
memory_extract_min_messages: int = 5
```

### 5. Observer 接入

`merco/observability/observer.py` 新增一个订阅：

```python
hooks.on("memory.saved", self._on_memory_saved)

async def _on_memory_saved(self, key: str, source: str, **kwargs):
    self._live.increment("memories_saved")
```

`/report` 输出新增：`memories_saved: N`

### 6. Agent 启动装配

`merco/core/agent.py`：

```python
# 已有
self.recaller = HybridRecaller(...)

# 新增
self.memory_save_pipeline = MemorySavePipeline(
    store=MemoryStore(config.memory_path),
    hooks=self.hooks,
)
self.memory_strategies = [ExplicitRememberStrategy(self.memory_save_pipeline)]
if config.memory_auto_extract_on_session_end:
    self.memory_strategies.append(
        SessionEndExtractStrategy(self.memory_save_pipeline, self.llm, ...)
    )
for strat in self.memory_strategies:
    strat.subscribe(self.hooks)
```

### 7. 新增 Hook 事件

| 事件 | 触发方 | 载荷 |
|------|-------|------|
| `command.remember` | `/remember` 命令 | `text, key?` |
| `memory.saved` | Pipeline.save 成功 | `key, value, source, tags` |
| `memory.failed` | Pipeline.save 失败 | `key, error` |

## 文件变更

| 文件 | 变更类型 | 职责 |
|------|---------|------|
| `merco/memory/save_pipeline.py` | 新建 | MemorySavePipeline + SaveItem + SourceEnricher + DedupProcessor |
| `merco/memory/strategy.py` | 新建 | MemorySaveStrategy ABC + ExplicitRememberStrategy + SessionEndExtractStrategy |
| `merco/memory/__init__.py` | 修改 | 导出新符号 |
| `merco/core/agent.py` | 修改 | 启动时装配 Pipeline + Strategies |
| `merco/core/config.py` | 修改 | 新增 3 个配置项 |
| `merco/cli/commands.py` | 修改 | 新增 /remember, /memories, /forget |
| `merco/observability/observer.py` | 修改 | 订阅 memory.saved |

## 测试计划

| 层 | 文件 | 用例 |
|---|------|------|
| Unit | `tests/memory/test_save_pipeline.py` | SourceEnricher 补 tag、DedupProcessor 优先级规则（user>extracted>system）、Pipeline 链顺序 |
| Unit | `tests/memory/test_strategy.py` | ExplicitRemember 派生 key、key=value 解析、SessionEndExtract 太短跳过、LLM 失败不抛 |
| Unit | `tests/memory/test_cli.py` | /remember /memories /forget 命令 |
| Integration | `tests/integration/test_memory_lifecycle.py` | emit → Strategy → Pipeline → Store 端到端，Observer 收到 memory.saved |

## 错误处理（fail-soft 分级）

| 场景 | 处理 | 用户感知 |
|------|------|---------|
| `MemoryStore.save` IO 失败 | log + emit `memory.failed` | CLI 提示"保存失败" |
| Dedup 冲突 | return None | 静默 skip |
| LLM 抽取失败 | log + return | session.destroy 正常 |
| LLM 输出非法 JSON | 整批丢弃 | 无 |
| `/forget` 不存在 key | 静默 no-op | 无 |
| `/memories` 空 | 友好提示 | "暂无记忆" |

## 扩展点（YAGNI 预留，spec 写明但不实现）

- `SecretFilterProcessor` — 敏感信息检测
- 跨 agent 共享 Memory（MemoryStore backend 抽象）
- 记忆图谱（实体-关系抽取）
- TTL 过期机制

## 风险

| 风险 | 缓解 |
|------|------|
| LLM 抽取消耗 token | opt-in 默认关，文档提醒 |
| 抽取内容质量不可控 | 显式 /remember 优先级最高 |
| 存储膨胀 | 暂无 TTL，靠 /forget 手动 |
| MemoryStore 并发写 | 已有，JSON 文件 fcntl 不在本 spec 范围 |

## 不在本 spec 范围

- Memory recall 召回逻辑（已通）
- MemoryStore 文件格式（不改）
- FTS5 索引（不动）
- Memory 加密/压缩（YAGNI）
