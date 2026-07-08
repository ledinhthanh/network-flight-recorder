"""Detects carrier flap patterns - distinguishes GPON from cable/NIC issues."""
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict

from nfr.models import Event, EventType, Severity


@dataclass
class FlapEvent:
    """Internal record of carrier state change."""
    ts: float
    new_state: str  # UP / DOWN
    iface: str


class FlapDetector:
    """Tracks carrier flap pattern per interface.

    Short-duration flaps (under threshold) repeating = likely GPON/ONT issue.
    Long single flaps = cable/NIC issue.
    """

    def __init__(self,
                 short_window_sec: float = 300.0,
                 short_flap_threshold: int = 3,
                 max_flaps_for_alert: int = 5):
        self.short_window = short_window_sec
        self.short_flap_threshold = short_flap_threshold
        self.max_alert = max_flaps_for_alert
        self._history: Dict[str, Deque[FlapEvent]] = {}
        self._reported_alerts = {}  # iface -> last alert ts

    def record(self, ev: Event) -> Event:
        """Record a carrier transition event. May emit flap pattern alert."""
        if ev.type not in (EventType.CARRIER_UP, EventType.CARRIER_DOWN):
            return None
        iface = ev.data.get("interface")
        if not iface:
            return None
        if iface not in self._history:
            self._history[iface] = deque(maxlen=64)
        now = time.time()
        self._history[iface].append(FlapEvent(
            ts=now,
            new_state=ev.new_state or ("UP" if ev.type == EventType.CARRIER_UP else "DOWN"),
            iface=iface,
        ))
        return self._analyze(iface, now)

    def _analyze(self, iface: str, now: float) -> Event:
        history = self._history.get(iface, deque())
        cutoff = now - self.short_window
        recent_flaps = [h for h in history if h.ts >= cutoff]
        flap_count = len(recent_flaps)
        if flap_count < self.short_flap_threshold:
            return None
        # Avoid duplicate alerts (within 5 minutes)
        last = self._reported_alerts.get(iface, 0)
        if now - last < 300:
            return None
        self._reported_alerts[iface] = now
        from datetime import datetime
        return Event(
            type=EventType.PHY_ERROR,  # use existing PHY_ERROR as flap signature
            severity=Severity.WARN,
            ts=datetime.now(),
            source="flap:" + iface,
            message=("%s: %d carrier transitions in %.0fs (likely GPON/ONT instability)" %
                     (iface, flap_count, self.short_window)),
            data={
                "interface": iface,
                "flap_count": flap_count,
                "window_sec": self.short_window,
                "signature": "rapid_flap",
                "diagnosis": "Repeated short-duration carrier transitions - consistent with GPON/ONT optical instability downstream of NIC",
            },
        )
