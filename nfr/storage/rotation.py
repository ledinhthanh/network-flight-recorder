"""Log rotation and retention."""
import gzip
from datetime import datetime, timedelta
from pathlib import Path

from nfr.constants import STORAGE_LOGS


def rotate_old(days: int = 30) -> int:
    """Compress logs older than N days. Returns count rotated."""
    cutoff = datetime.now() - timedelta(days=days)
    count = 0
    if not STORAGE_LOGS.exists():
        return 0
    for d in STORAGE_LOGS.iterdir():
        if not d.is_dir():
            continue
        try:
            dir_date = datetime.strptime(d.name, "%Y-%m-%d")
        except ValueError:
            continue
        if dir_date < cutoff:
            for f in d.glob("*.jsonl"):
                gz = f.with_suffix(f.suffix + ".gz")
                if not gz.exists():
                    with open(f, "rb") as src, gzip.open(gz, "wb") as dst:
                        dst.write(src.read())
                    f.unlink()
                    count += 1
    return count
