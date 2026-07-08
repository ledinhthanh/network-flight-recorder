"""Incident lifecycle builder.

Decides whether each event extends an open incident or starts a new one,
and when to close incidents. Recovery events close related incidents.
"""
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any

from nfr.incidents.models import Incident, IncidentSeverity, IncidentStatus, layer_of, RECOVERY_EVENTS, new_incident_id
from nfr.models import Event
from nfr.incidents.correlation import severity_for_events


# Events that indicate a problem (degrade service)
DEGRADING_TYPES = {
    "carrier_down", "ppp_lcp_timeout", "ppp_padt",
    "ppp_pado_timeout", "openwrt_wan_down",
    "gateway_unreachable", "route_deleted",
    "mce", "pcie_aer", "oom", "nic_reset",
    "dns_failure",
    "mac_flap",  # only if multiple - we'll handle below
    "bridge_topology_change",
}

# Severity ordering for comparison
SEV_ORDER = [IncidentSeverity.INFO, IncidentSeverity.NOTICE,
             IncidentSeverity.WARNING, IncidentSeverity.CRITICAL]


def sev_index(sev: IncidentSeverity) -> int:
    return SEV_ORDER.index(sev)


def max_severity(a: IncidentSeverity, b: IncidentSeverity) -> IncidentSeverity:
    return a if sev_index(a) >= sev_index(b) else b


class IncidentBuilder:
    """Stateful: open incidents active, closed incidents persisted."""

    AUTOCLOSE_AFTER_SEC = 60
    MERGE_REOPEN_SEC = 120  # if new degrading event happens this soon after close, re-merge
    CRITICAL_AFTER_SEC = 120
    MATCH_WINDOW_SEC = 30  # active correlation window for normal events
    RECOVERY_WINDOW_SEC = 3600  # window for recovery to close old incidents (1 hour)

    def __init__(self):
        self._active: Dict[str, Incident] = {}
        self._closed: List[Incident] = []
        self._lock = threading.Lock()
        self._on_open: List[Callable[[Incident], None]] = []
        self._on_close: List[Callable[[Incident], None]] = []
        # Track MAC flap count separately to avoid noise
        self._mac_flap_window: List[datetime] = []

    def on_incident_open(self, cb: Callable[[Incident], None]) -> None:
        self._on_open.append(cb)

    def on_incident_close(self, cb: Callable[[Incident], None]) -> None:
        self._on_close.append(cb)

    def active_incidents(self) -> List[Incident]:
        with self._lock:
            return list(self._active.values())

    def all_incidents(self) -> List[Incident]:
        with self._lock:
            return list(self._active.values()) + list(self._closed)

    def process(self, event: Event) -> Optional[Incident]:
        """Process one event. Returns incident if affected (open or closed)."""
        et = event.type.value
        # Suppress noise: 1 MAC flap alone isn't an incident
        if et == "mac_flap":
            self._mac_flap_window.append(event.ts)
            cutoff = event.ts - timedelta(seconds=300)
            self._mac_flap_window = [t for t in self._mac_flap_window if t >= cutoff]
            if len(self._mac_flap_window) < 3:
                return None  # suppress

        with self._lock:
            # Try to match an active incident first
            match = self._find_match(event)
            if match is not None:
                return self._extend(match, event)

            # Open new incident only for degrading events
            if et not in DEGRADING_TYPES:
                return None
            # Check recently-closed incidents for same-layer re-open
            for inc in reversed(self._closed[-5:]):
                gap = (event.ts - (inc.end_ts or event.ts)).total_seconds()
                if gap < 0 or gap > self.MERGE_REOPEN_SEC:
                    continue
                layer = layer_of(event.type.value)
                if layer in inc.layers_affected:
                    # Re-open this incident
                    inc.status = IncidentStatus.OPEN
                    inc.end_ts = None
                    inc.event_ids.append(event.id)
                    inc.raw_event_count += 1
                    inc.last_event_ts = event.ts
                    if layer not in inc.layers_affected:
                        inc.layers_affected.append(layer)
                    self._active[inc.id] = inc
                    return inc
            return self._open_incident(event)

    def sweep_timeouts(self, now: Optional[datetime] = None) -> List[Incident]:
        """Close incidents that have been quiet for too long."""
        now = now or datetime.now()
        closed_now: List[Incident] = []
        with self._lock:
            for inc in list(self._active.values()):
                if inc.last_event_ts is None:
                    continue
                gap = (now - inc.last_event_ts).total_seconds()
                if gap >= self.AUTOCLOSE_AFTER_SEC:
                    self._close_locked(inc)
                    closed_now.append(inc)
        for inc in closed_now:
            self._notify_close(inc)
        return closed_now

    def _find_match(self, event: Event) -> Optional[Incident]:
        et = event.type.value
        is_recovery = et in RECOVERY_EVENTS.values()
        window = self.RECOVERY_WINDOW_SEC if is_recovery else self.MATCH_WINDOW_SEC
        candidates = []
        for inc in self._active.values():
            if inc.last_event_ts is None:
                continue
            dt = (event.ts - inc.last_event_ts).total_seconds()
            if dt < 0 or dt > window:
                continue
            layer = layer_of(et)
            if layer in inc.layers_affected or "physical" in inc.layers_affected:
                candidates.append((inc.last_event_ts, inc))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _extend(self, inc: Incident, event: Event) -> Incident:
        inc.event_ids.append(event.id)
        inc.raw_event_count += 1
        inc.last_event_ts = event.ts
        layer = layer_of(event.type.value)
        if layer not in inc.layers_affected:
            inc.layers_affected.append(layer)
        et = event.type.value
        if et not in inc.key_event_types:
            inc.key_event_types.append(et)
        # Severity bump
        new_sev = severity_for_events(event)
        inc.severity = max_severity(inc.severity, new_sev)
        # Duration escalation
        elapsed = (event.ts - inc.start_ts).total_seconds()
        if elapsed >= self.CRITICAL_AFTER_SEC:
            inc.severity = IncidentSeverity.CRITICAL
        inc.impact_seconds = elapsed
        # Check recovery
        if self._is_recovery(inc, event):
            self._close_locked(inc)
            self._notify_close(inc)
        return inc

    def _is_recovery(self, inc: Incident, event: Event) -> bool:
        et = event.type.value
        for deg in inc.key_event_types:
            rec = RECOVERY_EVENTS.get(deg)
            if rec and rec == et and layer_of(et) == layer_of(deg):
                return True
        return False

    def _open_incident(self, event: Event) -> Incident:
        layer = layer_of(event.type.value)
        inc = Incident(
            id=new_incident_id(event.ts),
            start_ts=event.ts,
            last_event_ts=event.ts,
            status=IncidentStatus.OPEN,
            severity=severity_for_events(event),
            layers_affected=[layer],
            event_ids=[event.id],
            key_event_types=[event.type.value],
            raw_event_count=1,
        )
        self._active[inc.id] = inc
        self._notify_open(inc)
        return inc

    def _close_locked(self, inc: Incident) -> None:
        inc.status = IncidentStatus.CLOSED
        inc.end_ts = inc.last_event_ts or datetime.now()
        self._active.pop(inc.id, None)
        self._closed.append(inc)

    def _notify_open(self, inc: Incident) -> None:
        for cb in self._on_open:
            try:
                cb(inc)
            except Exception:
                pass

    def _notify_close(self, inc: Incident) -> None:
        for cb in self._on_close:
            try:
                cb(inc)
            except Exception:
                pass
