"""Tests for storage layer."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
import os
import tempfile
from datetime import datetime
from pathlib import Path

from nfr.models import Event, EventType, Severity
from nfr.storage.journal import append_event, read_events
from nfr.storage.index import update_day, get_index
from nfr.constants import STORAGE_INDEX


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_append_and_read(self):
        e = Event(
            type=EventType.CARRIER_DOWN,
            severity=Severity.CRITICAL,
            ts=datetime.now(),
            source="test",
            message="carrier down",
        )
        append_event(e)
        events = read_events()
        self.assertGreater(len(events), 0)
        # Find by message
        found = any(ev.message == "carrier down" for ev in events)
        self.assertTrue(found)

    def test_atomic_write(self):
        """Multiple writes should not corrupt the file."""
        for i in range(10):
            e = Event(
                type=EventType.CARRIER_DOWN,
                severity=Severity.INFO,
                ts=datetime.now(),
                source="test",
                message="msg " + str(i),
            )
            append_event(e)
        events = read_events()
        msgs = [ev.message for ev in events]
        for i in range(10):
            self.assertIn("msg " + str(i), msgs)

    def test_index_update(self):
        update_day("2026-07-08", "ok", 5, top_issue="none")
        idx = get_index()
        self.assertIn("2026-07-08", idx)


if __name__ == "__main__":
    unittest.main()
