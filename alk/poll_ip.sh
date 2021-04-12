#!/bin/bash

i=0
while true; do
ip=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
echo "$i $ip"
sleep 1
((i=i+1))
done
