#!/bin/bash
echo tricap_launcher_test > /home/radxa/tricap/logs/launch_test.txt
/usr/bin/python3 /home/radxa/tricap/tricap_launch_tester.py
# export PATH=/home/radxa/hello/helloenv/bin
# /home/radxa/hello/helloenv/bin/python /home/radxa/hello/hello.py
/usr/bin/python3 /home/radxa/tricap/tricap.py
