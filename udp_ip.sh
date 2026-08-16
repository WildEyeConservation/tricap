#!/bin/bash

while true
do
    # Get the default gateway IP address
    gateway_ip=$(ip route | awk '/default/ {print $3}')

    echo $gateway_ip

    # Get your own IP address
    ip_address=$(hostname -I | awk '{print $1}')

    echo $ip_address

    # Send the IP address via UDP to the default gateway
    echo -n $ip_address | nc -u $gateway_ip 12345 &

    # Wait for 5 seconds before sending the next IP address
    echo "Sleep"
    sleep 5
done
