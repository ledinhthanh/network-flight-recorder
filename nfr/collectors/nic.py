"""NIC state collector - extended with PHY error tracking."""
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.core.flap_detector import FlapDetector
from nfr.models import Event, EventType, Severity


class NICCollector(BaseCollector):
    """Tracks NIC link state + PHY errors + carrier_changes counter."""

    def __init__(self, bus: EventBus = None, interfaces=None,
                 phy_threshold: int = 100, flap_detector=None):
        super().__init__("nic", bus)
        self.interfaces = interfaces or self._discover_interfaces()
        self._prev_state = {}
        self._prev_counters = {}  # for delta detection
        self.phy_threshold = phy_threshold
        self.flap_detector = flap_detector or FlapDetector()  # errors/sec to alert

    @staticmethod
    def _discover_interfaces():
        out = []
        for p in sorted(Path("/sys/class/net").iterdir()):
            name = p.name
            if name == "lo":
                continue
            if name.startswith(("veth", "fw", "vmbr", "br-")):
                continue
            out.append(name)
        return out

    def setup(self):
        for iface in self.interfaces:
            self._prev_state[iface] = self._read_state(iface)
            self._prev_counters[iface] = self._read_counters(iface)

    def _read_state(self, iface):
        base = Path("/sys/class/net") / iface
        if not base.exists():
            return {}
        st = {"carrier": self._read_carrier(base)}
        op = base / "operstate"
        if op.exists():
            st["operstate"] = op.read_text().strip()
        sp = base / "speed"
        if sp.exists():
            st["speed"] = sp.read_text().strip()
        # carrier_changes counter
        cc = base / "carrier_changes"
        if cc.exists():
            try:
                st["carrier_changes"] = int(cc.read_text().strip())
            except ValueError:
                st["carrier_changes"] = 0
        return st

    @staticmethod
    def _read_carrier(base):
        f = base / "carrier"
        if not f.exists():
            return 0
        try:
            return int(f.read_text().strip())
        except ValueError:
            return 0

    def _read_counters(self, iface):
        """Read PHY error counters."""
        stats_dir = Path("/sys/class/net") / iface / "statistics"
        if not stats_dir.exists():
            return {}
        out = {}
        keys = ["rx_crc_errors", "rx_symbol_errors", "rx_frame_errors",
                "rx_length_errors", "tx_carrier_errors", "tx_aborted_errors",
                "rx_dropped", "tx_dropped", "rx_errors", "tx_errors",
                "multicast", "collisions"]
        for k in keys:
            f = stats_dir / k
            if f.exists():
                try:
                    out[k] = int(f.read_text().strip())
                except ValueError:
                    pass
        return out

    def loop(self):
        import time
        while not self._stop.is_set():
            for iface in self.interfaces:
                try:
                    cur_state = self._read_state(iface)
                    cur_counters = self._read_counters(iface)
                    prev_state = self._prev_state.get(iface, {})
                    prev_counters = self._prev_counters.get(iface, {})
                    self._diff(iface, prev_state, cur_state)
                    self._diff_counters(iface, cur_counters, prev_counters)
                    self._prev_state[iface] = cur_state
                    self._prev_counters[iface] = cur_counters
                except Exception as e:
                    self.log.debug("read %s failed: %s", iface, e)
            if self._stop.wait(5.0):
                break

    def _diff(self, iface, prev, cur):
        prev_carrier = prev.get("carrier", 0)
        cur_carrier = cur.get("carrier", 0)
        if prev_carrier != cur_carrier:
            self._emit_carrier(iface, prev_carrier, cur_carrier, cur)

    def _diff_counters(self, iface, cur, prev):
        """Detect PHY error increments."""
        delta_crc = cur.get("rx_crc_errors", 0) - prev.get("rx_crc_errors", 0)
        delta_symbol = cur.get("rx_symbol_errors", 0) - prev.get("rx_symbol_errors", 0)
        delta_frame = cur.get("rx_frame_errors", 0) - prev.get("rx_frame_errors", 0)
        if delta_crc > 0 or delta_symbol > 0 or delta_frame > 0:
            self._emit_phy_error(iface, cur, prev, delta_crc, delta_symbol, delta_frame)

    def _emit_carrier(self, iface, prev_carrier, cur_carrier, cur):
        if cur_carrier == 0:
            et, sev, st = EventType.CARRIER_DOWN, Severity.CRITICAL, "DOWN"
        else:
            et, sev, st = EventType.CARRIER_UP, Severity.INFO, "UP"
        self.bus.publish(Event(
            type=et, severity=sev, ts=datetime.now(),
            source="nic:" + iface,
            message=iface + " carrier " + st,
            data={
                "interface": iface,
                "speed": cur.get("speed"),
                "operstate": cur.get("operstate"),
                "carrier_changes_total": cur.get("carrier_changes", 0),
            },
            prev_state="UP" if prev_carrier else "DOWN",
            new_state=st,
        ))
        # Trigger flap analysis
        flap_ev = self.flap_detector.record(self.bus._queue.queue[-1] if False else None)
        # Use the actual event we just published
        # Reconstruct a minimal event for the flap detector (it only needs type, ts, data, new_state)
        flap_input = type("E", (), {
            "type": et, "ts": __import__("datetime").datetime.now(),
            "data": cur, "new_state": st
        })()
        flap_ev = self.flap_detector.record(flap_input)
        if flap_ev:
            self.bus.publish(flap_ev)

    def _emit_phy_error(self, iface, cur, prev, d_crc, d_sym, d_frame):
        self.bus.publish(Event(
            type=EventType.PHY_ERROR,
            severity=Severity.WARN,
            ts=datetime.now(),
            source="nic:" + iface,
            message=("%s PHY errors: +%d CRC, +%d symbol, +%d frame" % (iface, d_crc, d_sym, d_frame)),
            data={
                "interface": iface,
                "delta_crc": d_crc,
                "delta_symbol": d_sym,
                "delta_frame": d_frame,
                "total_crc": cur.get("rx_crc_errors", 0),
                "total_symbol": cur.get("rx_symbol_errors", 0),
                "total_frame": cur.get("rx_frame_errors", 0),
            },
        ))
