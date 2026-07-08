"""Configuration loader."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import yaml


@dataclass
class CollectorConfig:
    enabled: bool = True
    interval_sec: int = 300


@dataclass
class NicConfig(CollectorConfig):
    interfaces: List[str] = field(default_factory=list)


@dataclass
class BridgeConfig(CollectorConfig):
    pass


@dataclass
class OpenWrtConfig:
    enabled: bool = False
    host: str = "10.0.0.1"
    port: int = 22
    user: str = "root"
    ssh_key: Optional[str] = None


@dataclass
class DNSConfig(CollectorConfig):
    pass


@dataclass
class NFRConfig:
    nic: NicConfig = field(default_factory=NicConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    dns: DNSConfig = field(default_factory=DNSConfig)
    openwrt: OpenWrtConfig = field(default_factory=OpenWrtConfig)
    log_level: str = "INFO"


def load_config(path: Path = None) -> NFRConfig:
    path = path or Path("/etc/nfr/nfr.yaml")
    if not path.exists():
        return NFRConfig()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    cfg = NFRConfig()
    if "log_level" in raw:
        cfg.log_level = raw["log_level"]
    if "openwrt" in raw:
        ow = raw["openwrt"]
        cfg.openwrt.enabled = ow.get("enabled", False)
        cfg.openwrt.host = ow.get("host", "10.0.0.1")
        cfg.openwrt.port = ow.get("port", 22)
        cfg.openwrt.user = ow.get("user", "root")
        if "ssh_key" in ow:
            cfg.openwrt.ssh_key = ow["ssh_key"]
    if "nic" in raw and "interval_sec" in raw["nic"]:
        cfg.nic.interval_sec = raw["nic"]["interval_sec"]
    if "dns" in raw:
        cfg.dns.enabled = raw["dns"].get("enabled", True)
        if "interval_sec" in raw["dns"]:
            cfg.dns.interval_sec = raw["dns"]["interval_sec"]
    return cfg
