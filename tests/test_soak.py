"""Soak test: monitor memory + FD count over a short window.

Runs in foreground, sampling process metrics.
Reports leak detection.
"""
import sys
sys.path.insert(0, "/opt/nfr")
import os
import time
import psutil
import unittest


class TestSoak(unittest.TestCase):
    """Short-window soak test (5 minutes in production, 10s here)."""

    def test_no_fd_leak(self):
        """FD count should not grow unbounded."""
        samples = []
        for i in range(3):
            time.sleep(2)
            # scan all python processes
            count = 0
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info.get("name") and "python3" in proc.info["name"]:
                    try:
                        count += len(os.listdir("/proc/" + str(proc.info["pid"]) + "/fd"))
                    except (OSError, KeyError, PermissionError):
                        pass
            samples.append(count)
        # FD count should be stable (<50% growth)
        if len(samples) >= 2:
            growth = samples[-1] - samples[0]
            self.assertLess(growth, 50, "FD count grew by " + str(growth))

    def test_memory_baseline(self):
        """Record baseline memory."""
        proc = psutil.Process()
        rss = proc.memory_info().rss
        self.assertGreater(rss, 0)
        self.assertLess(rss, 100 * 1024 * 1024, "RSS exceeds 100MB")


if __name__ == "__main__":
    unittest.main()
