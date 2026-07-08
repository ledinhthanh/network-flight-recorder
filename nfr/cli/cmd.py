"""NFR CLI."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from nfr.constants import STORAGE_LOGS, STORAGE_INDEX
from nfr.models import Event, Finding
from nfr.rules.engine import RuleEngine
from nfr.storage.journal import read_events
from nfr.storage.index import get_index
from nfr.timeline.builder import build_summary
from nfr.incidents import storage as inc_storage
from nfr.incidents.models import IncidentSeverity, IncidentStatus
from nfr.notifier import Notifier, TelegramConfig
from nfr.version import __version__


def cmd_status(args):
    today = datetime.now().strftime("%Y-%m-%d")
    events = read_events(today)
    s = build_summary(today, events)
    print("NFR " + __version__)
    print("Date: " + today)
    print("Events: " + str(s["events"]))
    print("Status: " + s["status"])
    print("Outages: " + str(s["outages"]))


def cmd_today(args):
    today = datetime.now().strftime("%Y-%m-%d")
    events = read_events(today)
    for e in events:
        ts = e.ts.strftime("%H:%M:%S")
        print(ts + " [" + e.severity.value + "] " + e.type.value + ": " + e.message)
    return 0


def cmd_timeline(args):
    today = datetime.now().strftime("%Y-%m-%d")
    p = STORAGE_LOGS / today / "timeline.txt"
    if p.exists():
        print(p.read_text())
    else:
        events = read_events(today)
        for e in sorted(events, key=lambda x: x.ts):
            ts = e.ts.strftime("%H:%M:%S")
            print(ts + " " + e.message)
    return 0


def cmd_report(args):
    today = datetime.now().strftime("%Y-%m-%d")
    events = read_events(today)
    engine = RuleEngine()
    findings = engine.run(events)
    print("NFR Report " + today)
    print("=" * 60)
    s = build_summary(today, events)
    print("Status: " + s["status"])
    print("Events: " + str(s["events"]))
    print("")
    if findings:
        print("RCA Findings:")
        for f in findings:
            print("")
            print("  Cause: " + f.primary_cause)
            print("  Confidence: {:.0%}".format(f.confidence))
            print("  Evidence: " + str(len(f.evidence)) + " events")
            print("  Reasoning: " + f.reasoning)
            print("  Timeline:")
            for e in f.timeline:
                ts = e.ts.strftime("%H:%M:%S")
                print("    " + ts + " " + e.type.value + ": " + e.message[:80])
    else:
        print("No issues detected.")
    return 0


def cmd_index(args):
    idx = get_index()
    for date in sorted(idx.keys()):
        print(date + ": " + idx[date].get("status", "?") + " (" + str(idx[date].get("events", 0)) + " events)")
    return 0


def cmd_search(args):
    today = datetime.now().strftime("%Y-%m-%d")
    events = read_events(today)
    needle = args.query.lower()
    count = 0
    for e in events:
        if needle in e.message.lower() or needle in e.type.value.lower():
            ts = e.ts.strftime("%H:%M:%S")
            print(ts + " [" + e.severity.value + "] " + e.type.value + ": " + e.message)
            count += 1
    print("(" + str(count) + " matches)")
    return 0


def cmd_doctor(args):
    print("NFR Doctor")
    print("=" * 40)
    for p in [STORAGE_LOGS, STORAGE_INDEX.parent]:
        ok = p.exists()
        print("  " + str(p) + ": " + ("OK" if ok else "MISSING"))
    # check writable
    try:
        test = STORAGE_LOGS / "test.tmp"
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text("test")
        test.unlink()
        print("  write: OK")
    except Exception as e:
        print("  write: FAIL " + str(e))
    return 0




def cmd_incidents(args):
    """List incidents for today (or specified date)."""
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].count("-") == 2 else None
    if date and "-" in date and len(date) == 10:
        incidents = inc_storage.load_incidents_for_date(date)
    else:
        from datetime import datetime
        incidents = inc_storage.load_incidents_for_date(datetime.now().strftime("%Y-%m-%d"))
    if not incidents:
        print("No incidents for", date or "today")
        return 0
    sev_counts = {}
    for inc in incidents:
        sev_counts[inc.severity.value] = sev_counts.get(inc.severity.value, 0) + 1
    print("Incidents:", len(incidents))
    for k, v in sorted(sev_counts.items()):
        print("  " + k + ":", v)
    print()
    print("ID                          SEV       START          END            DURATION  RCA")
    for inc in sorted(incidents, key=lambda i: i.start_ts):
        start = inc.start_ts.strftime("%H:%M:%S")
        end = inc.end_ts.strftime("%H:%M:%S") if inc.end_ts else "..."
        dur = "%4ds" % int(inc.impact_seconds) if inc.impact_seconds else "    "
        rca = (inc.rca_cause or "")[:25]
        print("{:<26} {:<9} {:<14} {:<14} {:<8} {}".format(
            inc.id[-26:], inc.severity.value, start, end, dur, rca))
    return 0


def cmd_incident(args):
    """Show incident details. Usage: nfr incident <id>"""
    import sys
    if len(sys.argv) < 3:
        print("Usage: nfr incident <id>")
        return 1
    inc_id = sys.argv[2]
    inc = inc_storage.load_incident(inc_id)
    if not inc:
        # Try partial match
        idx = inc_storage.get_index()
        for date_str in sorted(idx.keys(), reverse=True):
            incidents = inc_storage.load_incidents_for_date(date_str)
            for inc in incidents:
                if inc.id.endswith(inc_id) or inc.id == inc_id:
                    break
            else:
                continue
            break
        else:
            inc = None
    if not inc:
        print("Incident not found:", inc_id)
        return 1
    print("Incident:", inc.id)
    print("Status:", inc.status.value)
    print("Severity:", inc.severity.value)
    print("Start:", inc.start_ts.isoformat())
    print("End:", inc.end_ts.isoformat() if inc.end_ts else "(ongoing)")
    print("Duration:", "%.1fs" % inc.impact_seconds)
    print("Layers:", ", ".join(inc.layers_affected))
    print("Events:", inc.raw_event_count)
    print("Key event types:", ", ".join(inc.key_event_types))
    print("Notified:", inc.notified, "(times:", inc.notification_count, ")")
    print()
    if inc.rca_cause:
        print("RCA:")
        print("  Cause:", inc.rca_cause)
        print("  Confidence:", "%.0f%%" % (inc.rca_confidence * 100) if inc.rca_confidence else "?")
        print("  Reasoning:", inc.rca_reasoning)
        print("  Evidence:", inc.rca_evidence_count, "events")
    return 0


def cmd_active(args):
    """Show currently-open incidents."""
    incidents = inc_storage.load_active_incidents()
    if not incidents:
        print("No active incidents")
        return 0
    print("Active incidents:", len(incidents))
    for inc in incidents:
        start = inc.start_ts.strftime("%H:%M:%S")
        age = "%.0fs" % inc.impact_seconds
        print("  [{}] {} (started {}) layers={} age={}".format(
            inc.severity.value.upper(), inc.id, start,
            ",".join(inc.layers_affected), age))
    return 0

def cmd_version(args):
    print("NFR " + __version__)
    return 0


def cmd_notify_test(args):
    """Send a test message to Telegram (if configured)."""
    n = Notifier()
    if not n.is_configured():
        print("Telegram not configured.")
        print("Set NFR_TELEGRAM_TOKEN + NFR_TELEGRAM_CHAT_ID env vars")
        print("OR create /etc/nfr/telegram.yaml with:")
        print("  token: <bot_token>")
        print("  chat_id: <chat_id>")
        return 1
    ok = n.test()
    if ok:
        print("Test message sent successfully.")
    else:
        print("Failed to send. Check token/chat_id.")
    return 0 if ok else 2


def cmd_notify_status(args):
    """Check Telegram configuration."""
    cfg = TelegramConfig.load()
    n = Notifier(cfg)
    print("Telegram configuration:")
    print("  enabled: " + str(n.is_configured()))
    if cfg.token:
        print("  token: ***" + cfg.token[-8:] if len(cfg.token) > 8 else "***")
    if cfg.chat_id:
        print("  chat_id: " + cfg.chat_id)
    return 0


def main():
    p = argparse.ArgumentParser(prog="nfr", description="Network Flight Recorder")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status")
    sub.add_parser("today")
    sub.add_parser("timeline")
    sub.add_parser("report")
    sub.add_parser("index")
    sub.add_parser("doctor")
    sub.add_parser("version")
    nt = sub.add_parser("notify-test", help="Send Telegram test message")
    sub.add_parser("notify-status", help="Show Telegram config status")
    s = sub.add_parser("search")
    s.add_argument("query")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1

    fn = globals().get("cmd_" + args.cmd)
    if not fn:
        return 1
    return fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
