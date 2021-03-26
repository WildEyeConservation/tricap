from time import sleep
from datetime import datetime
from serial_comms.SerialInterface import SerialInterface

ser = SerialInterface('/dev/rfcomm0')

while True:
  sleep(1)

  # start = datetime.now()
  # im = ser.buildIpAddress()
  # ser.write(im)
  # end = datetime.now()
  # print(end)
  # print((end-start).total_seconds())
  # print('write done')
  # sleep(1)
  # break