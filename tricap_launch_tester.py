#!/usr/bin/env python

from datetime import datetime

with open('/home/radxa/tricap/logs/python_launch_test.txt', 'w') as tfile:
    tfile.write(str(datetime.now())+'\n')
    tfile.write('Launch test\n')


