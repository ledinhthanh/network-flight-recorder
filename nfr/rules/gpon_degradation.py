"""Rule: GPON optical degradation inferred from NIC PHY errors + carrier flap."""
from typing import List, Optional

from nfr.models import Event, EventType, Finding
from nfr.rules.base import Rule


class GPONDegradationRule(Rule):
    """Detect patterns indicating GPON/ONT optical issues (which we cannot
    read directly from the locked-down HBG1000R ONT).
    """

    def name(self) -> str:
        return "gpon_degradation"

    def match(self, events: List[Event]) -> Optional[Finding]:
        # Look for rapid flap signals (from flap_detector)
        flaps = [e for e in events if e.type == EventType.PHY_ERROR
                 and e.data.get("signature") == "rapid_flap"]
        # Look for PHY_ERROR with significant CRC/symbol increase
        phy = [e for e in events if e.type == EventType.PHY_ERROR
               and (e.data.get("delta_crc", 0) > 10
                    or e.data.get("delta_symbol", 0) > 5)]

        evidence = []
        timeline = []
        counter = []

        if flaps:
            evidence.extend(e.id for e in flaps)
            timeline.extend(flaps)
        if phy:
            evidence.extend(e.id for e in phy)
            timeline.extend(phy)

        if not evidence:
            return None

        # Counter: NIC reset / MCE → hardware not optical
        nic_reset = [e for e in events if e.type == EventType.NIC_RESET]
        mce = [e for e in events if e.type == EventType.MCE]
        if nic_reset:
            counter.append(("NIC reset detected - NIC/driver fault more likely than GPON",
                            nic_reset[0].id))
        if mce:
            counter.append(("MCE detected - hardware fault, not optical",
                            mce[0].id))

        confidence = 0.7 if flaps else 0.6
        if phy:
            confidence = max(confidence, 0.65)
        if counter:
            confidence -= 0.2
        confidence = max(0.3, min(0.85, confidence))

        return Finding(
            primary_cause=("Likely GPON/ONT optical degradation (cannot verify directly - "
                           "ONT not accessible)"),
            confidence=confidence,
            evidence=evidence,
            counter_evidence=[(m, i) for m, i in counter],
            timeline=sorted(set(timeline), key=lambda e: e.ts),
            reasoning=(
                "Detected CRC/symbol errors and/or rapid carrier flap consistent with "
                "GPON optical signal degradation. ONT (HBG1000R) is not accessible "
                "for direct optical power monitoring. Recommend contacting ISP to "
                "check OLT RX optical level at the splitter/customer premises."
            ),
        )
