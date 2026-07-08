"""Async event bus between collectors and analyzers."""
import threading
from queue import Queue, Empty
from typing import Callable, List

from nfr.models import Event
from nfr.constants import EVENTBUS_QUEUE_SIZE


class EventBus:
    """Thread-safe pub/sub for events."""

    def __init__(self, maxsize: int = EVENTBUS_QUEUE_SIZE):
        self._queue: Queue = Queue(maxsize=maxsize)
        self._subscribers: List[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def publish(self, event: Event) -> None:
        try:
            self._queue.put_nowait(event)
        except Exception:
            pass

    def subscribe(self, cb: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(cb)

    def run(self) -> None:
        """Consume events and dispatch to subscribers. Blocking."""
        while not self._stop.is_set():
            try:
                ev = self._queue.get(timeout=1.0)
            except Empty:
                continue
            with self._lock:
                subs = list(self._subscribers)
            for cb in subs:
                try:
                    cb(ev)
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop.set()
