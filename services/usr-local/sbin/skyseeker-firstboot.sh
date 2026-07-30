#!/bin/bash
# Regenerate the per-device identity that must never be shared between rigs.
# The golden image ships without SSH host keys and with an empty machine-id;
# this runs once on first boot and is a no-op on every boot after that.
set -u

if ! ls /etc/ssh/ssh_host_*_key >/dev/null 2>&1; then
    ssh-keygen -A
fi

if [ ! -s /etc/machine-id ]; then
    systemd-machine-id-setup
fi

exit 0
