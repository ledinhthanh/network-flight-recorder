"""Periodic snapshot for trend analysis."""
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from nfr.models import Event, EventType, Severity
from nfr.constants import SNAPSHOT_INTERVAL_SEC, STORAGE_LOGS


class SnapshotService:
    def __init__(self, interval_sec: int = SNAPSHOT_INTERVAL_SEC,
                 providers: dict = None):
        self.interval = interval_sec
        self.providers = providers or {}
        self._stop = threading.Event()
        self._thread = None
        self._cb = None

    def on_snapshot(self, cb: Callable[[Event], None]):
        self._cb = cb

    def start(self):
        self._thread = threading.Thread(target=self._run, name="nfr-snapshot", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            self._take_snapshot()
            if self._stop.wait(self.interval):
                break

    def _take_snapshot(self):
        data = {}
        for name, provider in self.providers.items():
            try:
                data[name] = provider()
            except Exception:
                data[name] = None
        ev = Event(
            type=EventType.SNAPSHOT,
            severity=Severity.INFO,
            ts=datetime.now(),
            source="snapshot",
            message="periodic snapshot",
            data=data,
        )
        if self._cb:
            try:
                self._cb(ev)
            except Exception:
                pass


def nic_stats_provider():
    """Read NIC error counters for trend."""
    from pathlib import Path
    out = {}
    for p in Path("/sys/class/net").iterdir():
        name = p.name
        if name == "lo" or name.startswith(("veth", "fw", "vmbr", "br-")):
            continue
        stats_dir = p / "statistics"
        if not stats_dir.exists():
            continue
        try:
            rx_err = int((stats_dir / "rx_errors").read_text().strip()) if (stats_dir / "rx_errors").exists() else 0
            tx_err = int((stats_dir / "tx_errors").read_text().strip()) if (stats_dir / "tx_errors").exists() else 0
            rx_drop = int((stats_dir / "rx_dropped").read_text().strip()) if (stats_dir / "rx_dropped").exists() else 0
            carrier_changes = 0
            cc = p / "carrier_changes"
            if cc.exists():
                try:
                    carrier_changes = int(cc.read_text().strip())
                except ValueError:
                    carrier_changes = 0
            out[name] = {"rx_err": rx_err, "tx_err": tx_err, "rx_drop": rx_drop, "carrier_changes": carrier_changes}
        except (ValueError, OSError):
            continue
    return out


def host_stats_provider():
    """Basic host stats."""
    import psutil
    return {
        "load": psutil.getloadavg(),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "mem_percent": psutil.virtual_memory().percent,
    }
