"""Incident data model."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class IncidentSeverity(Enum):
    """Levels of operational impact.

    INFO: state change, no impact (e.g. recovery from brief flap)
    NOTICE: short blip (<30s), recovered automatically
    WARNING: brief outage worth knowing about
    CRITICAL: sustained outage requiring intervention
    """
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"


# Event type → layer classification for correlation
LAYER_MAP: Dict[str, str] = {
    "carrier_down": "physical",
    "carrier_up": "physical",
    "phy_error": "physical",
    "nic_reset": "physical",
    "ppp_lcp_timeout": "pppoe",
    "ppp_padt": "pppoe",
    "ppp_pado_timeout": "pppoe",
    "ppp_connected": "pppoe",
    "openwrt_wan_down": "wan",
    "openwrt_wan_up": "wan",
    "route_deleted": "routing",
    "route_added": "routing",
    "gateway_unreachable": "routing",
    "gateway_reachable": "routing",
    "dns_failure": "dns",
    "mac_flap": "bridge",
    "bridge_topology_change": "bridge",
    "mce": "hardware",
    "pcie_aer": "hardware",
    "oom": "system",
}

# State transition pairs (down → up). When "up" follows "down", incident can close.
RECOVERY_EVENTS = {
    "carrier_down": "carrier_up",
    "ppp_lcp_timeout": "ppp_connected",
    "openwrt_wan_down": "openwrt_wan_up",
    "gateway_unreachable": "gateway_reachable",
    "route_deleted": "route_added",
}


def layer_of(event_type: str) -> str:
    return LAYER_MAP.get(event_type, "other")


@dataclass
class Incident:
    """A correlated group of events representing one operational issue."""
    id: str
    start_ts: datetime
    end_ts: Optional[datetime] = None
    status: IncidentStatus = IncidentStatus.OPEN
    severity: IncidentSeverity = IncidentSeverity.NOTICE
    layers_affected: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    key_event_types: List[str] = field(default_factory=list)
    raw_event_count: int = 0
    impact_seconds: float = 0.0
    rca_cause: Optional[str] = None
    rca_confidence: Optional[float] = None
    rca_reasoning: Optional[str] = None
    rca_evidence_count: int = 0
    notified: bool = False
    notification_count: int = 0
    last_event_ts: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        d["start_ts"] = self.start_ts.astimezone(timezone.utc).isoformat()
        d["end_ts"] = self.end_ts.astimezone(timezone.utc).isoformat() if self.end_ts else None
        d["last_event_ts"] = self.last_event_ts.astimezone(timezone.utc).isoformat() if self.last_event_ts else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Incident":
        d = dict(d)
        d["status"] = IncidentStatus(d["status"])
        d["severity"] = IncidentSeverity(d["severity"])
        d["start_ts"] = datetime.fromisoformat(d["start_ts"])
        d["end_ts"] = datetime.fromisoformat(d["end_ts"]) if d.get("end_ts") else None
        d["last_event_ts"] = datetime.fromisoformat(d["last_event_ts"]) if d.get("last_event_ts") else None
        return cls(**d)


def new_incident_id(ts: datetime) -> str:
    """Generate a short, deterministic-ish id."""
    suffix = uuid.uuid4().hex[:4]
    return "inc-" + ts.strftime("%Y%m%d-%H%M%S") + "-" + suffix
