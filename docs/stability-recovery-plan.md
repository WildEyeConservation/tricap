# Network diagnostics and recovery

SkySeeker recovery is deliberately limited. It may restart a failed Wi-Fi AP
service, but it never reboots or power-cycles the device automatically.

## Network layout

| Component | Role |
|---|---|
| TP-Link RTL8192EU USB adapter | Runs the `skyseeker` access point through hostapd |
| dnsmasq | Assigns addresses on `192.168.50.0/24` |
| Onboard Broadcom Wi-Fi | Joins an internet uplink or the `skyseeker-rescue` hotspot |
| Ethernet | Direct laptop maintenance on `192.168.51.0/24` |
| NetBird | Provides remote access whenever an internet uplink is available |
| Flask | Serves the dashboard and API directly on port 80 |

The USB adapter is never used as an internet client. NetworkManager manages the
onboard radio and wired maintenance profile, and leaves the AP adapter to
hostapd. A directly connected laptop receives an address automatically and can
reach SSH or Flask at `192.168.51.1`.

## Automatic behavior

### Rescue hotspot

`skyseeker-recovery-scan.timer` checks every 30 seconds. If the onboard radio
already has any active connection, the scan exits without touching it. If it is
disconnected, the scanner looks for `skyseeker-rescue` and activates the
pre-provisioned profile when visible.

The scanner does not start, stop, or reconfigure NetBird. The NetBird service
handles network changes itself and reconnects after an uplink becomes usable.

### AP health and recovery

`skyseeker-health.timer` runs every 15 seconds. Each run records:

- hostapd, dnsmasq, Flask, and NetBird service state;
- AP interface, driver, link, control socket, station count, and weakest signal;
- internal storage mount state;
- PCIe/NVMe error count, temperature, load, and available memory.

The snapshot is written to the persistent system journal. If hostapd, its AP
interface, its control socket, or dnsmasq fails three consecutive checks, the
tool restarts only the failed service. A ten-minute cooldown prevents repeated
restarts. Create `/run/skyseeker-health.disabled` to disable recovery actions
during maintenance; diagnostics continue and the marker clears at reboot.

There is no automatic reboot path and no systemd hardware watchdog. Warm resets
on this Rockchip/NVMe platform can leave PCIe in a failed state, so a persistent
kernel, PCIe, or NVMe failure requires a deliberate full power cycle.

Flask is supervised separately by `tricap.service` with `Restart=always`.

## Diagnostics

The normal dashboard exposes component, uplink, and NetBird state. For a full
read-only snapshot over NetBird SSH or a local console, run:

```sh
sudo /usr/local/sbin/skyseeker-health
```

Historical snapshots and recovery decisions are available with:

```sh
journalctl -u skyseeker-health.service
journalctl -u skyseeker-recovery-scan.service
```

Useful service checks are:

```sh
systemctl status tricap.service hostapd.service dnsmasq.service netbird.service
systemctl status skyseeker-health.timer skyseeker-recovery-scan.timer
```

## Failure guide

| Symptom | Likely boundary | Action |
|---|---|---|
| AP visible but clients receive no address | dnsmasq | Health recovery restarts dnsmasq after three failures |
| AP disappears or hostapd control fails | hostapd or USB radio | Health recovery restarts hostapd after three failures |
| Dashboard unavailable while AP works | Flask | `tricap.service` restarts Flask; inspect its journal |
| AP and NetBird are unavailable | Wi-Fi paths | Connect a laptop directly by Ethernet and SSH to `192.168.51.1` |
| NetBird unavailable | Internet uplink or NetBird service | Check recovery-scan and NetBird service journals |
| PCIe/NVMe errors or complete lockup | Kernel or hardware | Pull power, wait, and perform a full cold start |

The retired diagnostics web server, duplicate log-only AP monitor, separate AP
watchdog, and UDP address announcer are not part of the current system. Their
useful diagnostics and recovery behavior is covered by `skyseeker-health`, the
dashboard, and NetBird without another HTTP server or discovery loop.
