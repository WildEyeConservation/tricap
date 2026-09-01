import serial
from time import sleep
from threading import Thread, Lock
import logging
from datetime import datetime
from .SerialProcess import SerialProcess

class SerialInterface(SerialProcess):
  _logger = logging.getLogger(__name__)

  def __init__(self, port, baud, capturing_lock=None, cam_manager=None):
    super().__init__(cam_manager)
    self.port = port
    self.isConnected = False
    self.killThread = False
    self._baud = baud
    self.serialPort = serial.Serial()
    self.rxThread = Thread(target=self.thread, daemon=True)
    self.mainThread = Thread(target=self.connect, daemon=True)
    self._lock = Lock()
    self._capturing_lock = capturing_lock
    self._lastGpsPacketDate = None
    self.mainThread.start()
    self.rxThread.start()

  def connect(self):
    """
    Try to connect every few seconds
    """
    while self.serialPort.is_open == False:
      self.open()
      sleep(2)
    self.isConnected = True
    self._logger.debug('Serial port {} connected'.format(self.port))

  def open(self):
    with self._lock:
      try:
        self._logger.debug('Serial port try connect')
        self.serialPort = serial.Serial(port=self.port, baudrate=self._baud)
        sleep(10e-3)
        bytesWaiting = self.serialPort.inWaiting()
      except:
        self.serialPort.close()
        # self._logger.debug('Failed to open port')

  def reconnect(self):
    with self._lock:
      self._logger.debug('Serial port reconnect')
      self.serialPort.close()

    self.connect()

  def hasGps(self):
    if (self._lastGpsPacketDate == None):
      return False

    if ((datetime.now() - self._lastGpsPacketDate).total_seconds() > 10):
      return False

    with self._lock:
      return self._hasGps

  def thread(self):
    self._logger.debug('Serial thread started')
    buff = bytearray()
    while self.killThread == False:
      if self.isConnected:
        try:
          bytesWaiting = self.serialPort.inWaiting()
          newData = False
          while bytesWaiting > 0:
            newData = True
            buff += self.serialPort.read(bytesWaiting)
            sleep(1e-3)
            bytesWaiting = self.serialPort.inWaiting()
          if newData:
            with self._lock:
              items = buff.splitlines(True)
              buff = bytearray()
              for item in items:
                if len(item) > 1:
                  self.processGpsResponse(item)
        except Exception as e:
          self._logger.debug(f"Serial thread error {e}")
          self._hasGps = False
          self.reconnect()
          buff = bytearray()

      for request in self._requests:
        try:
          if request.identity == 'GNGGA':
#            self._logger.debug('Process {}'.format(request.sentence_type))
            with self._capturing_lock:
              # do not open file while capture and copy has the file open 
              self.saveGga(request)
              self._lastGpsPacketDate = datetime.now()
          elif request.identity == 'GNRMC':
#            self._logger.debug('Process {}'.format(request.sentence_type))
            with self._capturing_lock:
              # do not open file while capture and copy has the file open 
              self.saveRmc(request)
          elif 'GSV' in request.identity:
            self.process_gsv(request)
          elif request.identity == 'GNGSA':
            self.process_gsa(request)
        except Exception as e:
            print(f"Serial process error {e}")
      self._requests = list()
      sleep(50e-3)
    self._logger.debug('Serial thread stopped')
