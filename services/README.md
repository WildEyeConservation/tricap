# SkySeeker system files

These mirror files that live outside the repo on the device:

- `systemd/` -> `/etc/systemd/system/`
- `journald.conf.d/` -> `/etc/systemd/journald.conf.d/`
- `modprobe.d/` -> `/etc/modprobe.d/`
- `udev-rules.d/` -> `/etc/udev/rules.d/`
- `usr-local/sbin/` -> `/usr/local/sbin/`
- `usr-local/bin/` -> `/usr/local/bin/`

The portal now runs from inside the repo (`/home/radxa/tricap/skyseeker-standalone/captive_portal.py`),
so a `git pull` updates it. After pulling a change that touches anything in this
directory, re-install and reload:

```sh
sudo cp services/systemd/* /etc/systemd/system/
sudo install -D -m 0644 services/journald.conf.d/skyseeker-journald.conf /etc/systemd/journald.conf.d/skyseeker-journald.conf
sudo cp services/modprobe.d/* /etc/modprobe.d/
sudo cp services/udev-rules.d/* /etc/udev/rules.d/
sudo cp services/usr-local/sbin/* /usr/local/sbin/
sudo cp services/usr-local/bin/* /usr/local/bin/
sudo systemctl daemon-reload
sudo systemctl restart systemd-journald
sudo systemctl enable --now skyseeker-ap-monitor.timer
sudo systemctl enable --now skyseeker-ap-watchdog.timer
sudo systemctl restart skyseeker-portal.service
# Restart tricap.service separately, only when tricap application code changed.
```

The modprobe options for the `8192eu` driver take effect when the module next
loads (reboot, or a manual module reload with hostapd stopped). The udev rule
and the `power_save off` assert in `skyseeker-ap-autodetect.sh` apply from the
next boot on their own.

`skyseeker-ap-monitor.timer` logs a one-line AP/DHCP/PCIe health snapshot to the
journal every 15 seconds (`journalctl -t skyseeker-ap-monitor` or
`journalctl -u skyseeker-ap-monitor.service`). It is log-only and takes no
recovery action. The journald drop-in makes logs persistent (bounded at 200 MB)
so a field failure can be analysed after a reboot or power cycle.

`skyseeker-ap-watchdog.timer` checks the AP path end to end every 15 seconds
(hostapd via its control socket, driver AP mode, link state, dnsmasq). Three
consecutive failures restart the failed service - hostapd, or dnsmasq for the
"AP visible but no DHCP" case. It has **no reboot path in the code** and a
10-minute cooldown between restarts, so a false positive can never loop. Every
decision is logged. For maintenance, `touch /run/skyseeker-ap-watchdog.disabled`
(clears on reboot). It needs hostapd's control socket, which
`skyseeker-ap-autodetect.sh` enables in the hostapd config at boot; the first
hostapd (re)start after that change brings the socket up.

On devices flashed from the 2026-07-29 (or earlier) image, `skyseeker-portal.service`
still points at the old copy in `/home/radxa/skyseeker-standalone/`. Run the block
above once to switch them over; the old directory can then be removed.
