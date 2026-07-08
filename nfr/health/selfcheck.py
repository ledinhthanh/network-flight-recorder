"""Self-health check for NFR collectors."""
import psutil
import time
import threading
from datetime import datetime
from pathlib import Path

from nfr.constants import RAM_BUDGET_MB


class SelfHealth:
    def __init__(self):
        self.start_time = time.time()
        self.collector_heartbeats = {}
        self._alert_callbacks = []

    def on_alert(self, cb):
        self._alert_callbacks.append(cb)

    def heartbeat(self, collector_name):
        self.collector_heartbeats[collector_name] = time.time()

    def check(self) -> dict:
        mem = psutil.Process().memory_info().rss / 1024 / 1024
        cpu_pct = psutil.Process().cpu_percent(interval=None)
        uptime = time.time() - self.start_time

        result = {
            "ts": datetime.now().isoformat(),
            "rss_mb": round(mem, 2),
            "cpu_pct": round(cpu_pct, 2),
            "uptime_sec": round(uptime),
            "budget_ok": mem < RAM_BUDGET_MB,
            "stale_collectors": [],
        }

        # Check for stale collectors (no heartbeat in 60s)
        now = time.time()
        for name, last in self.collector_heartbeats.items():
            if now - last > 60:
                result["stale_collectors"].append(name)

        return result

    def check_disk(self) -> dict:
        """Check disk space."""
        from nfr.constants import STORAGE_ROOT
        try:
            usage = psutil.disk_usage(str(STORAGE_ROOT))
            return {
                "free_gb": round(usage.free / 1024 / 1024 / 1024, 2),
                "percent": usage.percent,
            }
        except Exception as e:
            return {"error": str(e)}
