"""通用辅助函数"""

import os
import re
from pathlib import Path


def expand_path(path: str) -> Path:
    """展开路径中的 ~ 和环境变量"""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def truncate(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def extract_urls(text: str) -> list[str]:
    """提取文本中的 URL"""
    url_pattern = r"https?://[^\s<>\"]+|www\.[^\s<>\"]+"
    return re.findall(url_pattern, text)


def slugify(text: str) -> str:
    """将文本转换为 slug 格式"""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def format_bytes(bytes: int) -> str:
    """格式化字节数为可读格式"""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"
