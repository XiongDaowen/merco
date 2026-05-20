# 开发教训

每次犯错后的反思，避免重蹈覆辙。

---

## 2026-05-21: 不要把 provider 名写进核心代码

**场景**：调试 SCNet 的 429 限流时，在 `llm.py` 的注释和变量名里写了 "SCNet"。

**错误**：
- `# 关闭 SDK 自动重试（SCNet 不返回 Retry-After，SDK 退避太快）`
- 重试逻辑硬编码 `2s / 4s`，没有参数化

**教训**：
1. **核心模块不应知道任何 provider 的名字**。LLMClient 是一个通用客户端，今天接 SCNet，明天接 OpenAI，后天接 Groq。provider 特定的行为应该通过配置/参数传入，而不是写死在核心代码。
2. **看到自己在注释里写 provider 名时，立即停下来问：这个行为是所有 provider 都需要的，还是这一个的？** 如果是通用的，去掉 provider 名；如果是特定的，通过参数化暴露出去。
3. **评论是代码坏味道的镜子**——如果评论需要提到具体厂商名来解释为什么这里这样做，说明这个逻辑应该被参数化。

**正确做法**：
- 重试间隔参数化：`LLMClient(retry_delays=(2, 4))`
- 注释改为通用描述："部分网关不返回 Retry-After，SDK 内置退避过快"
- provider 特定的值由配置层传入

---

## 2026-05-21: 修一类 Bug 时要检查同类代码

**场景**：给 `chat()` 加了重试逻辑，但忘了 `chat_stream()` 也有同样的问题。

**教训**：改完一个方法后，搜索同类方法是否有同样的问题。在这个项目里，`chat` 和 `chat_stream` 是同一层的两个入口，改了一个必须检查另一个。

---

## 2026-05-21: patch 大段代码前先完整读取文件

**场景**：用分页读取（offset/limit）看了文件，然后直接 patch，结果写入验证失败。

**教训**：patch 操作需要完整文件内容来做写入后验证。如果之前用了 offset/limit 分页读取，**必须先 `read_file(path)` 无参读取整个文件**，再执行 patch。

---

## 2026-05-21: "最小修复"不是"只修一个文件"

**场景**：给 `chat()` 加 try/except 时只修了异常处理，没同步给 `chat_stream()`。

**教训**："最小修复"指改动范围最小，但不等于只改一个方法。同类代码的问题要一起修，否则留着一个已知的坑就是给自己埋雷。

---

## 2026-05-20: 表面修复只在延迟爆炸

**场景**：之前有人在调用方用 `try/except: pass` 掩盖底层崩溃。

**教训**：已纳入 Bug 修复流程规范。修复必须从根因改起，不允许在调用方加 `except: pass` 来掩盖问题。

---

## 遗留问题：会话启动前缺少模型探活

**场景**：Agent 启动时不验证模型是否可用，用户输入第一句话后才收到 422 "Model Not Exist" 或 401 认证失败。

**影响**：用户进了 REPL、打了招呼，然后才看到报错——体验很糟。今天切换 deepseek-v4-pro 时就踩了这个坑，模型不存在但 REPL 照样启动。

**应做**：Agent 初始化时发一个最小探活请求（`messages=[{"role":"user", "content":"ping"}], max_tokens=1`），通过才进 REPL，失败则立即报错退出。Hermes/OpenCode 都有这个机制。

---

## 遗留问题：敏感操作无权限拦截

**场景**：Bash 工具直接执行任意命令，没有经过 `SecurityChecker` 或 `PermissionManager`。Sandbox 隔离、沙箱、危险命令检测的代码都在 `openmercury/sandbox/` 里写好了，但 `bash_tools.py` 和 `file_tools.py` 根本没 import 它们。

**影响**：Agent 可以通过工具执行 `rm -rf /`、修改系统文件、读取敏感路径——完全没有拦截。

**应做**：工具执行前走 `PermissionManager.check()` + `SecurityChecker.scan()`，敏感操作弹确认或直接拒绝。代码已经有了（`sandbox/isolation.py`, `sandbox/permissions.py`, `sandbox/security.py`），只需要在工具层接入。
