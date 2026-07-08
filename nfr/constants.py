"""Network Flight Recorder constants."""
from pathlib import Path

STORAGE_ROOT = Path("/var/lib/nfr")
STORAGE_LOGS = STORAGE_ROOT / "logs"
STORAGE_INDEX = STORAGE_ROOT / "index.json"
CONFIG_PATH = Path("/etc/nfr/nfr.yaml")
PID_FILE = Path("/var/run/nfr.pid")

# Performance budgets
CPU_BUDGET_PERCENT = 1.0
RAM_BUDGET_MB = 50

# Collection intervals
SNAPSHOT_INTERVAL_SEC = 300  # 5 min
EVENTBUS_QUEUE_SIZE = 1024
