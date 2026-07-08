"""DNS active probe - resolves via multiple resolvers and detects failures."""
import socket
import subprocess
import time
from datetime import datetime
from typing import List

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class DNSCollector(BaseCollector):
    """Active probe DNS resolution.

    Probes multiple resolvers to distinguish:
    - Local resolver issue
    - Upstream resolver issue (8.8.8.8 down)
    - Network unreachable (timeout)
    """

    DEFAULT_RESOLVERS = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]
    DEFAULT_TARGETS = ["google.com", "cloudflare.com", "github.com"]

    def __init__(self, bus=None, resolvers=None, targets=None,
                 timeout_sec: float = 3.0, interval_sec: float = 60.0,
                 slow_threshold_ms: int = 200):
        super().__init__("dns", bus)
        self.resolvers = resolvers or self.DEFAULT_RESOLVERS
        self.targets = targets or self.DEFAULT_TARGETS
        self.timeout = timeout_sec
        self.interval = interval_sec
        self.slow_threshold = slow_threshold_ms
        self._last_state = {}  # (resolver, target) -> "ok" / "fail"

    def setup(self):
        pass

    def loop(self):
        while not self._stop.is_set():
            try:
                self._probe_all()
            except Exception as e:
                self.log.debug("dns err: %s", e)
            if self._stop.wait(self.interval):
                break

    def _probe_one(self, resolver: str, target: str) -> tuple:
        """Returns (state, latency_ms). state = ok/fail."""
        try:
            cmd = ["dig", "+short", "+time=" + str(int(self.timeout)),
                   "+tries=1", "@" + resolver, target]
            r = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=self.timeout + 2)
            if r.returncode != 0 or not r.stdout.strip():
                return ("fail", -1)
            return ("ok", self.timeout * 1000)  # approximate
        except subprocess.TimeoutExpired:
            return ("fail", -1)
        except Exception:
            return ("fail", -1)

    def _probe_all(self):
        for resolver in self.resolvers:
            ok_count = 0
            fail_count = 0
            for target in self.targets:
                state, _ = self._probe_one(resolver, target)
                if state == "ok":
                    ok_count += 1
                else:
                    fail_count += 1
            prev = self._last_state.get(resolver, "ok")
            new_state = "ok" if fail_count == 0 else ("partial" if ok_count > 0 else "fail")
            self._last_state[resolver] = new_state
            if new_state == prev:
                continue
            if new_state == "ok":
                self.bus.publish(Event(
                    type=EventType.DNS_FAILURE,
                    severity=Severity.INFO,
                    ts=datetime.now(),
                    source="dns:" + resolver,
                    message="DNS recovered for " + resolver,
                    data={"resolver": resolver, "state": new_state},
                    prev_state=prev,
                    new_state=new_state,
                ))
            elif new_state == "fail":
                self.bus.publish(Event(
                    type=EventType.DNS_FAILURE,
                    severity=Severity.CRITICAL,
                    ts=datetime.now(),
                    source="dns:" + resolver,
                    message="DNS unreachable via " + resolver,
                    data={"resolver": resolver, "state": new_state,
                          "ok": ok_count, "fail": fail_count},
                    prev_state=prev,
                    new_state=new_state,
                ))
            elif new_state == "partial":
                self.bus.publish(Event(
                    type=EventType.DNS_FAILURE,
                    severity=Severity.WARN,
                    ts=datetime.now(),
                    source="dns:" + resolver,
                    message="DNS partial: " + str(ok_count) + "/" + str(len(self.targets)) + " via " + resolver,
                    data={"resolver": resolver, "state": new_state,
                          "ok": ok_count, "fail": fail_count},
                    prev_state=prev,
                    new_state=new_state,
                ))
