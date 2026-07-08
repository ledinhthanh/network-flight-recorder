"""Tests for rule engine."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
from datetime import datetime, timedelta
from nfr.models import Event, EventType, Severity
from nfr.rules.engine import RuleEngine


def make_ev(etype, secs_ago=0):
    return Event(
        type=etype,
        severity=Severity.ERROR,
        ts=datetime.now() - timedelta(seconds=secs_ago),
        source="test",
        message="test"
    )


class TestRuleEngine(unittest.TestCase):
    def test_carrier_loss_causes_outage(self):
        evs = [
            make_ev(EventType.CARRIER_DOWN, 60),
            make_ev(EventType.PPP_LCP_TIMEOUT, 30),
            make_ev(EventType.OPENWRT_WAN_DOWN, 28),
        ]
        engine = RuleEngine()
        findings = engine.run(evs)
        self.assertTrue(len(findings) > 0)
        self.assertEqual(findings[0].primary_cause, "Physical layer / carrier loss")

    def test_pppoe_lcp_alone(self):
        evs = [make_ev(EventType.PPP_LCP_TIMEOUT, 10)]
        engine = RuleEngine()
        findings = engine.run(evs)
        lcp_findings = [f for f in findings if "LCP" in f.primary_cause]
        self.assertEqual(len(lcp_findings), 1)

    def test_pcie_aer(self):
        evs = [make_ev(EventType.PCIE_AER, 5)]
        engine = RuleEngine()
        findings = engine.run(evs)
        self.assertTrue(any("PCIe" in f.primary_cause or "Hardware" in f.primary_cause for f in findings))

    def test_no_events(self):
        engine = RuleEngine()
        self.assertEqual(engine.run([]), [])


if __name__ == "__main__":
    unittest.main()
