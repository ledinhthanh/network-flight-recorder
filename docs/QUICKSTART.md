# NFR Quick Start

## Trong 30 giây

```bash
ssh root@10.0.0.2
nfr report
```

Đọc kết quả:
- **Cause:** nguyên nhân gốc
- **Confidence:** độ tin cậy (0-100%)
- **Reasoning:** giải thích tại sao
- **Timeline:** chuỗi sự kiện

## Trong 2 phút

```bash
nfr status          # Tổng quan hôm nay
nfr timeline        # Xem timeline chi tiết
nfr report          # RCA findings
nfr search "error"  # Tìm event cụ thể
```

## Use cases thường gặp

### "Mạng chậm / chập chờn"

```bash
nfr report
# Look for: PPPoE reconnects, carrier flap, WAN state changes
```

### "Hôm qua ~14h mất mạng"

```bash
nfr index                       # List days
ls /var/lib/nfr/logs/           # All dates
cat /var/lib/nfr/logs/2026-07-07/timeline.txt
cat /var/lib/nfr/logs/2026-07-07/evidence.json
```

### "Kiểm tra sức khỏe hệ thống"

```bash
nfr doctor
systemctl status nfr.service
```

### "Tìm khi PPPoE reconnect"

```bash
nfr search "ppp"
nfr search "lcp"
nfr search "padt"
```

## Service management

```bash
# Status
systemctl status nfr.service

# Start/stop
sudo systemctl start nfr.service
sudo systemctl stop nfr.service

# Restart (sau khi đổi config)
sudo systemctl restart nfr.service

# Logs
journalctl -u nfr.service -f        # Live
journalctl -u nfr.service -n 100   # Last 100
journalctl -u nfr.service --since "1 hour ago"
```

## Cấu hình

```bash
sudo nano /etc/nfr/nfr.yaml
sudo systemctl restart nfr.service
```

## Tips

- NFR chạy như root, lắng nghe kernel events + OpenWrt state
- Events được ghi vào JSONL atomic - an toàn khi kill -9
- File lưu theo ngày: `/var/lib/nfr/logs/<YYYY-MM-DD>/`
- Sau 30 ngày tự động gzip
