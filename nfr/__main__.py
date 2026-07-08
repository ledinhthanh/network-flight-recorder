"""NFR Daemon entry point - all collectors integrated."""
import signal
import sys
import threading
import time
from datetime import datetime

from nfr.collectors.nic import NICCollector
from nfr.collectors.ppp import PPPCollector
from nfr.collectors.bridge import BridgeCollector
from nfr.collectors.route import RouteCollector
from nfr.collectors.host import HostCollector
from nfr.collectors.arp import ARPCollector
from nfr.collectors.edac import EDACCollector
from nfr.collectors.pmtu import PMTUCollector
from nfr.collectors.dns import DNSCollector
from nfr.collectors.openwrt import OpenWrtCollector
from nfr.config import load_config, OpenWrtConfig
from nfr.models import EventType
from nfr.core.eventbus import EventBus
from nfr.core.snapshot import SnapshotService, nic_stats_provider, host_stats_provider
from nfr.core.state import StateStore
from nfr.health.selfcheck import SelfHealth
from nfr.notifier import Notifier
from nfr.logging_setup import setup_logging
from nfr.storage.journal import append_event
from nfr.storage.index import update_day
from nfr.storage.rotation import rotate_old
from nfr.timeline.builder import write_timeline, build_summary
from nfr.rules.engine import RuleEngine
from nfr.version import __version__


def write_evidence(date, findings):
    if not findings:
        return
    from nfr.constants import STORAGE_LOGS
    out_dir = STORAGE_LOGS / date
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    p = out_dir / "evidence.json"
    p.write_text(json.dumps([f.to_dict() for f in findings], indent=2, default=str))


def main():
    log = setup_logging("INFO")
    log.info("NFR %s starting", __version__)

    cfg = load_config()
    log.info("config loaded (log_level=%s)", cfg.log_level)

    bus = EventBus()
    state = StateStore()
    health = SelfHealth()
    engine = RuleEngine()
    notifier = Notifier()

    # Persistence: all events go to journal
    def persist(ev):
        append_event(ev)
    bus.subscribe(persist)

    # State transitions
    def track_state(ev):
        # NIC carrier
        if ev.type in (EventType.CARRIER_DOWN, EventType.CARRIER_UP):
            iface = ev.data.get("interface")
            if iface:
                state.set(iface, "nic", ev.new_state.lower(),
                          prev_state=ev.prev_state.lower() if ev.prev_state else None,
                          source=ev.source, event_type=ev.type, severity=ev.severity,
                          message=ev.message, extra=ev.data)
        # PPPoE
        elif ev.type in (EventType.PPP_CONNECTED, EventType.PPP_LCP_TIMEOUT,
                         EventType.PPP_PADO_TIMEOUT, EventType.PPP_PADT):
            state.set("pppoe", "ppp",
                      "connected" if ev.type == EventType.PPP_CONNECTED else "disconnected",
                      source=ev.source, event_type=ev.type, severity=ev.severity,
                      message=ev.message, extra=ev.data)
        # WAN
        elif ev.type in (EventType.OPENWRT_WAN_UP, EventType.OPENWRT_WAN_DOWN):
            state.set("wan", "openwrt", "up" if ev.type == EventType.OPENWRT_WAN_UP else "down",
                      source=ev.source, event_type=ev.type, severity=ev.severity,
                      message=ev.message, extra=ev.data)
    bus.subscribe(track_state)

    # Heartbeat tracker
    def heartbeat(ev):
        if ev.type != EventType.SNAPSHOT:
            health.heartbeat("eventbus")

    # Initialize collectors
    collectors = []
    if getattr(cfg.nic, "enabled", True):
        collectors.append(NICCollector(bus=bus))
    collectors.append(PPPCollector(bus=bus))
    collectors.append(BridgeCollector(bus=bus))
    collectors.append(RouteCollector(bus=bus))
    collectors.append(HostCollector(bus=bus))
    collectors.append(ARPCollector(bus=bus))
    collectors.append(EDACCollector(bus=bus))
    collectors.append(PMTUCollector(bus=bus))
    if getattr(getattr(cfg, "dns", None), "enabled", False):
        collectors.append(DNSCollector(bus=bus))
    if getattr(cfg.openwrt, "enabled", False):
        collectors.append(OpenWrtCollector(bus=bus, cfg=cfg.openwrt))
    for c in collectors:
        health.heartbeat(c.name)
    for c in collectors:
        c.start()

    # Snapshot service
    snap = SnapshotService(interval_sec=300, providers={
        "nic": nic_stats_provider,
        "host": host_stats_provider,
    })
    snap.on_snapshot(lambda ev: (append_event(ev), health.heartbeat("snapshot")))
    snap.start()

    # Bus consumer thread
    bus_thread = threading.Thread(target=bus.run, daemon=True, name="nfr-bus")
    bus_thread.start()
    health.heartbeat("eventbus")

    # Daily summary writer (every 5 min, but only writes if changed)
    def daily_writer():
        last_summary = None
        last_write = 0
        while not stop.is_set():
            try:
                now = time.time()
                if now - last_write > 300:  # 5 min
                    last_write = now
                    date = datetime.now().strftime("%Y-%m-%d")
                    from nfr.storage.journal import read_events
                    events = read_events(date)
                    summary = build_summary(date, events)
                    if summary != last_summary:
                        update_day(date, summary["status"], summary["events"],
                                   top_issue=max(summary["by_type"], key=summary["by_type"].get) if summary["by_type"] else None)
                        # Rule engine
                        findings = engine.run(events)
                        write_evidence(date, findings)
                        write_timeline(date, events)
                        last_summary = summary
                        if notifier.is_configured():
                            for f in findings:
                                if f.confidence >= 0.8:
                                    try:
                                        notifier.notify_finding(f)
                                    except Exception:
                                        pass
            except Exception as e:
                log.debug("daily writer err: %s", e)
            if stop.wait(60):
                break

    stop = threading.Event()
    def sig(*_):
        log.info("signal received")
        stop.set()
    signal.signal(signal.SIGTERM, sig)
    signal.signal(signal.SIGINT, sig)

    writer_thread = threading.Thread(target=daily_writer, daemon=True, name="nfr-writer")
    writer_thread.start()

    log.info("all collectors started, waiting for events")
    try:
        stop.wait()
    finally:
        log.info("stopping...")
        for c in collectors:
            c.stop()
        snap.stop()
        bus.stop()
        try:
            rotate_old(30)
        except Exception:
            pass
        log.info("NFR stopped")


if __name__ == "__main__":
    import os
    os.chdir("/opt/nfr")
    sys.path.insert(0, "/opt/nfr")
    main()
