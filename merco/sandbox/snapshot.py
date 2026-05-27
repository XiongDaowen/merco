"""快照系统 — 文件修改历史跟踪

每次编辑前保存文件副本，支持：
- track(path, content) — 记录修改前内容
- history(session_id) — 查询某轮会话的所有改动
- revert(session_id) — 撤销整轮修改
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("merco.sandbox.snapshot")

# 快照存储根目录
SNAPSHOT_DIR = Path.home() / ".merco" / "snapshots"


def _ensure_dir() -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOT_DIR


def _session_path(session_id: str) -> Path:
    return _ensure_dir() / f"{session_id}.json"


# ── 当前会话 ID（由 Agent 在启动时设置）──
_current_session_id: str | None = None


def set_current_session(session_id: str) -> None:
    """设置当前会话 ID（由 Agent 在初始化时调用）"""
    global _current_session_id
    _current_session_id = session_id


def get_current_session() -> str | None:
    return _current_session_id


# ── 公开 API ────────────────────────────────────────────────────────


def track(path: str, content: str, session_id: str | None = None) -> dict:
    """记录一次编辑前的快照

    Args:
        path: 被修改的文件路径
        content: 修改前的文件内容
        session_id: 会话标识，默认用当前时间戳

    Returns:
        {session_id, snapshot_id, path, timestamp}
    """
    if session_id is None:
        session_id = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    snapshots = _load(session_id)
    entry = {
        "path": str(Path(path).resolve()),
        "content": content,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    snapshots.append(entry)
    _save(session_id, snapshots)

    return {
        "session_id": session_id,
        "snapshot_id": len(snapshots) - 1,
        "path": entry["path"],
        "timestamp": entry["timestamp"],
    }


def history(session_id: str) -> list[dict]:
    """查询某次会话的所有快照记录

    Returns:
        [{path, timestamp, content}]
    """
    return _load(session_id)


def list_sessions() -> list[dict]:
    """列出所有有快照的会话

    Returns:
        [{session_id, file_count, timestamp}]
    """
    sessions = []
    for f in sorted(_ensure_dir().glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "session_id": f.stem,
                "file_count": len(data),
                "timestamp": data[0]["timestamp"] if data else "",
            })
        except Exception:
            continue
    return sessions


def revert(session_id: str, snapshot_index: int | None = None) -> list[dict]:
    """撤销快照中的修改

    Args:
        session_id: 会话标识
        snapshot_index: 要撤销的快照索引（None=撤销全部）

    Returns:
        [{"path": str, "reverted": bool, "error": str|None}]
    """
    snapshots = _load(session_id)
    if not snapshots:
        return []

    if snapshot_index is not None:
        snapshots = [snapshots[snapshot_index]]

    results = []
    for entry in snapshots:
        file_path = Path(entry["path"])
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(entry["content"], encoding="utf-8")
            results.append({
                "path": entry["path"],
                "reverted": True,
                "error": None,
            })
            logger.info("已恢复 %s", entry["path"])
        except Exception as e:
            results.append({
                "path": entry["path"],
                "reverted": False,
                "error": str(e),
            })

    if snapshot_index is None:
        # 全部撤销后删除会话文件
        _session_path(session_id).unlink(missing_ok=True)

    return results


# ── 内部 ────────────────────────────────────────────────────────────


def _load(session_id: str) -> list[dict]:
    sp = _session_path(session_id)
    if sp.exists():
        try:
            return json.loads(sp.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(session_id: str, data: list[dict]) -> None:
    sp = _session_path(session_id)
    sp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
