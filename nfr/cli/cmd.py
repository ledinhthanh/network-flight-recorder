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


def cmd_version(args):
    print("NFR " + __version__)
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
