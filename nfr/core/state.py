"""State machine: tracks per-resource state and emits transitions only."""
import threading
from datetime import datetime
from typing import Dict, Optional, Callable, List

from nfr.models import Event, EventType, Severity, ResourceState


class StateStore:
    """Per-resource state tracking."""

    def __init__(self):
        self._states: Dict[str, ResourceState] = {}
        self._lock = threading.Lock()
        self._transitions: List[Event] = []
        self._listeners: List[Callable[[Event], None]] = []

    def on_transition(self, cb: Callable[[Event], None]):
        self._listeners.append(cb)

    def get(self, key: str) -> Optional[ResourceState]:
        with self._lock:
            return self._states.get(key)

    def all_states(self) -> List[ResourceState]:
        with self._lock:
            return list(self._states.values())

    def set(self, key: str, resource_type: str, state: str,
            prev_state: str = None, extra: dict = None,
            source: str = "state", event_type: EventType = None,
            severity: Severity = Severity.INFO,
            message: str = None) -> Optional[Event]:
        """Set state, emit transition event if changed."""
        with self._lock:
            old = self._states.get(key)
            new = ResourceState(
                name=key,
                resource_type=resource_type,
                state=state,
                last_update=datetime.now(),
                extra=extra or {},
            )
            self._states[key] = new
            changed = (old is None or old.state != state)
        if changed and old is not None:
            et = event_type or EventType.SNAPSHOT
            ev = Event(
                type=et,
                severity=severity,
                ts=datetime.now(),
                source=source,
                message=message or f"{key}: {old.state} -> {state}",
                data={"resource": key, "type": resource_type, **(extra or {})},
                prev_state=old.state,
                new_state=state,
            )
            with self._lock:
                self._transitions.append(ev)
            for cb in self._listeners:
                try:
                    cb(ev)
                except Exception:
                    pass
            return ev
        return None

    def transitions(self) -> List[Event]:
        with self._lock:
            return list(self._transitions)

    def clear_transitions(self):
        with self._lock:
            self._transitions.clear()
