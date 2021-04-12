#!/bin/bash

NETWORK_ID=$(wpa_cli -i wlan0 add_network)
echo $NETWORK_ID
if [ $NETWORK_ID -gt 3 ]
then
  PREV_ID=$((NETWORK_ID - 1))
  wpa_cli remove_network $PREV_ID
fi
wpa_cli -i wlan0 set_network $NETWORK_ID ssid \"$1\"
wpa_cli -i wlan0 set_network $NETWORK_ID psk \"$2\"
wpa_cli -i wlan0 set_network $NETWORK_ID priority 1
wpa_cli -i wlan0 enable_network $NETWORK_ID
# always enable the default networks
wpa_cli -i wlan0 enable_network 0
wpa_cli -i wlan0 enable_network 1
wpa_cli -i wlan0 save_config
wpa_cli -i wlan0 reconfigure
wpa_cli -i wlan0 select_network $NETWORK_ID