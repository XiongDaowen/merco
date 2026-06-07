# Stream Content 实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 实现 content 流式输出，修复 thinking 卡顿问题

**Architecture:** 
- 配置层新增 `stream_content` 和 `stream_thinking_transient` 字段
- StreamingProvider 在 thinking 结束后创建第二个 Live + Panel 用于 content 流式输出
- CLI 层检查配置，避免重复打印

**Tech Stack:** Python 3.12, asyncio, Rich Live/Panel

---

## Task 1: 配置层新增字段

**Objective:** 在 MercoConfig 中新增 `stream_content` 和 `stream_thinking_transient` 配置项

**Files:**
- Modify: `merco/core/config.py`

**Step 1: 查看当前配置结构**

```bash
cd /home/xiowen/code/merco
grep -n "stream_" merco/core/config.py | head -20
```

Expected: 看到现有的 streaming 相关配置项

**Step 2: 新增配置字段**

在 `merco/core/config.py` 的 `MercoConfig` dataclass 中，找到 `streaming: bool = False` 附近，新增：

```python
stream_content: bool = True  # 默认开启 content 流式输出
stream_thinking_transient: bool = False  # 默认保留 thinking 框
```

**Step 3: 更新 from_dict 方法**

在 `from_dict` 方法中，添加新字段的解析：

```python
stream_content=data.get('stream_content', True),
stream_thinking_transient=data.get('stream_thinking_transient', False),
```

**Step 4: 更新 to_dict 方法**

在 `to_dict` 方法中，添加新字段的序列化：

```python
'stream_content': self.stream_content,
'stream_thinking_transient': self.stream_thinking_transient,
```

**Step 5: 验证配置加载**

```bash
cd /home/xiowen/code/merco
python3 -c "
from merco.core.config import MercoConfig
config = MercoConfig()
print('stream_content:', config.stream_content)
print('stream_thinking_transient:', config.stream_thinking_transient)
"
```

Expected: 
```
stream_content: True
stream_thinking_transient: False
```

**Step 6: Commit**

```bash
git add merco/core/config.py
git commit -m "feat: add stream_content and stream_thinking_transient config fields"
```

---

## Task 2: Thinking 卡顿修复 - 定时刷新

**Objective:** 修复 thinking Live 面板在 API 返回慢时的卡顿问题

**Files:**
- Modify: `merco/core/agent.py` (StreamingProvider.get_response)

**Step 1: 查看当前 thinking 刷新逻辑**

```bash
cd /home/xiowen/code/merco
grep -n "live.update" merco/core/agent.py | head -10
```

Expected: 看到 `live.update(_build_reasoning_panel(reasoning_buf))` 在 reasoning chunk 处理中

**Step 2: 实现定时刷新任务**

在 `StreamingProvider.get_response` 方法中，在 `live.start()` 之后，添加定时刷新任务：

```python
# 定时刷新 thinking 面板，防止卡顿
async def _refresh_thinking():
    while True:
        await asyncio.sleep(0.5)
        if reasoning_buf:  # 只在有内容时刷新
            live.update(_build_reasoning_panel(reasoning_buf))

refresh_task = asyncio.create_task(_refresh_thinking())
```

**Step 3: 在 finally 块中取消任务**

在 `try...finally` 的 `finally` 块中，添加任务取消逻辑：

```python
finally:
    if 'refresh_task' in locals():
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    live.stop()
```

**Step 4: 更新 transient 配置**

将 `Live` 的 `transient` 参数改为从配置读取：

```python
live = Live(
    _build_reasoning_panel(""),
    console=console,
    refresh_per_second=10,
    transient=agent.config.stream_thinking_transient  # 从配置读取
)
```

**Step 5: 手动测试 thinking 刷新**

```bash
cd /home/xiowen/code/merco
python3 -c "
import asyncio
from merco.core.config import MercoConfig
from merco.core.agent import StreamingProvider

async def test():
    config = MercoConfig()
    config.stream_thinking = True
    config.stream_thinking_transient = False
    provider = StreamingProvider()
    # 模拟一个慢的 API 调用（这里需要 mock）
    print('Thinking panel should refresh every 0.5s')

asyncio.run(test())
"
```

Expected: 无报错，thinking 面板应该每 0.5 秒刷新一次

**Step 6: Commit**

```bash
git add merco/core/agent.py
git commit -m "fix: add periodic refresh for thinking panel to prevent stuttering"
```

---

## Task 3: Content 流式输出 - 第二个 Live + Panel

**Objective:** 在 thinking 结束后，创建第二个 Live + Panel 用于 content 流式输出

**Files:**
- Modify: `merco/core/agent.py` (StreamingProvider.get_response)

**Step 1: 查看 content 处理逻辑**

```bash
cd /home/xiowen/code/merco
grep -n "content_buf" merco/core/agent.py | head -10
```

Expected: 看到 `content_buf += chunk.get('content', '')` 在 chunk 处理中

**Step 2: 在 thinking 结束后创建 content Live**

在 `async for chunk in stream:` 循环之前，添加 content Live 的创建逻辑：

```python
# 准备 content 流式输出
content_live = None
content_panel = None
if agent.config.stream_content:
    content_panel = Panel("", title="💬 Response", border_style="blue")
    content_live = Live(
        content_panel,
        console=console,
        refresh_per_second=10,
        transient=agent.config.stream_thinking_transient
    )
    content_live.start()
```

