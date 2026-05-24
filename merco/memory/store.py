"""记忆存储引擎"""

import json
from pathlib import Path
from typing import Optional
from datetime import datetime


class MemoryStore:
    """持久化记忆存储"""

    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or "~/.merco/memory").expanduser()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value: dict, tags: list = None):
        """保存记忆"""
        entry = {
            "key": key,
            "value": value,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }

        file_path = self.base_path / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(entry, f, indent=2)

    def load(self, key: str) -> Optional[dict]:
        """加载记忆"""
        file_path = self.base_path / f"{key}.json"
        if not file_path.exists():
            return None

        with open(file_path) as f:
            return json.load(f)

    def delete(self, key: str):
        """删除记忆"""
        file_path = self.base_path / f"{key}.json"
        if file_path.exists():
            file_path.unlink()

    def list_keys(self, tag: str = None) -> list[str]:
        """列出所有记忆键"""
        keys = []
        for f in self.base_path.glob("*.json"):
            if tag:
                with open(f) as fh:
                    data = json.load(fh)
                    if tag in data.get("tags", []):
                        keys.append(f.stem)
            else:
                keys.append(f.stem)
        return keys

    def search(self, query: str) -> list[dict]:
        """搜索记忆（简单文本匹配）"""
        results = []
        query_lower = query.lower()

        for f in self.base_path.glob("*.json"):
            with open(f) as fh:
                data = json.load(fh)
                content = json.dumps(data).lower()
                if query_lower in content:
                    results.append(data)

        return results
