"""Cross-host and cross-layer event correlation.

When Proxmox NIC flap and OpenWrt WAN down occur within seconds of each other,
the cause is upstream (GPON/OLT), not inside Proxmox.
"""
from collections import defaultdict
from datetime import timedelta
from typing import List, Dict, Tuple

from nfr.models import Event, EventType, Severity, Finding


# Groups of related event types that suggest a common upstream cause
LAYER_GROUPS = {
    "physical": [EventType.CARRIER_DOWN, EventType.CARRIER_UP,
                 EventType.NIC_RESET, EventType.PHY_ERROR],
    "pppoe": [EventType.PPP_LCP_TIMEOUT, EventType.PPP_PADT,
              EventType.PPP_PADO_TIMEOUT, EventType.PPP_CONNECTED],
    "wan": [EventType.OPENWRT_WAN_DOWN, EventType.OPENWRT_WAN_UP],
    "routing": [EventType.ROUTE_DELETED, EventType.ROUTE_ADDED,
                EventType.GATEWAY_UNREACHABLE, EventType.GATEWAY_REACHABLE],
}


def layer_of(ev_type: EventType) -> str:
    for layer, types in LAYER_GROUPS.items():
        if ev_type in types:
            return layer
    return "other"


def correlate(events: List[Event], window_sec: int = 5) -> List[Finding]:
    """Find clusters of events across layers within a short window.
    Each cluster suggests a single upstream cause affecting all of them.
    """
    if not events:
        return []
    sorted_ev = sorted(events, key=lambda e: e.ts)
    clusters = []
    current = [sorted_ev[0]]
    for ev in sorted_ev[1:]:
        # Add to current cluster if within window of any event in cluster
        if any((ev.ts - c.ts).total_seconds() < window_sec for c in current):
            current.append(ev)
        else:
            if len(current) > 1:
                clusters.append(current)
            current = [ev]
    if len(current) > 1:
        clusters.append(current)

    findings = []
    for cluster in clusters:
        layers = defaultdict(list)
        for ev in cluster:
            layers[layer_of(ev.type)].append(ev)
        # If 2+ layers are represented → high signal
        affected_layers = [l for l in LAYER_GROUPS.keys() if layers.get(l)]
        if len(affected_layers) >= 2:
            all_ids = [ev.id for ev in cluster]
            primary_layer = "physical" if "physical" in affected_layers else affected_layers[0]
            layer_summary = ", ".join(affected_layers)
            confidence = 0.85 + 0.03 * (len(affected_layers) - 2)
            confidence = min(0.95, confidence)
            findings.append(Finding(
                primary_cause="Cross-layer event cluster (likely upstream/GPON)",
                confidence=confidence,
                evidence=all_ids,
                timeline=sorted(cluster, key=lambda e: e.ts),
                reasoning=(
                    "Events across " + str(len(affected_layers)) + " layers (" + layer_summary +
                    ") occurred within " + str(window_sec) + "s window. This simultaneous "
                    "multi-layer behavior suggests a single upstream cause (most likely "
                    "GPON/OLT affecting both Proxmox NIC and OpenWrt PPPoE), not isolated "
                    "component failure."
                ),
            ))
    return findings
