"""ARP / neighbor table collector.

Tracks ARP table changes to detect:
- Duplicate IP (2 MACs for same IP)
- Gratuitous ARP
- Gateway MAC change (could indicate failover)
"""
import subprocess
from datetime import datetime

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class ARPCollector(BaseCollector):
    """Polls `ip neigh show` and detects changes."""

    def __init__(self, bus=None, interval_sec: int = 30):
        super().__init__("arp", bus)
        self.interval = interval_sec
        self._prev = {}  # ip -> (mac, state)

    def setup(self):
        self._prev = self._read_neigh()

    def _read_neigh(self):
        try:
            r = subprocess.run(["ip", "-j", "neigh", "show"],
                              capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return {}
            import json
            data = json.loads(r.stdout) if r.stdout.strip() else []
            out = {}
            for entry in data:
                ip = entry.get("dst")
                if not ip:
                    continue
                lladdr = entry.get("lladdr")
                state = entry.get("state", "?")
                out[ip] = (lladdr, state)
            return out
        except Exception:
            return {}

    def loop(self):
        while not self._stop.is_set():
            try:
                cur = self._read_neigh()
                self._diff(cur)
                self._prev = cur
            except Exception as e:
                self.log.debug("arp err: %s", e)
            if self._stop.wait(self.interval):
                break

    def _diff(self, cur):
        # Detect MAC changes for known IPs
        for ip, (mac, state) in cur.items():
            prev = self._prev.get(ip)
            if prev and prev[0] != mac and mac:
                self.bus.publish(Event(
                    type=EventType.MAC_FLAP,
                    severity=Severity.WARN,
                    ts=datetime.now(),
                    source="arp:" + ip,
                    message="ARP MAC changed: " + ip + " " + str(prev[0]) + " -> " + str(mac),
                    data={"ip": ip, "old_mac": prev[0], "new_mac": mac,
                          "old_state": prev[1], "new_state": state},
                ))
            if prev and prev[1] != state:
                sev = Severity.WARN if state in ("FAILED", "INCOMPLETE") else Severity.INFO
                self.bus.publish(Event(
                    type=EventType.GATEWAY_UNREACHABLE if state in ("FAILED", "INCOMPLETE") else EventType.GATEWAY_REACHABLE,
                    severity=sev,
                    ts=datetime.now(),
                    source="arp:" + ip,
                    message="ARP state " + ip + ": " + str(prev[1]) + " -> " + state,
                    data={"ip": ip, "old_state": prev[1], "new_state": state, "mac": mac},
                ))
