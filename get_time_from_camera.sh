#!/bin/bash
DATETIME=`gphoto2 --get-config datetime`
if [ $? -ne 0 ]; then
    echo "some problem with gphoto2, probably no cameras connected"
    exit 0
fi

EPOCH=`echo "$DATETIME" | grep Current | awk '{print $2}'`
if [[ ! $EPOCH =~ [0-9]{10} ]]; then
        echo "gphoto2 did not return a usable time."
        exit 0
fi

NEWTIME=`date --date @$EPOCH`
echo "Setting time to $NEWTIME"
date -s @$EPOCH
