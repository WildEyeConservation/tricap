# SkySeeker system files

These mirror files that live outside the repo on the device:

- `systemd/` -> `/etc/systemd/system/`
- `NetworkManager/system-connections/` -> `/etc/NetworkManager/system-connections/`
- `journald.conf.d/` -> `/etc/systemd/journald.conf.d/`
- `modprobe.d/` -> `/etc/modprobe.d/`
- `udev-rules.d/` -> `/etc/udev/rules.d/`
- `usr-local/sbin/` -> `/usr/local/sbin/`

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
