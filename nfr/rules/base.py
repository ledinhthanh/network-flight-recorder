"""Rule base class with counter-evidence support."""
from abc import ABC, abstractmethod
from typing import List, Optional

from nfr.models import Event, Finding
from nfr.models import EventType as ET


class Rule(ABC):
    """Base class for RCA rules."""

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def match(self, events: List[Event]) -> Optional[Finding]:
        ...

    def _find_first(self, events, etype, window_sec=10):
        for e in events:
            if e.type == etype:
                return e
        return None

    def _find_after(self, events, etype, after_ev, window_sec=10):
        if not after_ev:
            return None
        from datetime import timedelta
        start = after_ev.ts
        end = start + timedelta(seconds=window_sec)
        for e in events:
            if e.type == etype and start <= e.ts <= end:
                return e
        return None

    def _count_after(self, events, etype, after_ev, window_sec=10):
        if not after_ev:
            return 0
        from datetime import timedelta
        start = after_ev.ts
        end = start + timedelta(seconds=window_sec)
        return sum(1 for e in events
                   if e.type == etype and start <= e.ts <= end)

    def _find_in_window(self, events, etype, center_ev, before_sec, after_sec):
        if not center_ev:
            return None
        from datetime import timedelta
        start = center_ev.ts - timedelta(seconds=before_sec)
        end = center_ev.ts + timedelta(seconds=after_sec)
        for e in events:
            if e.type == etype and start <= e.ts <= end and e.id != center_ev.id:
                return e
        return None
