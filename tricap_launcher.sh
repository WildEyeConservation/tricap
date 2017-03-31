#!/bin/bash
echo tricap_launcher_test > /home/rpi3/Projects/tricap/tricap/logs/launch_test.txt
/usr/bin/python3 /home/rpi3/Projects/tricap/tricap/tricap_launch_tester.py
# export PATH=/home/rpi3/Projects/hello/helloenv/bin
# /home/rpi3/Projects/hello/helloenv/bin/python /home/rpi3/Projects/hello/hello.py
/usr/bin/python3 /home/rpi3/Projects/tricap/tricap/tricap.py
