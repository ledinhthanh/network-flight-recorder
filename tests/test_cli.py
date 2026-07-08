"""Tests for CLI."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
from io import StringIO
from datetime import datetime

from nfr.models import Event, EventType, Severity
from nfr.storage.journal import append_event
from nfr.cli import cmd


class TestCLI(unittest.TestCase):
    def test_version(self):
        rc = cmd.cmd_version(type("A", (), {})())
        self.assertEqual(rc, 0)

    def test_doctor(self):
        rc = cmd.cmd_doctor(type("A", (), {})())
        self.assertEqual(rc, 0)

    def test_search_finds_events(self):
        e = Event(
            type=EventType.CARRIER_DOWN,
            severity=Severity.CRITICAL,
            ts=datetime.now(),
            source="test",
            message="specific_search_term_xyz123",
        )
        append_event(e)
        args = type("A", (), {"query": "specific_search_term_xyz123"})()
        rc = cmd.cmd_search(args)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
