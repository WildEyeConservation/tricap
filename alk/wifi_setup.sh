#!/bin/bash

NETWORK_ID=$(wpa_cli -i wlan0 add_network)
echo $NETWORK_ID
if [ $NETWORK_ID -gt 5 ]
then
  PREV_ID=$((NETWORK_ID - 1))
  wpa_cli remove_network $PREV_ID
fi
# echo "Add ssid"
wpa_cli -i wlan0 set_network $NETWORK_ID ssid \"$1\"
# echo "Add password"
wpa_cli -i wlan0 set_network $NETWORK_ID psk \"$2\"
# echo "Enable"
wpa_cli -i wlan0 enable_network $NETWORK_ID
# echo "Save"
wpa_cli -i wlan0 save_config
# echo "Reconfigure"
wpa_cli -i wlan0 reconfigure
wpa_cli -i wlan0 reassociate $NETWORK_ID