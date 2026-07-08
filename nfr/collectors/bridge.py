"""Bridge collector: FDB, MAC flap, STP state, broadcast storm detection."""
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class BridgeCollector(BaseCollector):
    """Tracks bridge state, FDB changes, STP topology, broadcast rate."""

    def __init__(self, bus=None, storm_threshold_pps: int = 5000):
        super().__init__("bridge", bus)
        self._prev_fdb = {}
        self._prev_stp = {}
        self._prev_rx_pkts = {}
        self.storm_threshold = storm_threshold_pps
        self._storm_history = {}  # bridge -> deque of (ts, pps)

    @staticmethod
    def _bridges():
        out = []
        for p in Path("/sys/class/net").iterdir():
            if p.name.startswith(("vmbr", "br-", "fwbr")):
                out.append(p.name)
        return out

    def setup(self):
        for b in self._bridges():
            self._prev_fdb[b] = self._read_fdb(b)
            self._prev_stp[b] = self._read_stp_state(b)
            self._prev_rx_pkts[b] = self._read_rx_packets(b)
            self._storm_history[b] = deque(maxlen=20)

    def _read_fdb(self, bridge):
        f = Path("/sys/class/net") / bridge / "brforward"
        if not f.exists():
            return {}
        out = {}
        try:
            for line in f.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 6:
                    mac = parts[2] if len(parts[2]) == 17 else parts[1]
                    port = parts[-2] if len(parts) >= 7 else parts[-1]
                    out[mac] = port
        except Exception:
            pass
        return out

    def _read_stp_state(self, bridge):
        stp = Path("/sys/class/net") / bridge / "bridge/stp_state"
        if stp.exists():
            try:
                return int(stp.read_text().strip())
            except ValueError:
                return 0
        return 0

    def _read_rx_packets(self, bridge):
        f = Path("/sys/class/net") / bridge / "statistics/rx_packets"
        if f.exists():
            try:
                return int(f.read_text().strip())
            except ValueError:
                return 0
        return 0

    def loop(self):
        while not self._stop.is_set():
            try:
                for b in self._bridges():
                    cur_fdb = self._read_fdb(b)
                    prev_fdb = self._prev_fdb.get(b, {})
                    for mac, port in cur_fdb.items():
                        if mac in prev_fdb and prev_fdb[mac] != port:
                            self.bus.publish(Event(
                                type=EventType.MAC_FLAP,
                                severity=Severity.WARN,
                                ts=datetime.now(),
                                source="bridge:" + b,
                                message="MAC moved: " + mac + " " + str(prev_fdb[mac]) + " -> " + str(port),
                                data={"bridge": b, "mac": mac, "old_port": prev_fdb[mac], "new_port": port},
                            ))
                    self._prev_fdb[b] = cur_fdb

                    # STP state changes
                    cur_stp = self._read_stp_state(b)
                    prev_stp = self._prev_stp.get(b, 0)
                    if prev_stp and prev_stp != cur_stp:
                        sev = Severity.WARN
                        self.bus.publish(Event(
                            type=EventType.BRIDGE_TOPOLOGY_CHANGE,
                            severity=sev,
                            ts=datetime.now(),
                            source="bridge:" + b,
                            message=b + " STP state changed: " + str(prev_stp) + " -> " + str(cur_stp),
                            data={"bridge": b, "old_stp": prev_stp, "new_stp": cur_stp},
                        ))
                    self._prev_stp[b] = cur_stp

                    # Broadcast rate
                    cur_rx = self._read_rx_packets(b)
                    prev_rx = self._prev_rx_pkts.get(b, cur_rx)
                    elapsed = 10.0
                    delta = cur_rx - prev_rx
                    pps = delta / elapsed
                    self._prev_rx_pkts[b] = cur_rx
                    if pps > self.storm_threshold:
                        self.bus.publish(Event(
                            type=EventType.BRIDGE_TOPOLOGY_CHANGE,
                            severity=Severity.WARN,
                            ts=datetime.now(),
                            source="bridge:" + b,
                            message=b + " high RX rate: " + str(int(pps)) + " pps",
                            data={"bridge": b, "pps": pps},
                        ))
            except Exception as e:
                self.log.debug("bridge err: %s", e)
            if self._stop.wait(10.0):
                break
