"""SQLite SessionStore 测试 — 无 merco 依赖"""

import os
import sys
import tempfile

sys.path.insert(0, ".")

# 直接 import，session_store.py 只依赖 stdlib
from merco.memory.session_store import SessionStore

db = os.path.join(tempfile.mkdtemp(), "test.db")
store = SessionStore(db)

print("── 创建会话 ──")
store.create_session("s1", "测试标题")
print("  ✓")

print("── 保存消息 ──")
store.save_message("s1", "user", "你好")
store.save_message("s1", "assistant", "你好！", reasoning="推理内容")
store.save_message("s1", "user", "帮我看个文件")
print("  ✓")

print("── 加载 ──")
s = store.load_session("s1")
assert s is not None
assert s["title"] == "测试标题"
assert len(s["messages"]) == 3
assert s["message_count"] == 3
print(f"  {len(s['messages'])} messages  ✓")

print("── 列出 ──")
sessions = store.list_sessions()
assert len(sessions) == 1
print(f"  {len(sessions)} session(s)  ✓")

print("── 不覆盖已有标题 ──")
store.create_session("s1", "新标题")  # IGNORE
store.update_title("s1", "新标题")  # title != '' → skip
s2 = store.load_session("s1")
assert s2["title"] == "测试标题"
print("  title preserved  ✓")

print("── 标题留空时才更新 ──")
store.create_session("s_empty", "")
store.update_title("s_empty", "自动标题")
s3 = store.load_session("s_empty")
assert s3["title"] == "自动标题"
print("  auto-titled  ✓")

print("── 删除 ──")
store.delete_session("s1")
assert store.load_session("s1") is None
print("  deleted  ✓")

os.remove(db)
print("\n全部通过 ✓")
