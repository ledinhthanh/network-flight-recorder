"""OpenWrt collector via SSH (read-only)."""
import subprocess
import time
from datetime import datetime
from typing import Optional

from nfr.collectors.base import BaseCollector
from nfr.config import OpenWrtConfig
from nfr.core.eventbus import EventBus
from nfr.models import Event, EventType, Severity


class OpenWrtCollector(BaseCollector):
    """Connects to OpenWrt via SSH, polls logread and ifstatus."""

    def __init__(self, bus=None, cfg: Optional[OpenWrtConfig] = None,
                 ssh_pass: str = None):
        super().__init__("openwrt", bus)
        self.cfg = cfg or OpenWrtConfig()
        self.ssh_pass = ssh_pass
        self._ssh_failure_count = 0
        self._prev_wan_state = None
        self._seen_lines = set()

    def setup(self):
        self.log.info("openwrt target=%s port=%d", self.cfg.host, self.cfg.port)

    def loop(self):
        consecutive_failures = 0
        while not self._stop.is_set():
            try:
                self._poll()
                consecutive_failures = 0
            except Exception as e:
                consecutive_failures += 1
                self.log.debug("openwrt poll err (attempt %d): %s", consecutive_failures, e)
            # exponential backoff on failures
            wait = min(10.0 + consecutive_failures * 5, 60.0)
            if self._stop.wait(wait):
                break

    def _ssh(self, cmd):
        """Run command on OpenWrt via SSH."""
        self._ssh_failure_count += 1
        base = ["ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=3",
                "-o", "BatchMode=yes",
                "-p", str(self.cfg.port)]
        if self.cfg.ssh_key:
            base += ["-i", self.cfg.ssh_key]
        base += [self.cfg.user + "@" + self.cfg.host, cmd]
        try:
            r = subprocess.run(base, capture_output=True, text=True, timeout=5)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None

    def _poll(self):
        # WAN state
        out = self._ssh("ubus call network.interface.wan status 2>/dev/null | head -c 500")
        cur_state = "unknown"
        if out:
            UP_TRUE = chr(34) + "up" + chr(34) + chr(58) + " true"
            if UP_TRUE in out:
                cur_state = "up"
            elif UP_TRUE.replace("true", "false") in out:
                cur_state = "down"
        if cur_state != self._prev_wan_state:
            et = EventType.OPENWRT_WAN_UP if cur_state == "up" else EventType.OPENWRT_WAN_DOWN
            sev = Severity.INFO if cur_state == "up" else Severity.CRITICAL
            self.bus.publish(Event(
                type=et, severity=sev, ts=datetime.now(),
                source="openwrt:wan",
                message="WAN " + cur_state,
                data={"prev": self._prev_wan_state, "cur": cur_state},
                prev_state=self._prev_wan_state,
                new_state=cur_state,
            ))
            self._prev_wan_state = cur_state

        # logread (new lines)
        log_out = self._ssh("logread | tail -n 50")
        if log_out:
            for line in log_out.splitlines()[-20:]:
                if line not in self._seen_lines:
                    self._seen_lines.add(line)
                    if "pppd" in line.lower() or "lcp" in line.lower():
                        self._parse_pppd_line(line)

    def _parse_pppd_line(self, line):
        low = line.lower()
        if "lcp" in low and ("timeout" in low or "not responding" in low):
            self.bus.publish(Event(
                type=EventType.PPP_LCP_TIMEOUT, severity=Severity.ERROR,
                ts=datetime.now(), source="openwrt:pppd",
                message=line[:200], data={"raw": line[:500]},
            ))
        elif "terminating" in low or "hangup" in low:
            self.bus.publish(Event(
                type=EventType.PPP_PADT, severity=Severity.WARN,
                ts=datetime.now(), source="openwrt:pppd",
                message=line[:200], data={"raw": line[:500]},
            ))
