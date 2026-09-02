# SkySeeker system files

These mirror files that live outside the repo on the device:

- `systemd/` -> `/etc/systemd/system/`
- `NetworkManager/system-connections/` -> `/etc/NetworkManager/system-connections/`
- `journald.conf.d/` -> `/etc/systemd/journald.conf.d/`
- `modprobe.d/` -> `/etc/modprobe.d/`
- `udev-rules.d/` -> `/etc/udev/rules.d/`
- `usr-local/sbin/` -> `/usr/local/sbin/`

## Files and setup not tracked here

The tracked tree is not sufficient on its own to provision a new unit. The
following files and setup are not in this repository and must be copied from a
working rig or written by hand:

| Path or item | Tracked file that needs it | Required contents or setup |
| --- | --- | --- |
| `/etc/default/skyseeker-standalone` | `usr-local/sbin/skyseeker-ap-autodetect.sh` and `systemd/skyseeker-standalone-net.service` | Must define `AP_IFACE=` with the AP interface name and `SUBNET_IP=` with the address to assign to that interface as a `/24`. |
| `/etc/hostapd/hostapd-skyseeker.conf` | `usr-local/sbin/skyseeker-ap-autodetect.sh` | Contents are not tracked; copy from a working rig. The script updates a pinned AP interface name and adds `ctrl_interface=/run/hostapd` if no control interface is configured. |
| `/etc/dnsmasq.d/skyseeker.conf` | `usr-local/sbin/skyseeker-ap-autodetect.sh` | Contents are not tracked; copy from a working rig. The script updates a pinned AP interface name. |
| `/etc/NetworkManager/conf.d/90-skyseeker-standalone.conf` | `usr-local/sbin/skyseeker-ap-autodetect.sh` | Contents are not tracked; copy from a working rig. The script updates a pinned AP interface name. |
| `/home/radxa/tricap` and the `/usr/bin/python3` environment | `systemd/tricap.service` | The repository must be present at `/home/radxa/tricap`, and the dependencies in `pyproject.toml` must be installed for the system Python interpreter used by the service. `uv.lock` governs only the development virtual environment. |
| `/dev/gps` | `app/__init__.py` and `serial_comms/SerialInterface.py` | A udev rule not tracked here must provide this symlink for the u-blox receiver; the application opens it at 921600 baud. Copy the rule from a working rig or write it by hand. |
| `/dev/nvme0n1p1` and `/mnt/ext_cam_storage` | `sensors/cam_manager.py` | The NVMe partition must exist and the mount-point directory must be available so the camera manager can mount the internal capture drive there (the path name is historical; this is the internal NVMe). |
| `/home/radxa/SonySDKWrapper` | `sensors/cam_manager.py` | Must provide the Sony SDK Python wrapper import `sonySDKWrapper.sonyCamera`. Contents are not tracked; copy from a working rig. |
| `netbird` CLI | `app/views/api.py` | Must be installed and available on the service command path so the API can run `netbird up`, `netbird down`, and `netbird status`. |
| NetworkManager profile `skyseeker-rescue` | `usr-local/sbin/skyseeker-recovery-scan` | Must be a provisioned Wi-Fi connection for the rescue hotspot, whose default SSID is also `skyseeker-rescue`, and must be activatable on the onboard Broadcom interface. Contents are not tracked; copy from a working rig or create by hand. |

Flask owns the operator UI and API and listens directly on port 80 through
`tricap.service`. Its request boundary accepts loopback, the
`192.168.50.0/24` access-point subnet, the `192.168.51.0/24` wired maintenance
subnet, and the `100.64.0.0/10` NetBird overlay. It rejects requests from the
internet-uplink Wi-Fi path.

After pulling a change that touches anything in this directory, re-install and
reload:

```sh
sudo cp services/systemd/* /etc/systemd/system/
sudo install -D -m 0600 \
  services/NetworkManager/system-connections/skyseeker-wired-access.nmconnection \
  /etc/NetworkManager/system-connections/skyseeker-wired-access.nmconnection
sudo install -D -m 0644 services/journald.conf.d/skyseeker-journald.conf /etc/systemd/journald.conf.d/skyseeker-journald.conf
sudo cp services/modprobe.d/* /etc/modprobe.d/
sudo cp services/udev-rules.d/* /etc/udev/rules.d/
sudo cp services/usr-local/sbin/* /usr/local/sbin/
sudo systemctl daemon-reload
sudo systemctl restart systemd-journald
sudo nmcli connection reload
sudo systemctl enable --now skyseeker-health.timer
sudo systemctl enable --now skyseeker-recovery-scan.timer
sudo systemctl restart tricap.service
```

## Direct Ethernet maintenance

The wired port is a dedicated last-resort maintenance connection. Connect it
directly to a laptop; NetworkManager gives the laptop an address on
`192.168.51.0/24`. Then use:

```sh
ssh radxa@192.168.51.1
```

The dashboard is also available at `http://192.168.51.1/`. The profile never
installs a default route on the rig, so it cannot replace the onboard Wi-Fi
uplink or interfere with NetBird. Because the port provides DHCP to the directly
connected laptop, do not connect it to a managed Ethernet LAN.

The profile activates automatically when Ethernet carrier appears. If the cable
was already connected while installing it, activate it immediately with:

```sh
sudo nmcli connection up skyseeker-wired-access
```

The modprobe options for the `8192eu` driver take effect when the module next
loads (reboot, or a manual module reload with hostapd stopped). The udev rule
and the `power_save off` assert in `skyseeker-ap-autodetect.sh` apply from the
next boot on their own.

`skyseeker-health.timer` records AP, service, storage, PCIe, temperature, load,
and memory state every 15 seconds. Three consecutive AP failures restart only
the failed hostapd or dnsmasq service, with a ten-minute cooldown and no reboot
path. Run `skyseeker-health` manually for the same read-only snapshot. The
journald drop-in keeps these records across reboots and bounds them at 200 MB.

`skyseeker-recovery-scan.timer` scans for the pre-provisioned
`skyseeker-rescue` hotspot whenever the onboard radio has no active uplink. It
does not replace a working connection and does not manage NetBird. See
[`docs/stability-recovery-plan.md`](../docs/stability-recovery-plan.md) for the
full behavior and incident guide.

On a device with retired web or recovery services, remove them once after
installing the current units:

```sh
sudo systemctl disable --now skyseeker-portal.service skyseeker-diag.service \
  skyseeker-ap-monitor.timer skyseeker-ap-watchdog.timer udp-ip.service
sudo rm -f /etc/systemd/system/skyseeker-portal.service \
  /etc/systemd/system/skyseeker-diag.service \
  /etc/systemd/system/skyseeker-ap-monitor.service \
  /etc/systemd/system/skyseeker-ap-monitor.timer \
  /etc/systemd/system/skyseeker-ap-watchdog.service \
  /etc/systemd/system/skyseeker-ap-watchdog.timer \
  /usr/local/bin/skyseeker-diag.py \
  /usr/local/sbin/skyseeker-ap-monitor \
  /usr/local/sbin/skyseeker-ap-watchdog \
  /etc/systemd/system/udp-ip.service
sudo systemctl daemon-reload
```

The old `/home/radxa/skyseeker-standalone/` directory is no longer used.
