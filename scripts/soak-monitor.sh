#!/bin/bash
PID=$(pgrep -f "python3 -m nfr" | head -1)
if [ -z "$PID" ]; then
    echo "NFR not running"
    exit 1
fi
LOG=/var/log/nfr-soak.log
while true; do
    RSS=$(ps -o rss= -p $PID 2>/dev/null)
    FD=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
    THREADS=$(ps -o nlwp= -p $PID 2>/dev/null)
    echo "$(date -Iseconds) rss=${RSS}KB fd=$FD threads=$THREADS" >> $LOG
    sleep 30
done
