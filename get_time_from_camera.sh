#!/bin/bash
# Let pending USB device events finish before gphoto2 opens a PTP session.
/usr/bin/udevadm settle --timeout=30 || true

DATETIME=$(timeout 10 gphoto2 --get-config datetime)
if [ $? -ne 0 ]; then
    echo "gphoto2 could not read camera time; Sony discovery will retry later"
    # Give the kernel time to release any PTP/USB claim before the Sony SDK.
    sleep 2
    exit 0
fi

EPOCH=$(echo "$DATETIME" | grep Current | awk '{print $2}')
if [[ ! $EPOCH =~ [0-9]{10} ]]; then
    echo "gphoto2 did not return a usable time"
    sleep 2
    exit 0
fi

echo "Setting time from camera epoch $EPOCH"
date -s "@$EPOCH"

# gphoto2 and the Sony SDK use the same camera USB/PTP interface.  Do not start
# the SDK in the instant after gphoto2 closes its session.
sleep 2
