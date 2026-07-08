"""Type-safe dataclasses for NFR."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
import uuid


class EventType(str, Enum):
    CARRIER_DOWN = "carrier_down"
    CARRIER_UP = "carrier_up"
    NIC_RESET = "nic_reset"
    NIC_LINK_SPEED_CHANGE = "nic_link_speed_change"
    PHY_ERROR = "phy_error"
    BRIDGE_TOPOLOGY_CHANGE = "bridge_topology_change"
    MAC_FLAP = "mac_flap"
    ROUTE_ADDED = "route_added"
    ROUTE_DELETED = "route_deleted"
    PPP_LCP_TIMEOUT = "ppp_lcp_timeout"
    PPP_PADO_TIMEOUT = "ppp_pado_timeout"
    PPP_PADT = "ppp_padt"
    PPP_CONNECTED = "ppp_connected"
    GATEWAY_UNREACHABLE = "gateway_unreachable"
    GATEWAY_REACHABLE = "gateway_reachable"
    DNS_FAILURE = "dns_failure"
    OPENWRT_WAN_DOWN = "openwrt_wan_down"
    OPENWRT_WAN_UP = "openwrt_wan_up"
    KERNEL_SOFT_LOCKUP = "kernel_soft_lockup"
    KERNEL_HUNG_TASK = "kernel_hung_task"
    NETDEV_WATCHDOG = "netdev_watchdog"
    PCIE_AER = "pcie_aer"
    MCE = "mce"
    OOM = "oom"
    VM_STOP = "vm_stop"
    VM_CRASH = "vm_crash"
    SNAPSHOT = "snapshot"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Event:
    """Normalized network event."""
    type: EventType
    severity: Severity
    ts: datetime
    source: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    prev_state: Optional[str] = None
    new_state: Optional[str] = None
    id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["severity"] = self.severity.value
        d["ts"] = self.ts.astimezone(timezone.utc).isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d["type"] = EventType(d["type"])
        d["severity"] = Severity(d["severity"])
        d["ts"] = datetime.fromisoformat(d["ts"])
        d.pop("id", None)
        return cls(**d)


@dataclass
class Finding:
    """Root cause analysis finding."""
    primary_cause: str
    confidence: float
    evidence: List[str]  # event IDs
    counter_evidence: List[str] = field(default_factory=list)
    timeline: List[Event] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "primary_cause": self.primary_cause,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "counter_evidence": [
                {"description": d, "event_id": i} if isinstance(d, tuple) else d
                for d in self.counter_evidence
            ] if self.counter_evidence else [],
            "reasoning": self.reasoning,
            "timeline": [e.to_dict() for e in self.timeline],
        }


@dataclass
class ResourceState:
    """State of a tracked resource."""
    name: str
    resource_type: str
    state: str
    last_update: datetime
    extra: Dict[str, Any] = field(default_factory=dict)
