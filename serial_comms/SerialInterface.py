import serial
from time import sleep
from threading import Thread, Lock
import base64
import serial_comms.out.tricap_pb2 as pb
import logging, subprocess

from .SerialProcess import SerialProcess

GET_STATUS = 1

class SerialInterface(SerialProcess):
  _logger = logging.getLogger(__name__)

  def __init__(self, port):
    super().__init__()
    self.port = port
    self.isConnected = False
    self.killThread = False
    self.serialPort = serial.Serial()
    self.rxThread = Thread(target=self.thread, daemon=True)
    self.mainThread = Thread(target=self.connect, daemon=True)
    self._lock = Lock()
    self.mainThread.start()
    self.rxThread.start()

  def connect(self):
    """
    Try to connect every few seconds
    """
    while self.serialPort.is_open == False:
      self.open()
      sleep(1)
    self.isConnected = True
    self._logger.debug('Serial port {} connected'.format(self.port))

  def open(self):
    with self._lock:
      try:
        self.serialPort = serial.Serial(port=self.port)
        sleep(50e-3)
        bytesWaiting = self.serialPort.inWaiting()
      except:
        self.serialPort.close()
        subprocess.run(['rfcomm', 'release', '0'])
        # self._logger.debug('Failed to open port')

  def close(self):
    """
    Stop thread and close serial port 
    """
    with self._lock:
      self.isConnected = False
      self.killThread = True
      self.serialPort.close()
      subprocess.run(['rfcomm', 'release', '0'])

  def reconnect(self):
    with self._lock:
      self.serialPort.close()
      subprocess.run(['rfcomm', 'release', '0'])
    self.connect()

  def write(self, buff):
    with self._lock:
      self._logger.debug('tx {} {}'.format(buff, len(buff)))
      try:
        self.serialPort.write(base64.b64encode(buff))
        self.serialPort.write(base64.b64encode(b'~!'))
      except:
        self._logger.debug('tx failed')

  def thread(self):
    self._logger.debug('Serial thread started')
    buff = bytearray()
    while self.killThread == False:
      if self.isConnected:
        try:
          newData = False
          bytesWaiting = self.serialPort.inWaiting()
          while bytesWaiting > 0:
            newData = True
            buff += self.serialPort.read(bytesWaiting)
            self._logger.debug('rx {} {}'.format(buff, len(buff)))
            sleep(1e-3)
            bytesWaiting = self.serialPort.inWaiting()
          if newData:
            with self._lock:
                if (self.processResponse(buff)):
                  # clear buffer
                  buff = bytearray()
        except:
          self._logger.debug('Serial thread error')
          self.reconnect()
          buff = bytearray()

      for request in self._requests:
        self._logger.debug('Process {}'.format(request.msgType))
        msg = bytearray()
        if request.msgType == pb.Message.MessageType.IP_ADDRESS:
          msg = self.buildIpAddress()
        elif request.msgType == pb.Message.MessageType.WIFI_SETUP:
          self.setupWifi(request.wifi.ssid, request.wifi.password)
          msg = self.buildWifiReply()
        if len(msg) > 0:
          self.write(msg)
      self._requests = list()
      sleep(50e-3)
    self._logger.debug('Serial thread stopped')
