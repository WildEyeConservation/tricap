#!/bin/bash

INTERVAL_SECONDS="${UDP_IP_INTERVAL_SECONDS:-5}"

while true; do
    # AP-only operation intentionally has no default route. In that state there
    # is nowhere to announce the rig address, so do nothing instead of invoking
    # netcat with an empty destination every five seconds.
    gateway_ip=$(ip -4 route show default 2>/dev/null | awk 'NR == 1 {print $3}')
    if [ -n "$gateway_ip" ]; then
        # Announce the address on the interface that can actually reach the
        # gateway, rather than whichever address hostname happens to list first.
        ip_address=$(ip -4 route get "$gateway_ip" 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')
        if [ -n "$ip_address" ]; then
            printf '%s' "$ip_address" | timeout 2 nc -u -w 1 "$gateway_ip" 12345 >/dev/null 2>&1 || true
        fi
    fi

    [ "${UDP_IP_ONCE:-0}" = "1" ] && exit 0
    sleep "$INTERVAL_SECONDS"
done
