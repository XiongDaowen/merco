# Bug记录：快照系统撤销逻辑缺陷  ✅ **已修复**
## 发现时间：2026-07-08
## 修复时间：2026-07-08
## 模块：merco.sandbox.snapshot
## 问题描述：
当调用 `revert(session_id)` 撤销整会话的所有快照时，无论撤销操作是否成功，都会删除会话文件。
即使部分或全部文件撤销失败，会话文件仍然会被删除，导致无法重试撤销操作。

## 问题代码位置：
`merco/sandbox/snapshot.py` 第143-145行（修复前）：
```python
if snapshot_index is None:
    # 全部撤销后删除会话文件
    _session_path(session_id).unlink(missing_ok=True)
```

## 修复方案：
仅当所有撤销操作都成功时，才删除会话文件。失败时保留会话文件以便重试。
```python
if snapshot_index is None:
    # 全部撤销后删除会话文件（仅当所有撤销都成功；失败时保留以便重试）
    if all(r["reverted"] for r in results):
        _session_path(session_id).unlink(missing_ok=True)
```

## 修复效果验证：
- ✅ 撤销失败时保留会话文件（Bug 修复点）
- ✅ 全部成功时删除会话文件
- ✅ 单条撤销时保留会话文件
- ✅ 部分失败场景测试通过（新增 `test_revert_partial_failure_keeps_session` 回归测试）
---
# Bug记录：LLM 思考标签提取逻辑缺陷  ✅ **已修复**
## 发现时间：2026-07-08
## 修复时间：2026-07-08
## 模块：merco.core.llm._client
## 问题描述：
`ThinkTagStrategy.extract_from_delta`（流式场景）遇到标准 `` 标签时会失败。
因为 `THINK_TAG_PAIRS` 的第一项是 `("<think>", "[/think]")`，当循环发现 `<think>` 开标签时，会先去找 `[/think]` 闭标签；找不到时**立即**进入跨 chunk 分支，不会继续尝试第二项 `("<think>", "")`，导致标准格式被错误地当作跨 chunk 场景处理。

## 影响范围：
- 仅**流式** `extract_from_delta` 受影响（`_parse_chunk` → `ThinkingExtractor.extract_from_delta`）
- **非流式** `extract_from_message` 不受影响（每个标签对独立编译正则）
- 触发条件：使用 `<think>...</think>` 的 provider，单 chunk 包含完整 think 块

## 问题代码位置：
`merco/core/llm/_client.py` 第 205-223行（修复前）：
```python
for ot, ct in THINK_TAG_PAIRS:
    if ot in content:
        before_open, rest = content.split(ot, 1)
        if ct in rest:
            # 处理完整块
            ...
        else:
            # 进入跨 chunk 分支（错误：应继续尝试下一个标签对）
            self._in_thinking = True
            ...
            return result
return {"content": content}
```

## 修复方案：
第一轮循环只尝试**完整匹配**：开标签命中但闭标签不匹配时 `continue`，不进入跨 chunk。
第二轮循环处理**真正的跨 chunk 场景**：所有标签对都开标签命中但闭标签都不匹配时，进入状态机。

```python
# 第一轮：完整匹配
for ot, ct in THINK_TAG_PAIRS:
    if ot in content:
        before_open, rest = content.split(ot, 1)
        if ct in rest:
            # 完整块处理
            ...
            return result
        # 闭标签不匹配 → continue，尝试下一个标签对
# 第二轮：跨 chunk 状态机
for ot, ct in THINK_TAG_PAIRS:
    if ot in content:
        before_open, rest = content.split(ot, 1)
        self._in_thinking = True
        ...
        return result
return {"content": content}
```

## 验证结果：
- ✅ 单 chunk 标准格式 `` 可正确提取（`test_extract_from_delta_single_chunk`）
- ✅ 通过 ThinkingExtractor 入口同样正常（`test_extract_from_delta_fallback_to_tag_strategy`）
- ✅ 跨 chunk 场景（`[/think]` 格式）未受影响（`test_extract_from_delta_cross_chunk_open_first`）
- ✅ LLM 客户端全部 36 个测试通过
---
# Bug记录：LLM 错误消息敏感信息脱敏逻辑缺陷
## 发现时间：2026-07-08
## 模块：merco.core.llm.error_ui
## 问题描述：
敏感信息脱敏的正则表达式使用了 `\bapi_key\b` 进行匹配，只能匹配带下划线的 "api_key"，无法匹配带空格的 "API key" 这种常见写法。

## 问题代码位置：
`merco/core/llm/error_ui.py` 第109-111行：
```python
for kw in _SENSITIVE_KEYWORDS:
    if re.search(r'(?i)\b' + re.escape(kw) + r'\b', msg):
        return "(包含敏感信息，已脱敏)"
```

## 影响：
包含 "API key" 字样的错误消息不会被脱敏，可能导致敏感信息泄露。
---
# 测试bug：test_default_session_id_format
## 问题描述：
测试用例没有正确mock所有datetime.now()调用，导致第二个调用（用于生成timestamp字段）返回MagicMock对象，无法被JSON序列化。
## 修复方案（仅测试层）：
需要mock datetime.now()的返回值，使其isoformat()方法返回一个字符串，或者只mock第一次调用。
