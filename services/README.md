# SkySeeker system files

These mirror files that live outside the repo on the device:

- `systemd/` -> `/etc/systemd/system/`
- `journald.conf.d/` -> `/etc/systemd/journald.conf.d/`
- `usr-local/sbin/` -> `/usr/local/sbin/`
- `usr-local/bin/` -> `/usr/local/bin/`

The portal now runs from inside the repo (`/home/radxa/tricap/skyseeker-standalone/captive_portal.py`),
so a `git pull` updates it. After pulling a change that touches anything in this
directory, re-install and reload:

```sh
sudo cp services/systemd/* /etc/systemd/system/
sudo install -D -m 0644 services/journald.conf.d/skyseeker-journald.conf /etc/systemd/journald.conf.d/skyseeker-journald.conf
sudo cp services/usr-local/sbin/* /usr/local/sbin/
sudo cp services/usr-local/bin/* /usr/local/bin/
sudo systemctl daemon-reload
sudo systemctl restart systemd-journald
sudo systemctl enable --now skyseeker-ap-monitor.timer
sudo systemctl restart skyseeker-portal.service
# Restart tricap.service separately, only when tricap application code changed.
```

`skyseeker-ap-monitor.timer` logs a one-line AP/DHCP/PCIe health snapshot to the
journal every 15 seconds (`journalctl -t skyseeker-ap-monitor` or
`journalctl -u skyseeker-ap-monitor.service`). It is log-only and takes no
recovery action. The journald drop-in makes logs persistent (bounded at 200 MB)
so a field failure can be analysed after a reboot or power cycle.

On devices flashed from the 2026-07-29 (or earlier) image, `skyseeker-portal.service`
still points at the old copy in `/home/radxa/skyseeker-standalone/`. Run the block
above once to switch them over; the old directory can then be removed.
