"""Atomic JSONL storage for events."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Iterator

from nfr.models import Event
from nfr.constants import STORAGE_LOGS


def _today_dir() -> Path:
    STORAGE_LOGS.mkdir(parents=True, exist_ok=True)
    d = STORAGE_LOGS / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(exist_ok=True)
    return d


def append_event(event: Event) -> None:
    """Atomically append an event to today's log."""
    path = _today_dir() / "events.jsonl"
    line = json.dumps(event.to_dict()) + "\n"
    # atomic append
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read_events(date: str = None) -> List[Event]:
    """Read events for a given date (default: today)."""
    if date is None:
        path = _today_dir() / "events.jsonl"
    else:
        path = STORAGE_LOGS / date / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Event.from_dict(json.loads(line)))
        except Exception:
            continue
    return out


def iter_events(date: str = None) -> Iterator[Event]:
    for e in read_events(date):
        yield e
