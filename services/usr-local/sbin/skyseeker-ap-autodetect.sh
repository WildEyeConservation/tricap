#!/bin/bash
# SkySeeker AP interface auto-detect. Runs at every boot, before the AP stack.
#
# Why: the rescue AP belongs on the USB high-gain radio, while the onboard
# Broadcom radio searches for the phone recovery hotspot. Interface names may
# change on cloned units and the USB dongle model may change between rigs, so
# detect the AP radio by elimination and rewrite stale pins.
#
# Detection: any wireless interface that is not the onboard Broadcom radio
# (driver brcmfmac). If several qualify, the one already pinned in
# /etc/default/skyseeker-standalone wins, then the first by name.
#
# Testing: pass a directory as $1 to treat it as the filesystem root
# (e.g. skyseeker-ap-autodetect.sh /tmp/fakeroot). Service reloads
# (NetworkManager) and iw calls are skipped in that mode.
set -u

ROOT="${1:-}"
LOG_TAG="skyseeker-ap-autodetect"
ONBOARD_DRIVER="brcmfmac"
ENV_FILE="$ROOT/etc/default/skyseeker-standalone"
PIN_FILES=(
    "$ENV_FILE"
    "$ROOT/etc/hostapd/hostapd-skyseeker.conf"
    "$ROOT/etc/dnsmasq.d/skyseeker.conf"
    "$ROOT/etc/NetworkManager/conf.d/90-skyseeker-standalone.conf"
)

log() {
    if [ -z "$ROOT" ]; then logger -t "$LOG_TAG" "$1"; fi
    echo "$LOG_TAG: $1"
}

ensure_hostapd_control() {
    # Enable hostapd's local control socket so the health check can ask it
    # "are you alive" rather than trusting the systemd unit state. Takes
    # effect the next time hostapd (re)starts.
    local conf="$ROOT/etc/hostapd/hostapd-skyseeker.conf"
    [ -f "$conf" ] || return 0
    if ! grep -q '^ctrl_interface=' "$conf"; then
        printf '\n# Local control socket used by SkySeeker health checks.\nctrl_interface=/run/hostapd\n' >> "$conf"
        log "enabled hostapd control socket in $conf"
    fi
}

interface_driver() {
    # sysfs reports the bound driver twice: as DRIVER= in device/uevent and
    # as the device/driver symlink. Prefer the plain file; fall back to the
    # symlink for the rare bus that leaves DRIVER= out of uevent.
    local dev="$ROOT/sys/class/net/$1/device" driver=""
    [ -r "$dev/uevent" ] && driver=$(sed -n 's/^DRIVER=//p' "$dev/uevent" | head -1)
    [ -n "$driver" ] || driver=$(basename "$(readlink -f "$dev/driver" 2>/dev/null)" 2>/dev/null)
    echo "$driver"
}

pinned_iface() {
    [ -f "$ENV_FILE" ] || return 0
    sed -n 's/^AP_IFACE=//p' "$ENV_FILE" | head -1
}

# Print every wireless interface that is not the onboard radio, one per line.
candidate_ifaces() {
    local i name
    for i in "$ROOT"/sys/class/net/*; do
        name=$(basename "$i")
        [ -d "$i/wireless" ] || continue
        [ "$(interface_driver "$name")" = "$ONBOARD_DRIVER" ] && continue
        echo "$name"
    done
}

detect_ap_iface() {
    local candidates pinned
    candidates=$(candidate_ifaces)
    [ -n "$candidates" ] || return 1
    pinned=$(pinned_iface)
    if [ -n "$pinned" ] && grep -qx -- "$pinned" <<< "$candidates"; then
        echo "$pinned"
        return 0
    fi
    head -n 1 <<< "$candidates"
}

supports_ap_mode() {
    # Ask the kernel whether the radio behind the interface can run an AP.
    # Only advisory: a dongle that cannot will fail inside hostapd, so warn
    # early and loudly rather than silently leaving the rig without an AP.
    local phy
    phy=$(basename "$(readlink -f "/sys/class/net/$1/phy80211" 2>/dev/null)" 2>/dev/null)
    [ -n "$phy" ] || return 0
    iw phy "$phy" info 2>/dev/null \
        | sed -n '/Supported interface modes/,/^\t[^\t]/p' \
        | grep -q '^\t\t \* AP$'
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
    log "no USB AP adapter found after 30s (only the onboard $ONBOARD_DRIVER radio is present); leaving configs untouched"
    exit 0
fi

driver=$(interface_driver "$iface")
extra=$(candidate_ifaces | grep -vx -- "$iface" | tr '\n' ' ')
[ -z "$extra" ] || log "several USB radios present (${extra% }); using $iface"
log "AP adapter is $iface (driver ${driver:-unknown})"

if [ -z "$ROOT" ]; then
    if ! supports_ap_mode "$iface"; then
        log "WARNING: $iface (driver ${driver:-unknown}) does not advertise AP mode; hostapd is likely to fail"
    fi
    # Belt-and-braces: assert no runtime power saving on the AP radio every
    # boot. The 8192eu driver-level knobs are pinned in /etc/modprobe.d and
    # the TP-Link USB autosuspend policy in /etc/udev/rules.d; these two lines
    # cover the interface flag and USB autosuspend for whatever dongle is
    # actually plugged in.
    iw dev "$iface" set power_save off 2>/dev/null || true
    echo on > "/sys/class/net/$iface/device/power/control" 2>/dev/null || true
fi

ensure_hostapd_control

if [ ! -f "$ENV_FILE" ]; then
    log "$ENV_FILE missing; is this a standalone unit? nothing to do"
    exit 0
fi
pinned=$(pinned_iface)
if [ -z "$pinned" ]; then
    log "no AP_IFACE in $ENV_FILE; nothing to do"
    exit 0
fi

if [ "$iface" = "$pinned" ]; then
    exit 0  # names match: the common case on the original unit
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
