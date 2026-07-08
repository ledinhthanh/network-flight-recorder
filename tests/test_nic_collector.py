"""Tests for NIC collector."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
from nfr.collectors.nic import NICCollector
from nfr.core.eventbus import EventBus
from nfr.models import EventType


class TestNICCollector(unittest.TestCase):
    def test_discover_interfaces(self):
        c = NICCollector(interfaces=["enp1s0"])
        self.assertIn("enp1s0", c.interfaces)

    def test_diff_emits_carrier_down(self):
        bus = EventBus()
        c = NICCollector(bus=bus, interfaces=["enp1s0"])
        c._diff("enp1s0",
                {"carrier": 1, "operstate": "up", "speed": "1000"},
                {"carrier": 0, "operstate": "down", "speed": "-1"})
        # EventBus is async - check queue directly
        self.assertEqual(bus._queue.qsize(), 1)
        ev = bus._queue.get_nowait()
        self.assertEqual(ev.type, EventType.CARRIER_DOWN)

    def test_diff_emits_carrier_up(self):
        bus = EventBus()
        c = NICCollector(bus=bus, interfaces=["enp1s0"])
        c._diff("enp1s0",
                {"carrier": 0, "operstate": "down", "speed": "-1"},
                {"carrier": 1, "operstate": "up", "speed": "1000"})
        self.assertEqual(bus._queue.qsize(), 1)
        ev = bus._queue.get_nowait()
        self.assertEqual(ev.type, EventType.CARRIER_UP)

    def test_no_diff_when_same(self):
        bus = EventBus()
        c = NICCollector(bus=bus, interfaces=["enp1s0"])
        c._diff("enp1s0",
                {"carrier": 1, "operstate": "up", "speed": "1000"},
                {"carrier": 1, "operstate": "up", "speed": "1000"})
        self.assertEqual(bus._queue.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
