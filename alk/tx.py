import serial, time

ser = serial.Serial('/dev/rfcomm0')
for i in range(5):
  print('tx', 'helloalk'.encode())
  ser.write('helloalk'.encode())
  time.sleep(4)

ser.close()
