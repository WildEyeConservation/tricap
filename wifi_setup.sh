#!/bin/bash
# wifi_setup.sh  —  idempotent, adapter-independent Wi-Fi setup for the tricap rig.
#
# Ensures a NetworkManager profile for <ssid>/<password> exists and is up — but
# ONLY changes things when something actually differs. It never re-writes the
# PSK or bounces a healthy connection.
#
# Why this matters: tricap's app/__init__.py runs this at EVERY startup. The
# previous version re-applied the PSK every time, which made NetworkManager
# tear the connection down and reconnect (~5 s after it first associated). That
# self-inflicted disconnect/reconnect raced with the AP/driver/DHCP at boot and
# intermittently left the rig OFF the hotspot. Making this a no-op when already
# connected removes that churn.
#
# It also sets connection.autoconnect-retries=0 (retry forever) so a genuine
# transient failure self-heals instead of giving up after 4 attempts.
#
# Always exits 0 so it can never crash tricap at start-up.
#
# Usage:  wifi_setup.sh <ssid> <password>     (runs as root; tricap runs as root)

ssid="$1"
psk="$2"

if [ -z "$ssid" ] || [ -z "$psk" ]; then
    echo "usage: wifi_setup.sh <ssid> <password>" >&2
    exit 0
fi

export PATH=/usr/sbin:/sbin:/usr/bin:/bin

# Return the name of any active Wi-Fi connection. The onboard radio may already
# be using a recovery or operator-supplied hotspot, which must take precedence
# over the legacy ESS-ops default requested by app/__init__.py.
active_wifi_name() {
    nmcli -t -f NAME,TYPE,STATE connection show --active 2>/dev/null |
        awk -F: '$2 == "802-11-wireless" && $3 == "activated" { print $1; exit }'
}

# Is the named connection currently active (connected)?
is_active() {
    nmcli -t -f NAME,STATE connection show --active 2>/dev/null | grep -Fxq "$ssid:activated"
}

active_wifi="$(active_wifi_name)"
if [ -n "$active_wifi" ] && [ "$active_wifi" != "$ssid" ]; then
    echo "wifi_setup: '$active_wifi' already connected — preserving current uplink"
    exit 0
fi

if nmcli -t -f NAME connection show | grep -Fxq "$ssid"; then
    # Profile exists. Only touch the PSK if it has actually changed — re-writing
    # the same secret is what triggered the boot-time reconnect churn.
    cur_psk="$(nmcli -s -g 802-11-wireless-security.psk connection show "$ssid" 2>/dev/null)"
    if [ "$cur_psk" != "$psk" ]; then
        echo "wifi_setup: psk for '$ssid' changed — updating profile"
        nmcli connection modify "$ssid" \
            802-11-wireless-security.key-mgmt wpa-psk \
            802-11-wireless-security.psk "$psk" \
            connection.autoconnect yes \
            connection.autoconnect-priority 10 \
            connection.autoconnect-retries 0 || true
    fi

    # Bring it up ONLY if it isn't already connected (no churn on a healthy boot).
    if is_active; then
        echo "wifi_setup: '$ssid' already connected — nothing to do"
    else
        echo "wifi_setup: '$ssid' not active — bringing it up"
        nmcli -w 10 connection up "$ssid" >/dev/null 2>&1 || true
    fi
    exit 0
fi

# Profile does not exist yet (e.g. the mobile app pushed a brand-new network).
echo "wifi_setup: creating profile '$ssid'"
nmcli connection add type wifi con-name "$ssid" ssid "$ssid" \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.psk "$psk" \
    connection.autoconnect yes \
    connection.autoconnect-priority 10 \
    connection.autoconnect-retries 0 || true
nmcli -w 10 connection up "$ssid" >/dev/null 2>&1 || true
exit 0
