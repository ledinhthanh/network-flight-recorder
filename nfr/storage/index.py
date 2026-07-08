"""Daily index file."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from nfr.constants import STORAGE_INDEX


def _load() -> dict:
    if not STORAGE_INDEX.exists():
        return {}
    try:
        return json.loads(STORAGE_INDEX.read_text())
    except Exception:
        return {}


def _save(idx: dict) -> None:
    STORAGE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORAGE_INDEX.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, indent=2, sort_keys=True))
    tmp.rename(STORAGE_INDEX)


def update_day(date: str, status: str, event_count: int, top_issue: str = None) -> None:
    idx = _load()
    idx[date] = {"status": status, "events": event_count, "top_issue": top_issue}
    _save(idx)


def get_index() -> Dict[str, Any]:
    return _load()
