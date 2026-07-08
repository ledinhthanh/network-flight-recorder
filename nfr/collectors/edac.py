"""EDAC / MCE counter polling.

Tracks memory ECC errors (CE = correctable, UE = uncorrectable) and
Machine Check Exceptions to detect hardware degradation trends.
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class EDACCollector(BaseCollector):
    def __init__(self, bus=None, interval_sec: int = 60):
        super().__init__("edac", bus)
        self.interval = interval_sec
        self._prev = {}  # mcN -> {"ce": count, "ue": count}

    def setup(self):
        self._prev = self._read_counters()

    def _read_counters(self) -> Dict[str, Dict[str, int]]:
        out = {}
        base = Path("/sys/devices/system/edac/mc")
        if not base.exists():
            return out
        for mc in base.glob("mc*"):
            ce_f = mc / "ce_count"
            ue_f = mc / "ue_count"
            ce = 0
            ue = 0
            try:
                if ce_f.exists():
                    ce = int(ce_f.read_text().strip())
            except ValueError:
                pass
            try:
                if ue_f.exists():
                    ue = int(ue_f.read_text().strip())
            except ValueError:
                pass
            out[mc.name] = {"ce": ce, "ue": ue}
        return out

    def loop(self):
        while not self._stop.is_set():
            try:
                cur = self._read_counters()
                self._diff(cur)
                self._prev = cur
            except Exception as e:
                self.log.debug("edac err: %s", e)
            if self._stop.wait(self.interval):
                break

    def _diff(self, cur):
        for mc, counts in cur.items():
            prev = self._prev.get(mc, {"ce": 0, "ue": 0})
            d_ce = counts["ce"] - prev["ce"]
            d_ue = counts["ue"] - prev["ue"]
            if d_ue > 0:
                self.bus.publish(Event(
                    type=EventType.MCE,
                    severity=Severity.CRITICAL,
                    ts=datetime.now(),
                    source="edac:" + mc,
                    message="Uncorrectable ECC error: +" + str(d_ue) + " on " + mc,
                    data={"mc": mc, "delta_ue": d_ue, "total_ue": counts["ue"]},
                ))
            elif d_ce > 0:
                # Correctable - emit only if rate is concerning (>10 per poll)
                if d_ce > 10:
                    self.bus.publish(Event(
                        type=EventType.SNAPSHOT,
                        severity=Severity.WARN,
                        ts=datetime.now(),
                        source="edac:" + mc,
                        message="High CE rate: +" + str(d_ce) + " on " + mc,
                        data={"mc": mc, "delta_ce": d_ce, "total_ce": counts["ce"],
                              "diagnosis": "Possible memory degradation - monitor closely"},
                    ))
