#!/bin/bash

ssid=$1

# Check if the network is already added
if wpa_cli list_networks | grep $ssid; then
    echo "Network $ssid is already added"
    exit 0
else
    echo "Network $ssid is not added"
fi

NETWORK_ID=$(wpa_cli -i wlx5c628bcde76d add_network)
echo $NETWORK_ID
if [ $NETWORK_ID -gt 3 ]
then
  PREV_ID=$((NETWORK_ID - 1))
  wpa_cli remove_network $PREV_ID
fi
wpa_cli -i wlx5c628bcde76d set_network $NETWORK_ID ssid \"$1\"
wpa_cli -i wlx5c628bcde76d set_network $NETWORK_ID psk \"$2\"
wpa_cli -i wlx5c628bcde76d set_network $NETWORK_ID priority 1
wpa_cli -i wlx5c628bcde76d enable_network $NETWORK_ID
# always enable the default networks
wpa_cli -i wlx5c628bcde76d enable_network 0
wpa_cli -i wlx5c628bcde76d enable_network 1
wpa_cli -i wlx5c628bcde76d save_config
wpa_cli -i wlx5c628bcde76d reconfigure
wpa_cli -i wlx5c628bcde76d select_network $NETWORK_ID
