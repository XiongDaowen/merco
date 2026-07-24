"""JSONBackend — 每记忆一个 .json 文件"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from merco.memory.backend import MemoryBackend


class JSONBackend(MemoryBackend):
    """JSON 文件后端"""

    name = "json"

    def __init__(self, base_path: str):
        self.base_path = Path(base_path).expanduser()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value, tags: list = None) -> None:
        entry = {
            "key": key,
            "value": value,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }
        file_path = self.base_path / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(entry, f, indent=2)

    def load(self, key: str) -> dict | None:
        file_path = self.base_path / f"{key}.json"
        if not file_path.exists():
            return None
        with open(file_path) as f:
            return json.load(f)

    def delete(self, key: str) -> None:
        file_path = self.base_path / f"{key}.json"
        if file_path.exists():
            file_path.unlink()

    def list_keys(self, tag: str = None) -> list[str]:
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
        results = []
        query_lower = query.lower()
        for f in self.base_path.glob("*.json"):
            with open(f) as fh:
                data = json.load(fh)
                content = json.dumps(data).lower()
                if query_lower in content:
                    results.append(data)
        return results
