"""Rule engine with cross-layer correlation."""
from typing import List, Optional

from nfr.core.correlation import correlate
from nfr.models import Event, Finding
from nfr.rules.base import Rule
from nfr.rules.carrier_loss import CarrierLossRule
from nfr.rules.pppoe_lcp import PPPoELCPRule, PPPoEPADORule
from nfr.rules.nic_reset import NICResetRule, BridgeLoopRule
from nfr.rules.gpon_degradation import GPONDegradationRule


DEFAULT_RULES = [
    CarrierLossRule(),
    PPPoELCPRule(),
    PPPoEPADORule(),
    NICResetRule(),
    BridgeLoopRule(),
    GPONDegradationRule(),
]


class RuleEngine:
    def __init__(self, rules: List[Rule] = None):
        self.rules = rules or DEFAULT_RULES

    def run(self, events: List[Event]) -> List[Finding]:
        findings = []
        for r in self.rules:
            try:
                f = r.match(events)
                if f:
                    findings.append(f)
            except Exception:
                continue
        # Cross-layer correlation
        try:
            for f in correlate(events):
                findings.append(f)
        except Exception:
            pass
        findings.sort(key=lambda x: x.confidence, reverse=True)
        return findings
