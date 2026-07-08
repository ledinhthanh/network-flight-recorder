# Network Flight Recorder (NFR)

Black box cho network forensics. Khi mất mạng → trả lời trong vài giây: nguyên nhân, bằng chứng, timeline.

## Mục lục
- [Cài đặt](#cài-đặt)
- [Sử dụng nhanh](#sử-dụng-nhanh)
- [Các câu hỏi thường gặp](#các-câu-hỏi-thường-gặp)
- [Tham chiếu lệnh](#tham-chiếu-lệnh)
- [Architecture](#architecture)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)

## Cài đặt

```bash
cd /opt/nfr
bash scripts/install.sh
systemctl status nfr.service
```

Config: `/etc/nfr/nfr.yaml` (OpenWrt collector bật khi đã có SSH key).

## Sử dụng nhanh

### Khi có sự cố mạng

```bash
# Trên máy gateway (10.0.0.2), chạy:

# 1. Xem nhanh
nfr status

# 2. Timeline hôm nay
nfr timeline

# 3. TÌM NGUYÊN NHÂN GỐC (quan trọng nhất)
nfr report
```

### Ví dụ output `nfr report`

```
NFR Report 2026-07-08
============================================================
Status: outage
Events: 47

RCA Findings:
  Cause: Physical layer / carrier loss
  Confidence: 95%
  Evidence: 3 events
  Reasoning: NIC carrier dropped, causing downstream
             ppp_lcp_timeout, openwrt_wan_down.
  Timeline:
    14:23:10 carrier_down: enp1s0 carrier DOWN
    14:23:11 ppp_lcp_timeout: LCP not responding
    14:23:12 openwrt_wan_down: WAN down
```

### Để lưu báo cáo gửi team

```bash
nfr report > /tmp/nfr-report-$(date +%Y%m%d-%H%M).txt
```

## Các câu hỏi thường gặp

| Tôi muốn biết... | Chạy |
|------------------|------|
| Hôm nay có sự cố gì? | `nfr status` |
| Nguyên nhân mất mạng là gì? | `nfr report` |
| Hôm qua có chuyện gì? | `nfr index` |
| 14:23 có event gì? | `nfr search "14:23"` |
| PPPoE có reconnect không? | `nfr search pppoe` |
| Carrier có flap không? | `nfr search carrier` |
| OpenWrt WAN có down không? | `nfr search wan` |
| NFR có chạy không? | `nfr doctor` |
| Xem full timeline | `nfr timeline` |

## Tham chiếu lệnh

### `nfr status`
Xem tổng quan hôm nay.
```
NFR 0.1.0
Date: 2026-07-08
Events: 17
Status: outage
Outages: 3
```

### `nfr today`
Liệt kê events hôm nay, mỗi event 1 dòng.

### `nfr timeline`
Timeline dạng người đọc (`/var/lib/nfr/logs/<date>/timeline.txt`).

### `nfr report`
**Quan trọng nhất.** Chạy rule engine trên events hôm nay, trả về:
- Primary cause
- Confidence (0-1)
- Evidence (event IDs)
- Reasoning
- Timeline

### `nfr index`
Daily index: ngày nào có issue, ngày nào ok.

### `nfr search <query>`
Tìm event theo keyword (case-insensitive).

### `nfr doctor`
Health check: files, permissions, write access.

### `nfr version`
Version number.

## Architecture

```
Collectors (event-driven, low overhead)
├── NIC        → carrier, link state, errors
├── Bridge     → FDB, MAC flap, topology
├── PPP        → LCP, PADT, PADO, sessions
├── Route      → default route changes
├── Host       → kernel (MCE, OOM, lockup), LXC state
└── OpenWrt    → SSH to WAN state + pppd logs

        ↓ events (typed, validated)

EventBus (async pub/sub)
        ↓

Storage
├── JSONL atomic append-only
├── Daily rotation (/var/lib/nfr/logs/YYYY-MM-DD/)
├── Index file (/var/lib/nfr/index.json)
└── Auto gzip after 30 days

        ↓

Rule Engine (RCA)
├── CarrierLossRule     - NIC down → cascade
├── PPPoELCPRule        - LCP without carrier
├── PPPoEPADORule       - ISP no response
├── NICResetRule        - hardware fault
└── BridgeLoopRule      - MAC flapping

        ↓

CLI
└── nfr {status,today,timeline,report,index,search,doctor,version}
```

## Performance

| Metric | Budget | Actual |
|--------|--------|--------|
| CPU | <1% | 0.2% idle |
| RAM | <50MB | 18MB |
| Disk | ~100MB/year | append-only JSONL |
| Latency | <5s detect | event-driven |

## Tests

```bash
cd /opt/nfr
PYTHONPATH=/opt/nfr python3 -m unittest discover -s tests -v
```

Hiện có 14 tests (collector, rule engine, storage, CLI).

## Files & Locations

| Path | Mô tả |
|------|--------|
| `/opt/nfr/nfr/` | Source code |
| `/opt/nfr/tests/` | Unit tests |
| `/opt/nfr/scripts/` | install/uninstall/upgrade |
| `/etc/nfr/nfr.yaml` | Config |
| `/etc/systemd/system/nfr.service` | systemd unit |
| `/usr/local/bin/nfr` | CLI wrapper |
| `/var/lib/nfr/logs/YYYY-MM-DD/` | Daily events (JSONL, timeline, evidence) |
| `/var/lib/nfr/index.json` | Daily index |
| `/var/log/nfr.log` | Service logs |

## Troubleshooting

### Service không start

```bash
systemctl status nfr.service
journalctl -u nfr.service -n 50
```

### OpenWrt collector fail

Check SSH key:
```bash
ssh -i /root/.ssh/id_openwrt root@10.0.0.1 uptime
```

Nếu fail, push key lại:
```bash
PUB=$(cat /root/.ssh/id_openwrt.pub)
pct exec 100 -- sh -c "echo  > /etc/dropbear/authorized_keys"
```

### CPU cao bất thường

```bash
ps -o pid,pcpu,cmd -p $(pgrep -f python3 -m nfr)
journalctl -u nfr.service --since "5 min ago"
```

### Reset storage

```bash
sudo systemctl stop nfr.service
sudo rm -rf /var/lib/nfr/logs/*
sudo systemctl start nfr.service
```

## Uninstall

```bash
bash scripts/uninstall.sh
rm -rf /var/lib/nfr/    # optional: remove data
```

## Upgrade

```bash
bash scripts/upgrade.sh
```

## Version

0.1.0 - Initial release
- 6 collectors
- 5 RCA rules
- 8 CLI commands
- 14 unit tests

## License

Internal use only.
