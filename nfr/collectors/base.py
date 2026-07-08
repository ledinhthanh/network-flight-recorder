"""Base collector."""
import abc
import threading
from typing import Optional

from nfr.core.eventbus import EventBus
from nfr.logging_setup import setup_logging


class BaseCollector(abc.ABC):
    """Base class for collectors."""

    def __init__(self, name: str, bus: Optional[EventBus] = None):
        self.name = name
        self.bus = bus or EventBus()
        self.log = setup_logging().getChild(f"collector.{name}")
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @abc.abstractmethod
    def setup(self) -> None:
        """Initialize resources."""

    @abc.abstractmethod
    def loop(self) -> None:
        """Main collection loop. Called in a thread."""

    def start(self) -> None:
        self.log.info("starting")
        self.setup()
        self._thread = threading.Thread(target=self._safe_loop, name=f"nfr-{self.name}", daemon=True)
        self._thread.start()

    def _safe_loop(self) -> None:
        try:
            self.loop()
        except Exception as e:
            self.log.exception("loop crashed: %s", e)

    def stop(self) -> None:
        self.log.info("stopping")
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
