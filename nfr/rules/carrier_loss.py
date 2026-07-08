"""Rule: Carrier loss causes downstream failures (with counter-evidence)."""
from typing import List, Optional

from nfr.models import Event, EventType, Finding
from nfr.rules.base import Rule


class CarrierLossRule(Rule):
    """NIC carrier down -> PPPoE/connectivity loss."""

    def name(self) -> str:
        return "carrier_loss"

    def match(self, events: List[Event]) -> Optional[Finding]:
        carrier_down = self._find_first(events, EventType.CARRIER_DOWN, window_sec=60)
        if not carrier_down:
            return None

        ppp_lcp = self._find_after(events, EventType.PPP_LCP_TIMEOUT, carrier_down, window_sec=30)
        ppp_padt = self._find_after(events, EventType.PPP_PADT, carrier_down, window_sec=30)
        wan_down = self._find_after(events, EventType.OPENWRT_WAN_DOWN, carrier_down, window_sec=30)
        gateway_lost = self._find_after(events, EventType.GATEWAY_UNREACHABLE, carrier_down, window_sec=30)

        downstream = [e for e in [ppp_lcp, ppp_padt, wan_down, gateway_lost] if e is not None]
        all_ev = [carrier_down] + downstream
        timeline = sorted(all_ev, key=lambda e: e.ts)

        # counter-evidence: PHY errors BEFORE carrier_down => maybe hardware not carrier
        phy_before = self._find_in_window(events, EventType.PHY_ERROR, carrier_down, 30, 5)
        # counter: NIC reset/mce => hardware not pure carrier
        nic_reset = self._find_in_window(events, EventType.NIC_RESET, carrier_down, 10, 30)
        mce = self._find_in_window(events, EventType.MCE, carrier_down, 60, 60)

        counter = []
        confidence = 0.95 if downstream else 0.85

        if phy_before:
            counter.append(("PHY errors detected 30s BEFORE carrier_down → possible hardware degradation, not pure carrier issue", phy_before.id))
            confidence -= 0.15
        if nic_reset:
            counter.append(("NIC reset within ±30s → driver-level issue, not pure carrier", nic_reset.id))
            confidence -= 0.2
        if mce:
            counter.append(("Machine Check Exception detected → hardware fault likely", mce.id))
            confidence -= 0.05  # hardware, but might still cause carrier

        confidence = max(0.1, min(0.99, confidence))

        return Finding(
            primary_cause="Physical layer / carrier loss",
            confidence=confidence,
            evidence=[e.id for e in all_ev],
            counter_evidence=[(msg, ev_id) for msg, ev_id in counter],
            timeline=timeline,
            reasoning=("NIC carrier dropped at " + carrier_down.ts.isoformat() +
                       (", causing downstream " + ", ".join(e.type.value for e in downstream) if downstream
                        else ", no downstream impact observed yet") + "."),
        )
