#!/bin/bash
echo tricap_launcher_test > /home/pi/tricap/logs/launch_test.txt
/usr/bin/python3 /home/pi/tricap/tricap_launch_tester.py
# export PATH=/home/pi/hello/helloenv/bin
# /home/pi/hello/helloenv/bin/python /home/pi/hello/hello.py
/usr/bin/python3 /home/pi/tricap/tricap.py
