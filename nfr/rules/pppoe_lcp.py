"""Rule: PPPoE LCP timeout without carrier loss = PPP/auth issue."""
from typing import List, Optional

from nfr.models import Event, EventType, Finding
from nfr.rules.base import Rule


class PPPoELCPRule(Rule):
    def name(self) -> str:
        return "pppoe_lcp"

    def match(self, events: List[Event]) -> Optional[Finding]:
        lcp = self._find_first(events, EventType.PPP_LCP_TIMEOUT, window_sec=60)
        if not lcp:
            return None

        # Check for carrier_down around same time
        carrier_down_within = None
        for e in events:
            if e.type == EventType.CARRIER_DOWN:
                dt = (lcp.ts - e.ts).total_seconds()
                if abs(dt) < 5:
                    carrier_down_within = e
                    break
        if carrier_down_within:
            return None  # handled by carrier_loss rule

        return Finding(
            primary_cause="PPPoE LCP timeout (no carrier loss)",
            confidence=0.85,
            evidence=[lcp.id],
            reasoning="LCP timeout but physical link appears up. Likely PPPoE/auth/peer issue.",
            timeline=[lcp],
        )


class PPPoEPADORule(Rule):
    def name(self) -> str:
        return "pppoe_pado"

    def match(self, events: List[Event]) -> Optional[Finding]:
        pado = self._find_first(events, EventType.PPP_PADO_TIMEOUT, window_sec=60)
        if not pado:
            return None
        return Finding(
            primary_cause="PPPoE PADO timeout (no response from ISP)",
            confidence=0.9,
            evidence=[pado.id],
            reasoning="PPPoE server (BRAS) did not respond. Likely ISP-side issue.",
            timeline=[pado],
        )
