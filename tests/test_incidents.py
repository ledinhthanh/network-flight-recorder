"""Tests for incident pipeline."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
from datetime import datetime, timedelta

from nfr.models import Event, EventType, Severity
from nfr.incidents.builder import IncidentBuilder
from nfr.incidents.models import Incident, IncidentSeverity, IncidentStatus, layer_of
from nfr.incidents.correlation import cluster, severity_for_events
from nfr.incidents.notify_policy import NotificationPolicy
from nfr.notifier import Notifier, TelegramConfig


def mk(t: EventType, ts, sev=Severity.CRITICAL, src="test") -> Event:
    return Event(type=t, severity=sev, ts=ts, source=src, message="m")


class TestSeverity(unittest.TestCase):
    def test_carrier_down_is_warning(self):
        self.assertEqual(severity_for_events("carrier_down"), IncidentSeverity.WARNING)

    def test_mce_is_critical(self):
        self.assertEqual(severity_for_events("mce"), IncidentSeverity.CRITICAL)

    def test_phy_error_is_notice(self):
        self.assertEqual(severity_for_events("phy_error"), IncidentSeverity.NOTICE)


class TestBuilder(unittest.TestCase):
    def test_single_degrading_event_opens_incident(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        ev = mk(EventType.CARRIER_DOWN, ts)
        inc = b.process(ev)
        self.assertIsNotNone(inc)
        self.assertEqual(inc.status, IncidentStatus.OPEN)
        self.assertEqual(inc.severity, IncidentSeverity.WARNING)
        self.assertIn("physical", inc.layers_affected)

    def test_recovery_event_closes_incident(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        b.process(mk(EventType.CARRIER_DOWN, ts))
        inc_close = b.process(mk(EventType.CARRIER_UP, ts + timedelta(seconds=2)))
        self.assertIsNotNone(inc_close)
        self.assertEqual(inc_close.status, IncidentStatus.CLOSED)

    def test_correlated_events_extend_same_incident(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        first = b.process(mk(EventType.CARRIER_DOWN, ts))
        second = b.process(mk(EventType.PPP_LCP_TIMEOUT, ts + timedelta(seconds=2)))
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.raw_event_count, 2)

    def test_isolated_events_create_different_incidents(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        # long gap > MATCH_WINDOW
        i1 = b.process(mk(EventType.CARRIER_DOWN, ts))
        i2 = b.process(mk(EventType.PPP_LCP_TIMEOUT, ts + timedelta(seconds=60)))
        # different layer, likely new incident
        self.assertIsNotNone(i2)

    def test_info_event_does_not_open(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        # snapshot events should never open
        result = b.process(mk(EventType.SNAPSHOT, ts))
        self.assertIsNone(result)

    def test_timeout_closes_incident(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        b.process(mk(EventType.CARRIER_DOWN, ts))
        # sweep 90s later
        b.sweep_timeouts(now=ts + timedelta(seconds=90))
        active = b.active_incidents()
        self.assertEqual(len(active), 0)

    def test_single_mac_flap_suppressed(self):
        b = IncidentBuilder()
        ts = datetime(2026, 7, 8, 14, 23, 0)
        result = b.process(mk(EventType.MAC_FLAP, ts, sev=Severity.WARN))
        self.assertIsNone(result)  # suppressed (need 3+ in window)


class TestNotifyPolicy(unittest.TestCase):
    def _open_inc(self, sev, impact=60, rca_conf=0.8):
        inc = Incident(
            id="inc-test", start_ts=datetime.now(),
            severity=sev, layers_affected=["physical"],
            event_ids=["e1"], key_event_types=["carrier_down"],
            raw_event_count=1, impact_seconds=impact,
            rca_cause="carrier", rca_confidence=rca_conf,
            rca_reasoning="x", rca_evidence_count=1,
        )
        return inc

    def test_info_does_not_notify(self):
        n = NotificationPolicy(notifier=_disabled_notifier())
        inc = self._open_inc(IncidentSeverity.INFO)
        self.assertFalse(n.should_notify(inc))

    def test_critical_with_high_rca_notifies(self):
        n = NotificationPolicy(notifier=_disabled_notifier())
        inc = self._open_inc(IncidentSeverity.CRITICAL, impact=120, rca_conf=0.9)
        self.assertTrue(n.should_notify(inc))

    def test_short_blip_no_notify(self):
        n = NotificationPolicy(notifier=_disabled_notifier())
        inc = self._open_inc(IncidentSeverity.WARNING, impact=5)
        self.assertFalse(n.should_notify(inc))

    def test_low_rca_no_notify(self):
        n = NotificationPolicy(notifier=_disabled_notifier())
        inc = self._open_inc(IncidentSeverity.WARNING, impact=60, rca_conf=0.2)
        self.assertFalse(n.should_notify(inc))

    def test_dedup_already_notified(self):
        n = NotificationPolicy(notifier=_disabled_notifier())
        inc = self._open_inc(IncidentSeverity.CRITICAL, impact=120)
        inc.notified = True
        self.assertFalse(n.should_notify(inc))


def _disabled_notifier() -> Notifier:
    cfg = TelegramConfig()
    cfg.token = None
    cfg.chat_id = None
    return Notifier(cfg)


if __name__ == "__main__":
    unittest.main()
