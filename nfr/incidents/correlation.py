"""Event correlation.

Groups related events into clusters based on time proximity and layer affinity.
Each cluster becomes an Incident.
"""
from collections import defaultdict
from datetime import timedelta
from typing import List, Dict, Tuple

from nfr.incidents.models import Incident, layer_of, IncidentSeverity, IncidentStatus, new_incident_id, RECOVERY_EVENTS
from nfr.models import Event


# Correlation time window per layer-pair affinity (seconds).
# Tighter = events must happen closer together.
CORRELATION_WINDOWS = {
    ("physical", "pppoe"): 5,
    ("pppoe", "wan"): 5,
    ("physical", "wan"): 10,
    ("wan", "routing"): 5,
    ("physical", "routing"): 10,
    ("physical", "pppoe", "wan"): 10,  # wildcard - max
    ("physical", "pppoe", "wan", "routing"): 15,
}

# Default if no specific rule matches
DEFAULT_WINDOW = 30


def _window_between(layers: set) -> float:
    """Get the correlation window for a set of affected layers."""
    layers_tuple = tuple(sorted(layers))
    # Try exact matches first
    if layers_tuple in CORRELATION_WINDOWS:
        return CORRELATION_WINDOWS[layers_tuple]
    # Try wildcard matches (max)
    for keys, window in CORRELATION_WINDOWS.items():
        if all(l in layers_tuple for l in keys):
            return window
    return DEFAULT_WINDOW


def cluster(events: List[Event]) -> List[List[Event]]:
    """Group events into clusters by time proximity + shared/correlated layers.

    Within a cluster: events are close enough in time AND share at least one
    "adjacent" layer relationship.
    Events from unrelated layers (e.g. hardware MCE + DNS) cluster separately.
    """
    if not events:
        return []
    sorted_ev = sorted(events, key=lambda e: e.ts)
    clusters: List[List[Event]] = []
    current = [sorted_ev[0]]
    cur_layers = {layer_of(sorted_ev[0].type.value)}
    for ev in sorted_ev[1:]:
        ev_layer = layer_of(ev.type.value)
        # Time proximity to current cluster (any event in cluster)
        time_ok = False
        for c in current:
            if (ev.ts - c.ts).total_seconds() <= _window_between(cur_layers):
                time_ok = True
                break
        # Layer affinity: same layer OR adjacent in correlation graph
        layer_ok = (
            ev_layer in cur_layers
            or any(_window_between(cur_layers | {ev_layer}) < DEFAULT_WINDOW
                   for _ in [None])
        )
        if time_ok and (ev_layer in cur_layers or ev_layer == "physical"):
            current.append(ev)
            cur_layers.add(ev_layer)
        else:
            clusters.append(current)
            current = [ev]
            cur_layers = {ev_layer}
    if current:
        clusters.append(current)
    return clusters


def severity_for_events(items) -> IncidentSeverity:
    """Compute severity from events or type strings."""
    critical_types = {"mce", "pcie_aer", "oom", "nic_reset"}
    warn_types = {"carrier_down", "ppp_lcp_timeout", "ppp_padt",
                  "openwrt_wan_down", "gateway_unreachable"}
    notice_types = {"ppp_pado_timeout", "dns_failure", "route_deleted",
                    "mac_flap", "bridge_topology_change", "phy_error"}
    types_seen = set()
    for it in (items if isinstance(items, list) else [items]):
        if hasattr(it, "type"):
            types_seen.add(it.type.value)
        else:
            types_seen.add(str(it))
    if types_seen & critical_types:
        return IncidentSeverity.CRITICAL
    if types_seen & warn_types:
        return IncidentSeverity.WARNING
    if types_seen & notice_types:
        return IncidentSeverity.NOTICE
    return IncidentSeverity.INFO
