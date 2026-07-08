"""Route collector: default gateway + route changes."""
import subprocess
from datetime import datetime

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class RouteCollector(BaseCollector):
    """Tracks default route and gateway reachability."""

    def __init__(self, bus=None):
        super().__init__("route", bus)
        self._prev_default = None

    def setup(self):
        self._prev_default = self._default_route()

    def _default_route(self):
        try:
            r = subprocess.run(["ip", "route", "show", "default"],
                              capture_output=True, text=True, timeout=3)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None

    def loop(self):
        while not self._stop.is_set():
            try:
                cur = self._default_route()
                if cur != self._prev_default:
                    et = EventType.ROUTE_ADDED if cur and not self._prev_default else EventType.ROUTE_DELETED
                    sev = Severity.WARN if et == EventType.ROUTE_DELETED else Severity.INFO
                    self.bus.publish(Event(
                        type=et, severity=sev, ts=datetime.now(),
                        source="route",
                        message="default route changed",
                        data={"prev": self._prev_default, "cur": cur},
                    ))
                    self._prev_default = cur
            except Exception as e:
                self.log.debug("route err: %s", e)
            if self._stop.wait(5.0):
                break

    def ping_gateway(self):
        try:
            r = subprocess.run(["ping", "-c", "1", "-W", "2", "1.1.1.1"],
                              capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False
