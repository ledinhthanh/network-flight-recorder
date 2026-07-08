"""Allow: python3 -m nfr.cli <command>

Refactored to avoid the -m globals() lookup issue by using dispatch directly.
"""
import sys
import argparse
from nfr.cli import cmd as _cmd
from nfr.cli.cmd import (
    cmd_status, cmd_today, cmd_timeline, cmd_report, cmd_index,
    cmd_doctor, cmd_version, cmd_search, cmd_notify_test, cmd_notify_status,
)

DISPATCH = {
    "status": cmd_status,
    "today": cmd_today,
    "timeline": cmd_timeline,
    "report": cmd_report,
    "index": cmd_index,
    "doctor": cmd_doctor,
    "version": cmd_version,
    "search": cmd_search,
    "notify-test": cmd_notify_test,
    "notify-status": cmd_notify_status,
}


def main():
    p = argparse.ArgumentParser(prog="nfr", description="Network Flight Recorder")
    sub = p.add_subparsers(dest="cmd")
    for name in DISPATCH:
        sp = sub.add_parser(name)
        if name == "search":
            sp.add_argument("query")
    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1
    fn = DISPATCH.get(args.cmd)
    if not fn:
        return 1
    return fn(args) or 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(rc)
