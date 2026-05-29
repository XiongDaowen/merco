# Memory 召回 — 设计规格

> 自动从历史会话和持久化记忆中召回相关内容，注入 Agent 上下文。

## 动机

merco 已有完整的会话存储（`SessionStore` + `SessionSearch` FTS5）和记忆存储（`MemoryStore`），但没有自动召回机制。每次新对话都是「全新开始」，Agent 无法利用历史上下文。对标 hermes/openclaw 都有记忆召回，merco 目前 7 分，此项是追分项。

## 方案选择

选择 **方案 C（FTS5 + Embedding 扩展）**：
- Phase 2 当前：纯 FTS5 关键字匹配
- 接口预留 Embedding 扩展点，后续不破坏现有代码
- 同时搜索 SessionSearch（历史会话）和 MemoryStore（持久化记忆），合并去重

## 架构总览

```
Agent.run(prompt)
  │
  ├─ _recall()  ← 新增
  │   ├─ FTS5Recaller → SessionSearch.search(prompt)
  │   └─ MemoryRecaller → MemoryStore.search(prompt)
  │
  ├─ _build_system_prompt()  ← 召回结果追加到末尾
  │
  └─ _agent_loop()  ← 不变
```

## 配置项

`merco.json` 新增 `memory` 段：

```json
{
  "memory": {
    "recall_enabled": true,
    "recall_limit": 3,
    "recall_max_chars": 300,
    "recall_threshold": 0.0
  }
}
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `recall_enabled` | true | 是否自动召回 |
| `recall_limit` | 3 | 最多注入条数 |
| `recall_max_chars` | 300 | 每条最大字符 |
| `recall_threshold` | 0.0 | 最小匹配分数（0=不过滤，为 embedding 预留） |

## Recaller 接口

```python
@dataclass
class RecallResult:
    snippet: str           # 截断后的内容
    session_title: str     # 来自哪个会话
    score: float           # 匹配分数
    source: str            # "fts5" | "memory"

class BaseRecaller(ABC):
    name: str = ""
    @abstractmethod
    async def recall(self, query: str, limit: int) -> list[RecallResult]: ...

class FTS5Recaller(BaseRecaller):     # Phase 2：调 SessionSearch
class MemoryRecaller(BaseRecaller):   # 调 MemoryStore.search
class HybridRecaller(BaseRecaller):   # 聚合 + 排序 + 去重 + 截断
```

## Agent 集成

- `agent.py` `__init__` 初始化 `HybridRecaller`
- `_build_system_prompt()` 末尾追加召回结果（3 条 × 300 字 ≈ 600 tokens ≈ 1-3% 上下文）
- 同一 prompt 不重复查询（内部缓存）
- `recall_enabled=False` 时零开销

注入格式：
```
## 相关历史对话（仅供参考）
1. [会话标题] 片段内容...
2. [会话标题] 片段内容...
```

## CLI 命令

`/recall <关键词>` — 手动触发，返回匹配结果预览，不注入上下文。

## 改动文件

| 文件 | 改动 |
|------|------|
| `merco/memory/recall.py` | 重写：BaseRecaller + FTS5Recaller + MemoryRecaller + HybridRecaller |
| `merco/core/agent.py` | `__init__` 初始化 recaller + `_build_system_prompt` 注入召回 |
| `merco/core/config.py` | 加 `memory` 配置段 |
| `cli/main.py` | 加 `/recall` 命令 |

## 性能评估

- 搜索：本地 SQLite FTS5 查询（毫秒级）
- Token 开销：最坏 3×300 字 ≈ 600 tokens（< 1-3% 上下文）
- 收益：减少重复解释和来回澄清，一轮对话省下的 token 远超开销

## 后续扩展

- `EmbeddingRecaller` — 接入 embedding 模型做语义精排
- `recall_threshold` — 现在为 0，embedding 后可设 cosine 阈值
- 召回内容去重 — 同一会话多次匹配时合并
