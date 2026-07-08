import sys
sys.path.insert(0, "/opt/nfr")
from typing import List, Optional
from datetime import timedelta, timezone

from nfr.incidents.models import Incident
from nfr.models import Event
from nfr.rules.engine import RuleEngine
from nfr.storage.journal import read_events


def _as_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def load_events_for_incident(inc):
    all_events = []
    today = inc.start_ts.strftime("%Y-%m-%d")
    yesterday = (inc.start_ts - timedelta(days=1)).strftime("%Y-%m-%d")
    for d in (yesterday, today):
        all_events.extend(read_events(d))
    margin = timedelta(minutes=5)
    start = _as_aware(inc.start_ts) - margin
    end = _as_aware(inc.end_ts or inc.start_ts) + margin
    matches = [e for e in all_events if start <= _as_aware(e.ts) <= end]
    id_set = set(inc.event_ids)
    if id_set and id_set & {e.id for e in matches}:
        return [e for e in matches if e.id in id_set]
    return matches


def analyze(inc, engine=None):
    events = load_events_for_incident(inc)
    if not events:
        return
    engine = engine or RuleEngine()
    findings = engine.run(events)
    if not findings:
        inc.rca_cause = "Undetermined"
        inc.rca_confidence = 0.0
        inc.rca_reasoning = "No rules matched the collected events."
        inc.rca_evidence_count = 0
        return
    findings.sort(key=lambda f: f.confidence, reverse=True)
    top = findings[0]
    inc.rca_cause = top.primary_cause
    inc.rca_confidence = top.confidence
    inc.rca_reasoning = top.reasoning
    inc.rca_evidence_count = len(top.evidence)
