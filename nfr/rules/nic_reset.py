"""Rule: NIC reset / hardware issue detection."""
from typing import List, Optional

from nfr.models import Event, EventType, Finding
from nfr.rules.base import Rule


class NICResetRule(Rule):
    def name(self) -> str:
        return "nic_reset"

    def match(self, events: List[Event]) -> Optional[Finding]:
        pcie = self._find_first(events, EventType.PCIE_AER, window_sec=60)
        netdev_wd = self._find_first(events, EventType.NETDEV_WATCHDOG, window_sec=60)
        mce = self._find_first(events, EventType.MCE, window_sec=60)

        trigger = pcie or netdev_wd or mce
        if not trigger:
            return None

        timeline = [trigger]
        # If MCE, confidence very high
        confidence = 0.95 if mce else 0.85 if pcie else 0.8
        cause = "Hardware fault"
        if mce:
            cause = "Machine Check Exception (CPU/hardware error)"
        elif pcie:
            cause = "PCIe AER (link/device error)"
        elif netdev_wd:
            cause = "NETDEV watchdog (NIC hang)"

        # counter: if also see carrier_down shortly after, might be driver issue
        carrier_down = self._find_after(events, EventType.CARRIER_DOWN, trigger, window_sec=10)
        if carrier_down:
            timeline.append(carrier_down)
            confidence = min(confidence + 0.1, 0.99)

        return Finding(
            primary_cause=cause,
            confidence=confidence,
            evidence=[e.id for e in timeline],
            reasoning="Hardware/kernel-level event detected that may explain NIC issue.",
            timeline=timeline,
        )


class BridgeLoopRule(Rule):
    def name(self) -> str:
        return "bridge_loop"

    def match(self, events: List[Event]) -> Optional[Finding]:
        flaps = [e for e in events if e.type == EventType.MAC_FLAP]
        if len(flaps) < 3:
            return None
        return Finding(
            primary_cause="Bridge loop / MAC flapping",
            confidence=0.85,
            evidence=[e.id for e in flaps[:5]],
            reasoning="Multiple MAC moves detected in short window. Likely bridge loop or L2 issue.",
            timeline=flaps[:5],
        )
