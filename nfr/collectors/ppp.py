"""PPPoE collector via pppd journal."""
import re
import time
import subprocess
from datetime import datetime
from typing import Optional

from nfr.collectors.base import BaseCollector
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class PPPCollector(BaseCollector):
    """Tracks PPPoE session state from systemd journal (pppd)."""

    LCP_TIMEOUT = re.compile(r"(LCP|peer) not responding|LCP: timeout", re.I)
    PADT = re.compile(r"PAD[TO]|terminating", re.I)
    PADO = re.compile(r"PAD[OIO]|timeout", re.I)
    CONNECTED = re.compile(r"Connect(?:ing|ed).*(\d+\.\d+\.\d+\.\d+)|local.*IP.*(\d+\.\d+\.\d+\.\d+)", re.I)
    DISCONNECTED = re.compile(r"Disconnected|Connection terminated|peer hangup", re.I)

    def __init__(self, bus: EventBus = None):
        super().__init__("ppp", bus)
        self._last_log_ts: Optional[str] = None

    def setup(self):
        pass

    def loop(self):
        while not self._stop.is_set():
            try:
                self._poll_journal()
            except Exception as e:
                self.log.debug("ppp poll failed: %s", e)
            if self._stop.wait(5.0):
                break

    def _poll_journal(self):
        # tail pppd messages since last poll
        cmd = ["journalctl", "-u", "pppd", "--since", "1 minute ago",
               "-o", "short", "--no-pager"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception:
            return
        if r.returncode != 0 or not r.stdout:
            return
        for line in r.stdout.splitlines():
            self._parse(line)

    def _parse(self, line: str):
        if self.LCP_TIMEOUT.search(line):
            self._emit(EventType.PPP_LCP_TIMEOUT, Severity.ERROR, line)
        elif self.PADT.search(line):
            self._emit(EventType.PPP_PADT, Severity.WARN, line)
        elif self.PADO.search(line) and "timeout" in line.lower():
            self._emit(EventType.PPP_PADO_TIMEOUT, Severity.WARN, line)
        elif self.CONNECTED.search(line):
            self._emit(EventType.PPP_CONNECTED, Severity.INFO, line)
        elif self.DISCONNECTED.search(line):
            self._emit(EventType.PPP_PADT, Severity.WARN, line)

    def _emit(self, et: EventType, sev: Severity, raw: str):
        self.bus.publish(Event(
            type=et, severity=sev, ts=datetime.now(),
            source="ppp", message=raw[:200],
            data={"raw": raw[:500]},
        ))
