#!/bin/bash
set -e
NFR_HOME=/opt/nfr

# Create user (optional - currently runs as root)
# useradd -r -s /usr/sbin/nologin nfr 2>/dev/null || true

# Install dependencies
apt-get install -y python3-pyroute2 python3-yaml python3-click python3-psutil python3-psutil

# Create storage directory
mkdir -p /var/lib/nfr/logs

# Install systemd
install -m 644 /opt/nfr/nfr.service /etc/systemd/system/ 2>/dev/null || cp /opt/nfr/scripts/nfr.service /etc/systemd/system/

# Create config dir
mkdir -p /etc/nfr

# Install CLI wrapper
install -m 755 /usr/local/bin/nfr 2>/dev/null || cp /opt/nfr/scripts/nfr /usr/local/bin/nfr
chmod +x /usr/local/bin/nfr

systemctl daemon-reload
systemctl enable nfr.service
systemctl restart nfr.service

echo "NFR installed. Run: nfr status"
