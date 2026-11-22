"""保存每个浏览器会话的 SQL 草稿和通过记录。"""

from __future__ import annotations

import json
from pathlib import Path


def empty_progress() -> dict:
    return {"passed": {}, "sql": {}, "hints": {}, "answers_seen": {}, "lineage": {}}


def load_progress(path: Path) -> dict:
    if not path.exists():
        return empty_progress()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_progress()
    base = empty_progress()
    if isinstance(data, dict):
        for key in base:
            if isinstance(data.get(key), dict):
                base[key] = data[key]
    return base


def save_progress(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
