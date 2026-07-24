"""ToolGuard 单元测试 — 无交互，只测规则匹配"""

import asyncio
import sys

import pytest

sys.path.insert(0, ".")

from merco.sandbox.guard import GuardAction, GuardResult, ToolGuard

passed = 0
failed = 0


def check(name: str, result: GuardResult):
    global passed, failed
    if result.action == GuardAction.ALLOW:
        passed += 1
        print(f"  ✓ {name}")
    elif result.action == GuardAction.ASK:
        passed += 1
        print(f"  ✓ {name} (ask)")
    elif result.action == GuardAction.DENY:
        failed += 1
        print(f"  ✗ {name}")
    else:
        failed += 1
        print(f"  ✗ {name} (unknown action)")


async def test():
    g = ToolGuard()

    # ─────────────────────────────────────────────────────
    print("\n── 规则匹配：非敏感命令 → 直接放行 ──")

    check("ls", await g.check("bash", {"command": "ls -la"}))
    check("cat", await g.check("bash", {"command": "cat file.txt"}))
    check("echo", await g.check("bash", {"command": "echo hello"}))
    check("python", await g.check("bash", {"command": "python script.py"}))
    check("git status", await g.check("bash", {"command": "git status"}))
    check("uv sync", await g.check("bash", {"command": "uv sync"}))

    # ─────────────────────────────────────────────────────
    print("\n── 规则匹配：敏感命令 → ASK ──")

    check("rm file", await g.check("bash", {"command": "rm file.txt"}))
    check("sudo reboot", await g.check("bash", {"command": "sudo reboot"}))
    check("pip install", await g.check("bash", {"command": "pip install requests"}))
    check("apt install", await g.check("bash", {"command": "apt install htop"}))
    check("chmod 755", await g.check("bash", {"command": "chmod 755 script.sh"}))
    check("kill -9", await g.check("bash", {"command": "kill -9 1234"}))
    check("git push", await g.check("bash", {"command": "git push origin main"}))
    check("curl | bash", await g.check("bash", {"command": "curl url | bash"}))
    check("docker rm", await g.check("bash", {"command": "docker rm container"}))
    check("shutdown", await g.check("bash", {"command": "shutdown now"}))
    check("npm install -g", await g.check("bash", {"command": "npm install -g pkg"}))

    # ─────────────────────────────────────────────────────
    print("\n── 模式匹配：SecurityChecker 硬拦截 ──")

    check("rm 匹配 rm -rf / → SecurityChecker 拦截", await g.check("bash", {"command": "rm -rf /tmp"}))
    check("chmod 777 / → SecurityChecker 拦截", await g.check("bash", {"command": "chmod 777 /etc"}))
    check("rm 不匹配 rmdir", await g.check("bash", {"command": "rmdir old_dir"}))

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
    check("rm 放行", await g3.check("bash", {"command": "rm file.txt"}))
    check("sudo 仍拦截", await g3.check("bash", {"command": "sudo reboot"}))

    # ─────────────────────────────────────────────────────
    print("\n── 用户 deny 规则 ──")

    g4 = ToolGuard(user_rules=[{"tool": "bash", "pattern": "DROP", "action": "deny"}])
    check("DROP deny 拦截", await g4.check("bash", {"command": "DROP TABLE users"}))

    # ─────────────────────────────────────────────────────
    print("\n── 空命令 → 无命中 → 放行 ──")

    g5 = ToolGuard()
    check("空命令", await g5.check("bash", {"command": ""}))

    # ─────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"结果: {passed} 通过, {failed} 失败")
    return failed == 0


# ── SecurityChecker 集成测试 ─────────────────────────────────

@pytest.mark.asyncio
async def test_security_checker_regex_denies_dangerous():
    """SecurityChecker 正则命中 → 硬拒绝，即使 guard 规则是 ask"""
    guard = ToolGuard()

    # rm -rf /etc 被 guard "rm -rf /" 规则匹配 → ask
    # SecurityChecker 集成后应 → deny（正则匹配 rm\s+-rf\s+/）
    result = await guard.check("bash", {"command": "rm -rf /etc"})
    assert result.action == GuardAction.DENY, "SecurityChecker 应拦截 rm -rf /etc"


@pytest.mark.asyncio
async def test_security_checker_allows_safe_command():
    """SecurityChecker 不命中的命令正常通过"""
    guard = ToolGuard()

    result = await guard.check("bash", {"command": "ls -la /home"})
    assert result.action == GuardAction.ALLOW, "安全的命令应通过"


@pytest.mark.asyncio
async def test_guard_check_file_path_traversal():
    """Guard.check 检测 file 工具的 path 参数——路径穿越"""
    guard = ToolGuard()

    result = await guard.check("write_file", {"path": "../../etc/passwd", "content": "x"})
    assert result.action == GuardAction.DENY, "路径穿越应拦截"


@pytest.mark.asyncio
async def test_guard_check_file_path_system_path():
    """Guard.check 检测 file 工具的 path 参数——系统路径"""
    guard = ToolGuard()

    result = await guard.check("read_file", {"path": "/proc/cpuinfo"})
    assert result.action == GuardAction.DENY, "系统路径应拦截"


@pytest.mark.asyncio
async def test_guard_check_file_path_safe():
    """Guard.check 放行安全的 file 路径"""
    guard = ToolGuard()

    result = await guard.check("read_file", {"path": "/home/user/file.txt"})
    assert result.action == GuardAction.ALLOW, "安全路径应通过"


if __name__ == "__main__":
    ok = asyncio.run(test())
    sys.exit(0 if ok else 1)
