"""PMTU active probe using ping with DF bit."""

import subprocess
import time
from datetime import datetime

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class PMTUCollector(BaseCollector):
    """Discovers Path MTU by sending DF-bit pings of increasing size.

    When ping with -M do returns message too long or frag needed,
    we have discovered the MTU ceiling.
    """

    DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1"]
    # Common MTU sizes to probe (descending)
    PROBE_SIZES = [1500, 1492, 1480, 1460, 1400, 1280]

    def __init__(self, bus=None, targets=None,
                 interval_sec: int = 600, timeout_sec: int = 5):
        super().__init__("pmtu", bus)
        self.targets = targets or self.DEFAULT_TARGETS
        self.interval = interval_sec
        self.timeout = timeout_sec
        self._prev_mtu = None

    def setup(self):
        self._prev_mtu = self._probe_mtu(self.targets[0])

    def _probe_mtu(self, target: str) -> int:
        """Returns the largest unfragmented packet size that succeeds, or 0."""
        for size in self.PROBE_SIZES:
            payload = size - 28  # subtract IP+ICMP headers
            try:
                cmd = ["ping", "-c", "1", "-W", str(self.timeout),
                       "-M", "do", "-s", str(payload), target]
                r = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self.timeout + 2)
                if r.returncode == 0:
                    return size
                # Check for frag-needed message
                if "frag needed" in (r.stdout + r.stderr).lower() or \
                   "message too long" in (r.stdout + r.stderr).lower() or \
                   "too big" in (r.stdout + r.stderr).lower():
                    return -size  # negative = MTU ceiling is below size
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        return 0

    def loop(self):
        while not self._stop.is_set():
            try:
                mtu = self._probe_mtu(self.targets[0])
                if mtu != self._prev_mtu:
                    self._emit_change(mtu)
                    self._prev_mtu = mtu
            except Exception as e:
                self.log.debug("pmtu err: %s", e)
            if self._stop.wait(self.interval):
                break

    def _emit_change(self, mtu):
        if mtu == 0:
            return
        if mtu > 0 and mtu < self.PROBE_SIZES[0]:
            self.bus.publish(Event(
                type=EventType.PHY_ERROR,
                severity=Severity.WARN,
                ts=datetime.now(),
                source="pmtu",
                message="Path MTU is " + str(mtu) + " (below standard 1500 - PMTU blackhole possible)",
                data={"mtu": mtu, "target": self.targets[0]},
            ))
        elif mtu < 0:
            self.bus.publish(Event(
                type=EventType.PHY_ERROR,
                severity=Severity.ERROR,
                ts=datetime.now(),
                source="pmtu",
                message="Frag-needed received for size " + str(-mtu) + " - ICMP MTU discovery issue",
                data={"mtu_blocked": -mtu, "target": self.targets[0]},
            ))
