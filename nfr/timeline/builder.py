"""Builds human-readable timeline + summary.json + health.txt from events."""
import json
from datetime import datetime
from pathlib import Path
from typing import List

from nfr.models import Event, EventType
from nfr.constants import STORAGE_LOGS


def write_timeline(date: str, events: List[Event]) -> Path:
    """Write a human-readable timeline file."""
    if not events:
        return None
    out_dir = STORAGE_LOGS / date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "timeline.txt"
    lines = ["NFR Timeline for " + date, "=" * 60, ""]
    for e in sorted(events, key=lambda x: x.ts):
        ts = e.ts.strftime("%H:%M:%S.%f")[:-3]
        prefix = "[" + e.severity.value.upper() + "]"
        line = ts + " " + prefix + " " + e.source + ": " + e.message
        if e.prev_state and e.new_state:
            line += " ({} -> {})".format(e.prev_state, e.new_state)
        lines.append(line)
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def build_summary(date: str, events: List[Event]) -> dict:
    """Build daily summary - returns dict AND writes summary.json + health.txt."""
    by_type = {}
    by_severity = {"info": 0, "warn": 0, "error": 0, "critical": 0}
    by_source = {}
    for e in events:
        by_type[e.type.value] = by_type.get(e.type.value, 0) + 1
        by_severity[e.severity.value] = by_severity.get(e.severity.value, 0) + 1
        by_source[e.source] = by_source.get(e.source, 0) + 1

    outages = by_type.get(EventType.CARRIER_DOWN.value, 0) + by_type.get(EventType.OPENWRT_WAN_DOWN.value, 0)
    pppoe = by_type.get(EventType.PPP_LCP_TIMEOUT.value, 0) + by_type.get(EventType.PPP_PADT.value, 0)
    phy = by_type.get(EventType.PHY_ERROR.value, 0)

    status = "ok"
    if outages > 0 or pppoe > 2 or phy > 0:
        status = "degraded"
    if outages > 3 or pppoe > 10:
        status = "outage"

    summary = {
        "date": date,
        "events": len(events),
        "outages": outages,
        "pppoe_reconnects": pppoe,
        "phy_errors": phy,
        "status": status,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_source": by_source,
    }
    # Write files
    out_dir = STORAGE_LOGS / date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    # Health.txt - quick read
    health_lines = [
        "Health " + date,
        "-" * 40,
        "Status:    " + status,
        "Events:    " + str(len(events)),
        "Outages:   " + str(outages),
        "PPPoE:     " + str(pppoe),
        "PHY errs:  " + str(phy),
        "",
        "Top sources:",
    ]
    for src, cnt in sorted(by_source.items(), key=lambda x: -x[1])[:5]:
        health_lines.append("  " + src + ": " + str(cnt))
    (out_dir / "health.txt").write_text("\n".join(health_lines) + "\n")
    return summary
