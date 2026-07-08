"""Host collector: SMART, thermal, sensors, VM state, kernel events."""
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class HostCollector(BaseCollector):
    """Tracks SMART, thermal, VM/container state."""

    MCE_RE = re.compile(r"Machine Check|mce:|Hardware Error", re.I)
    OOM_RE = re.compile(r"Out of memory|Killed process", re.I)
    SOFTLOCKUP_RE = re.compile(r"soft lockup", re.I)
    HUNG_RE = re.compile(r"hung_task_timeout|blocked for more than", re.I)
    NETDEV_WD_RE = re.compile(r"NETDEV WATCHDOG", re.I)
    PCIE_AER_RE = re.compile(r"pcieport|AER|pcie aer", re.I)
    PCIE_CORR_RE = re.compile(r"Corrected.*error|bad TLP", re.I)

    def __init__(self, bus=None):
        super().__init__("host", bus)
        self._prev_lxc = {}

    def setup(self):
        pass

    def loop(self):
        while not self._stop.is_set():
            try:
                self._check_journal()
                self._check_thermal()
                self._check_lxc()
            except Exception as e:
                self.log.debug("host err: %s", e)
            if self._stop.wait(15.0):
                break

    def _check_journal(self):
        cmd = ["journalctl", "-k", "--since", "30 seconds ago", "-o", "short", "--no-pager"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:
            return
        if r.returncode != 0 or not r.stdout:
            return
        for line in r.stdout.splitlines():
            self._parse_kmsg(line)

    def _parse_kmsg(self, line):
        if self.PCIE_AER_RE.search(line):
            sev = Severity.ERROR if self.PCIE_CORR_RE.search(line) else Severity.WARN
            self._emit(EventType.PCIE_AER, sev, line)
        elif self.MCE_RE.search(line):
            self._emit(EventType.MCE, Severity.CRITICAL, line)
        elif self.OOM_RE.search(line):
            self._emit(EventType.OOM, Severity.CRITICAL, line)
        elif self.SOFTLOCKUP_RE.search(line):
            self._emit(EventType.KERNEL_SOFT_LOCKUP, Severity.ERROR, line)
        elif self.HUNG_RE.search(line):
            self._emit(EventType.KERNEL_HUNG_TASK, Severity.ERROR, line)
        elif self.NETDEV_WD_RE.search(line):
            self._emit(EventType.NETDEV_WATCHDOG, Severity.ERROR, line)

    def _check_thermal(self):
        out = {}
        for tz in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                v = int(tz.read_text().strip())
                out[tz.parent.name] = v // 1000
            except Exception:
                continue
        # passive detection of thermal events
        for name, t in out.items():
            if t > 90:
                self.bus.publish(Event(
                    type=EventType.SNAPSHOT, severity=Severity.WARN,
                    ts=datetime.now(), source="thermal",
                    message="thermal zone " + name + " at " + str(t) + "C",
                    data={"zone": name, "temp_c": t},
                ))

    def _check_lxc(self):
        try:
            r = subprocess.run(["pct", "list", "-o", "json", "2>/dev/null"],
                              capture_output=True, text=True, timeout=5, shell=True)
            if r.returncode != 0 or not r.stdout.strip():
                return
            import json as _json
            current = {ct["vmid"]: ct["status"] for ct in _json.loads(r.stdout)}
            for vmid, status in current.items():
                prev = self._prev_lxc.get(vmid)
                if prev and prev != status:
                    if status == "running":
                        et = EventType.VM_STOP if prev == "stopped" else EventType.SNAPSHOT
                        sev = Severity.INFO
                    else:
                        et = EventType.VM_STOP
                        sev = Severity.WARN
                    self.bus.publish(Event(
                        type=et, severity=sev, ts=datetime.now(),
                        source="lxc:" + str(vmid),
                        message="LXC " + str(vmid) + " " + prev + " -> " + status,
                        data={"vmid": vmid, "prev": prev, "cur": status},
                    ))
            self._prev_lxc = current
        except Exception:
            return

    def _emit(self, et, sev, raw):
        self.bus.publish(Event(
            type=et, severity=sev, ts=datetime.now(),
            source="kernel", message=raw[:200], data={"raw": raw[:500]},
        ))