**Step 3: 在 chunk 处理中更新 content Live**

在 `content_buf += chunk.get('content', '')` 之后，添加：

```python
if content_live and content_buf:
    content_panel.renderable = Markdown(content_buf)
    content_live.update(content_panel)
```

**Step 4: 在 finally 块中停止 content Live**

在 `finally` 块中，添加 content Live 的停止逻辑：

```python
finally:
    # ... 现有的 refresh_task 取消逻辑 ...
    live.stop()
    if content_live:
        content_live.stop()
```

**Step 5: 手动测试 content 流式输出**

```bash
cd /home/xiowen/code/merco
# 启动 merco 并发送一个简单问题
python3 -m merco
```

输入: "你好"

Expected: 
- Thinking 框显示并保留
- Content 框流式显示回复内容
- 两个框都有边框，内容逐字出现

**Step 6: Commit**

```bash
git add merco/core/agent.py
git commit -m "feat: implement streaming content output with Live + Panel"
```

---

## Task 4: CLI 层避免重复打印

**Objective:** 在 CLI 层检查配置，避免重复打印已流式输出的 content

**Files:**
- Modify: `cli/main.py`

**Step 1: 查看当前打印逻辑**

```bash
cd /home/xiowen/code/merco
grep -n "console.print.*Markdown" cli/main.py | head -10
```

Expected: 看到 `console.print(Panel(Markdown(response)))` 在 agent.run() 之后

**Step 2: 添加配置检查**

在 `cli/main.py` 中，找到打印 response 的地方，修改为：

```python
response = await agent.run(user_input)

# 只在未开启流式输出时打印
if not agent.config.stream_content:
    console.print(Panel(Markdown(response), border_style="blue", title="💬 Response"))
```

**Step 3: 手动测试避免重复打印**

```bash
cd /home/xiowen/code/merco
python3 -m merco
```

输入: "你好"

Expected: 
- Content 只出现一次（流式输出）
- 没有重复的 Panel 打印

**Step 4: 测试 stream_content=False 的情况**

```bash
cd /home/xiowen/code/merco
# 临时修改配置
python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['stream_content'] = False
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
python3 -m merco
```

输入: "你好"

Expected: 
- Thinking 框显示
- Content 一次性打印（非流式）

**Step 5: 恢复配置**

```bash
cd /home/xiowen/code/merco
python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['stream_content'] = True
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

**Step 6: Commit**

```bash
git add cli/main.py
git commit -m "fix: prevent duplicate printing when stream_content is enabled"
```

---

## Task 5: 集成测试与边界情况

**Objective:** 测试各种边界情况，确保功能稳定

**Files:**
- Test: 手动测试

**Step 1: 测试 thinking + content 都流式**

```bash
cd /home/xiowen/code/merco
python3 -m merco
```

输入: "解释一下 Python 的 GIL"

Expected: 
- Thinking 框流式显示思考过程
- Thinking 框保留
- Content 框流式显示回复
- 两个框都有边框

**Step 2: 测试空 content**

输入: 一个会导致空回复的问题（如果有的话）

Expected: 
- 不崩溃
- 显示空 content 或错误提示

**Step 3: 测试 tool_calls 场景**

输入: "读取当前目录的文件列表"

Expected: 
- Thinking 框显示
- Tool 调用显示
- Content 框显示最终回复

**Step 4: 测试 Ctrl+C 中断**

输入: 一个长问题，在回复过程中按 Ctrl+C

Expected: 
- 优雅退出
- 已输出的内容保留在屏幕上
- 无报错

**Step 5: 测试 stream_thinking_transient=True**

```bash
cd /home/xiowen/code/merco
python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['stream_thinking_transient'] = True
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
python3 -m merco
```

输入: "你好"

Expected: 
- Thinking 框在结束后消失
- Content 框保留

**Step 6: 恢复配置**

```bash
cd /home/xiowen/code/merco
python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['stream_thinking_transient'] = False
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

**Step 7: Commit**

```bash
git add .
git commit -m "test: verify stream content functionality with edge cases"
```

---

## Task 6: 文档更新

**Objective:** 更新配置文档，说明新增的配置项

**Files:**
- Modify: `README.md` 或相关文档

**Step 1: 查找配置文档位置**

```bash
cd /home/xiowen/code/merco
find . -name "*.md" -type f | grep -i config | head -10
```

Expected: 找到配置相关的文档

**Step 2: 添加新配置项说明**

在配置文档中，添加：

```markdown
### 流式输出配置

- `stream_content`: 是否启用 content 流式输出（默认: true）
- `stream_thinking_transient`: thinking 框是否在结束后消失（默认: false，即保留）
```

**Step 3: Commit**

```bash
git add *.md
git commit -m "docs: add documentation for stream_content and stream_thinking_transient"
```

---

## 完成标准

- [ ] 所有任务完成并通过测试
- [ ] `stream_content=True` 时，content 流式输出
- [ ] `stream_thinking_transient=False` 时，thinking 框保留
- [ ] 无重复打印
- [ ] 边界情况处理正确
- [ ] 文档更新完成

---

## 执行方式

使用 `subagent-driven-development` skill 执行此计划：
- 每个 Task 分配给一个 subagent
- Spec compliance review 检查是否符合设计文档
- Code quality review 检查代码质量
- 两个 review 都通过后才进入下一个 Task
