#!/bin/bash
set -e

systemctl stop nfr.service 2>/dev/null || true
systemctl disable nfr.service 2>/dev/null || true
rm -f /etc/systemd/system/nfr.service
rm -f /usr/local/bin/nfr

systemctl daemon-reload

echo "NFR uninstalled. Data in /var/lib/nfr/ preserved."
echo "To remove data: rm -rf /var/lib/nfr/"
