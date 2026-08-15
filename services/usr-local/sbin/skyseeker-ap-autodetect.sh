#!/bin/bash
# SkySeeker AP interface auto-detect. Runs at every boot, before the AP stack.
#
# Why: the rescue AP belongs on the USB high-gain radio, while the onboard
# Broadcom radio searches for the phone recovery hotspot. Interface names may
# change on cloned units, so detect the AP radio by driver and rewrite stale
# pins.
#
# Detection: a wireless interface driven by rtl8192eu/8192eu (the USB radio).
#
# Testing: pass a directory as $1 to treat it as the filesystem root
# (e.g. skyseeker-ap-autodetect.sh /tmp/fakeroot). Service reloads
# (NetworkManager) are skipped in that mode.
set -u

ROOT="${1:-}"
LOG_TAG="skyseeker-ap-autodetect"
PIN_FILES=(
    "$ROOT/etc/default/skyseeker-standalone"
    "$ROOT/etc/hostapd/hostapd-skyseeker.conf"
    "$ROOT/etc/dnsmasq.d/skyseeker.conf"
    "$ROOT/etc/NetworkManager/conf.d/90-skyseeker-standalone.conf"
)

log() {
    if [ -z "$ROOT" ]; then logger -t "$LOG_TAG" "$1"; fi
    echo "$LOG_TAG: $1"
}

ensure_hostapd_control() {
    local conf="$ROOT/etc/hostapd/hostapd-skyseeker.conf"
    [ -f "$conf" ] || return 0
    if ! grep -q '^ctrl_interface=' "$conf"; then
        printf '\n# Local control socket used by the AP liveness watchdog.\nctrl_interface=/run/hostapd\n' >> "$conf"
        log "enabled hostapd control socket in $conf"
    fi
}

detect_ap_iface() {
    local i name driver
    for i in "$ROOT"/sys/class/net/*; do
        name=$(basename "$i")
        [ -d "$i/wireless" ] || continue
        driver=$(basename "$(readlink -f "$i/device/driver" 2>/dev/null)" 2>/dev/null)
        case "$driver" in
            rtl8192eu|8192eu) echo "$name"; return 0 ;;
        esac
    done
    return 1
}

# USB enumeration can lag boot: wait up to 30 s for the AP interface. A
# synthetic test root is checked once.
iface=""
attempts=30
[ -z "$ROOT" ] || attempts=1
for _ in $(seq 1 "$attempts"); do
    iface=$(detect_ap_iface) && break
    sleep 1
done
if [ -z "$iface" ]; then
    log "no USB RTL8192EU AP adapter found after 30s; leaving configs untouched"
    exit 0
fi

env_file="$ROOT/etc/default/skyseeker-standalone"
if [ ! -f "$env_file" ]; then
    log "$env_file missing; is this a standalone unit? nothing to do"
    exit 0
fi
pinned=$(sed -n 's/^AP_IFACE=//p' "$env_file" | head -1)
if [ -z "$pinned" ]; then
    log "no AP_IFACE in $env_file; nothing to do"
    exit 0
fi

ensure_hostapd_control

if [ "$iface" = "$pinned" ]; then
    exit 0  # names match — the common case on the original unit
fi

log "adapter is $iface but configs pin $pinned; rewriting"
for f in "${PIN_FILES[@]}"; do
    if [ -f "$f" ] && grep -q "$pinned" "$f"; then
        sed -i "s/$pinned/$iface/g" "$f"
        log "updated $f"
    fi
done

if [ -z "$ROOT" ]; then
    # Make NetworkManager release the USB radio to hostapd.
    nmcli general reload conf 2>/dev/null || true
    nmcli general reload 2>/dev/null || true
    # The reload is asynchronous. On a freshly cloned card hostapd can start
    # while wpa_supplicant is still tearing this interface down, then exit
    # cleanly when that teardown resets the radio. Give the handoff time to
    # finish before systemd advances to hostapd.service.
    sleep 2
fi
log "done: AP interface is now $iface"
exit 0
