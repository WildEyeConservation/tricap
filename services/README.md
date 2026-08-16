# SkySeeker system files

These mirror files that live outside the repo on the device:

- `systemd/` -> `/etc/systemd/system/`
- `usr-local/sbin/` -> `/usr/local/sbin/`
- `usr-local/bin/` -> `/usr/local/bin/`

The portal now runs from inside the repo (`/home/radxa/tricap/skyseeker-standalone/captive_portal.py`),
so a `git pull` updates it. After pulling a change that touches anything in this
directory, re-install and reload:

```sh
sudo cp services/systemd/* /etc/systemd/system/
sudo cp services/usr-local/sbin/* /usr/local/sbin/
sudo cp services/usr-local/bin/* /usr/local/bin/
sudo systemctl daemon-reload
sudo systemctl restart skyseeker-portal.service tricap.service
```

On devices flashed from the 2026-07-29 (or earlier) image, `skyseeker-portal.service`
still points at the old copy in `/home/radxa/skyseeker-standalone/`. Run the block
above once to switch them over; the old directory can then be removed.
