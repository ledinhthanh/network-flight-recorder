"""Notification policy.

Decides WHEN to notify and WHAT to send.

Rules:
- Only WARNING/CRITICAL incidents → telegram
- One notification per incident (dedup via inc.notified)
- Skip if RCA confidence < 0.5 (could be noise)
- Skip short blips (impact_seconds < threshold)
"""
from datetime import datetime
from typing import Optional

from nfr.incidents.models import Incident, IncidentSeverity
from nfr.notifier import Notifier


# Thresholds - tune per environment via config later
MIN_NOTIFY_IMPACT_SEC = 30
MIN_RCA_CONFIDENCE = 0.5


class NotificationPolicy:
    def __init__(self, notifier: Optional[Notifier] = None):
        self.notifier = notifier or Notifier()

    def should_notify(self, inc: Incident) -> bool:
        """Decision logic."""
        if inc.notified:
            return False
        if inc.severity not in (IncidentSeverity.WARNING, IncidentSeverity.CRITICAL):
            return False
        if inc.rca_confidence is None or inc.rca_confidence < MIN_RCA_CONFIDENCE:
            return False
        if inc.impact_seconds < MIN_NOTIFY_IMPACT_SEC:
            return False
        return True

    def notify(self, inc: Incident) -> bool:
        """Send notification if policy allows. Marks incident as notified.

        Returns True if sent.
        """
        if not self.notifier.is_configured():
            return False
        if not self.should_notify(inc):
            return False
        duration = self._format_duration(inc.impact_seconds)
        start = inc.start_ts.strftime("%H:%M:%S")
        end = inc.end_ts.strftime("%H:%M:%S") if inc.end_ts else "ongoing"
        text = (
            "🚨 *NFR Incident*\n\n"
            f"*ID:* `{inc.id}`\n"
            f"*Severity:* `{inc.severity.value.upper()}`\n"
            f"*Start:* {start}\n"
            f"*End:* {end}\n"
            f"*Duration:* {duration}\n"
            f"*Layers affected:* {', '.join(inc.layers_affected)}\n"
            f"*Events:* {inc.raw_event_count} ({', '.join(inc.key_event_types[:5])})\n\n"
            f"*Root cause:* {inc.rca_cause or 'Pending'}\n"
            f"*Confidence:* {int((inc.rca_confidence or 0) * 100)}%\n"
            f"*Reasoning:* {inc.rca_reasoning or 'N/A'}"
        )
        ok = self.notifier.send(text)
        if ok:
            inc.notified = True
            inc.notification_count += 1
        return ok

    @staticmethod
    def _format_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return str(s) + "s"
        m, s = divmod(s, 60)
        if m < 60:
            return str(m) + "m " + str(s) + "s"
        h, m = divmod(m, 60)
        return str(h) + "h " + str(m) + "m"
