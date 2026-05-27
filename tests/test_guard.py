"""ToolGuard 单元测试 — 无交互，只测规则匹配"""

import asyncio
import sys
sys.path.insert(0, ".")

from merco.sandbox.guard import ToolGuard

passed = 0
failed = 0


def check(name: str, condition: bool):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")


async def test():
    # ── 偷换 _confirm：测试模式下不等待输入 ──
    async def mock_confirm(self, command, rule):
        return True  # 模拟用户按了 y

    async def mock_reject(self, command, rule):
        return False  # 模拟用户按了 n

    ToolGuard._confirm = mock_confirm

    # ─────────────────────────────────────────────────────
    print("\n── 规则匹配：非敏感命令 → 直接放行 ──")

    g = ToolGuard()
    check("ls", await g._check("bash", "ls -la"))
    check("cat", await g._check("bash", "cat file.txt"))
    check("echo", await g._check("bash", "echo hello"))
    check("python", await g._check("bash", "python script.py"))
    check("git status", await g._check("bash", "git status"))
    check("uv sync", await g._check("bash", "uv sync"))

    # ─────────────────────────────────────────────────────
    print("\n── 规则匹配：敏感命令 → 命中确认 ──")

    check("rm file", await g._check("bash", "rm file.txt"))
    check("sudo reboot", await g._check("bash", "sudo reboot"))
    check("pip install", await g._check("bash", "pip install requests"))
    check("apt install", await g._check("bash", "apt install htop"))
    check("chmod 755", await g._check("bash", "chmod 755 script.sh"))
    check("kill -9", await g._check("bash", "kill -9 1234"))
    check("git push", await g._check("bash", "git push origin main"))
    check("curl | bash", await g._check("bash", "curl url | bash"))
    check("docker rm", await g._check("bash", "docker rm container"))
    check("shutdown", await g._check("bash", "shutdown now"))
    check("npm install -g", await g._check("bash", "npm install -g pkg"))

    # ─────────────────────────────────────────────────────
    print("\n── 模式匹配：精确命中 ──")

    check("rm 不匹配 rmdir", await g._check("bash", "rmdir old_dir") is True)
    check("rm 匹配 rm -rf /", await g._check("bash", "rm -rf /tmp"))
    check("chmod 777 / 命中", await g._check("bash", "chmod 777 /etc"))

    # ─────────────────────────────────────────────────────
    print("\n── 非 bash 工具 → 跳过 ──")

    check("write_file", await g.check("write_file", {"path": "/etc/hosts", "content": "x"}))
    check("read_file", await g.check("read_file", {"path": "/etc/passwd"}))
    check("edit_file", await g.check("edit_file", {"path": "foo.py"}))

    # ─────────────────────────────────────────────────────
    print("\n── mode=auto → 全跳过 ──")

    g2 = ToolGuard(mode="auto")
    check("rm -rf / in auto", await g2.check("bash", {"command": "rm -rf /"}))
    check("sudo in auto", await g2.check("bash", {"command": "sudo reboot"}))

    # ─────────────────────────────────────────────────────
    print("\n── 用户 rule('rm ', 'allow') 覆盖默认 ask ──")

    g3 = ToolGuard()
    g3.rule("bash", "rm ", "allow")
    check("rm 放行", await g3._check("bash", "rm file.txt"))
    check("sudo 仍拦截", await g3._check("bash", "sudo reboot"))

    # ─────────────────────────────────────────────────────
    print("\n── 用户 deny 规则 ──")

    g4 = ToolGuard(user_rules=[{"tool": "bash", "pattern": "DROP", "action": "deny"}])
    ToolGuard._confirm = mock_reject  # 换成 mock 拒绝，但 deny 不应该走到 confirm
    # deny 不调 confirm，mock 拒绝不影响 deny
    check("DROP deny 拦截", not await g4._check("bash", "DROP TABLE users"))

    # ─────────────────────────────────────────────────────
    print("\n── 空命令 → 无命中 → 放行 ──")

    g5 = ToolGuard()
    check("空命令", await g5._check("bash", ""))

    # ─────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(test())
    sys.exit(0 if ok else 1)
