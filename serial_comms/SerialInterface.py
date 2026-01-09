import serial
from time import sleep
from threading import Thread, Lock
import base64
import serial_comms.out.tricap_pb2 as pb
import logging, subprocess
from datetime import datetime, timedelta
import re
from .SerialProcess import SerialProcess
import ntplib
from .ubloxAgps import UBXAgps

GET_STATUS = 1

class SerialInterface(SerialProcess):
  _logger = logging.getLogger(__name__)

  def __init__(self, port, baud, require_release = False, process_protobuf = False, capturing_lock = None, cam_manager = None):
    super().__init__(cam_manager)
    self.port = port
    self.isConnected = False
    self.killThread = False
    self._process_protobuf = process_protobuf
    self._require_release = require_release
    self._baud = baud
    if require_release:
      # rfcomm for bluetooth is not always present and require release
      subprocess.run(['rfcomm', 'release', '0'])
    self.serialPort = serial.Serial()
    self.rxThread = Thread(target=self.thread, daemon=True)
    self.mainThread = Thread(target=self.connect, daemon=True)
    self._lock = Lock()
    self._capturing_lock = capturing_lock
    self._lastGpsPacketDate = None
    self._AGPS_sent = False
    self._cam_manager = cam_manager
    self._AGPS_max_retries = 3
    self._ubxAgps = UBXAgps(self.serialPort,self._requests)
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
        if self._require_release:
          subprocess.run(['rfcomm', 'release', '0'])
        # self._logger.debug('Failed to open port')

  def reconnect(self):
    with self._lock:
      self._logger.debug('Serial port reconnect')
      self.serialPort.close()
      if self._require_release:
        subprocess.run(['rfcomm', 'release', '0'])

    self.connect()

  def hasGps(self):
    if (self._lastGpsPacketDate == None):
      return False

    if ((datetime.now() - self._lastGpsPacketDate).total_seconds() > 10):
      return False

    with self._lock:
      return self._hasGps

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
          if self._process_protobuf:
            # bluetooth
            bytesWaiting = self.serialPort.inWaiting()
            while bytesWaiting > 0:
              newData = True
              buff += self.serialPort.read(bytesWaiting)
              sleep(1e-3)
              bytesWaiting = self.serialPort.inWaiting()
            if newData:
              # self._logger.debug('rx {} {}'.format(buff, len(buff)))
              with self._lock:
                if self._process_protobuf:
                  if self.processProtobufResponse(buff):
                    # clear buffer
                    buff = bytearray()
          else:
            # gps
            bytesWaiting = self.serialPort.inWaiting()
            newData = False
            while bytesWaiting > 0:
              # self._logger.debug('GPS serial bytes in waiting {}'.format(bytesWaiting))
              newData = True
              buff += self.serialPort.read(bytesWaiting)
              sleep(1e-3)
              bytesWaiting = self.serialPort.inWaiting()
            if newData:
              # self._logger.debug('rx {} {}'.format(buff, len(buff)))
              with self._lock:
                  items = buff.splitlines(True) 
                  # clear buffer
                  buff = bytearray()
                  for item in items:
                    if(len(item) > 1):
                      self.processGpsResponse(item)   
        except Exception as e:
          self._logger.debug(f"Serial thread error {e}")
          self._hasGps = False
          self.reconnect()
          buff = bytearray()

      for request in self._requests:
        try:
          msg = bytearray()
          if self._process_protobuf:
            self._logger.debug('Process {}'.format(request.msgType))
            if request.msgType == pb.Message.MessageType.IP_ADDRESS:
              msg = self.buildIpAddress()
            elif request.msgType == pb.Message.MessageType.WIFI_SETUP:
              self.setupWifi(request.wifi.ssid, request.wifi.password)
              msg = self.buildWifiReply()
          elif request.identity == 'GNGGA':
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
          if len(msg) > 0:
            self.write(msg)
        except Exception as e:
            print(f"Serial process error {e}")
      self._requests = list()
      # Send AGPS data to the GPS if we have'nt yet and we have an internet connection
      if(self._AGPS_max_retries > 0 and self.isConnected and (not self._lastGpsPacketDate == None) and (not self.hasGps()) and (not self._AGPS_sent) and self._ubxAgps.has_internet()):
        try:
          if(self._cam_manager):
            # To be able to connect to the AGPS server we need to have the system time set correctly. So query an NTP server and set the time
            ntp_client = ntplib.NTPClient()
            ntp_response = ntp_client.request('pool.ntp.org')
            time_to_set = datetime.now() + timedelta(seconds=ntp_response.offset) 
            self._cam_manager.sync_time(time_to_set.strftime('%Y-%m-%d %H:%M:%S.%f'))
          else:
            self._logger.warning("No cam manager, cannot sync time before AGPS download. Connection to AGPS server may fail.")
          self._ubxAgps.download_and_send_agps(self.serialPort)
          self._AGPS_sent = True
        except Exception as e:
          print(f"Failed to upload AGPS data: {e}")
          self._AGPS_max_retries -= 1
      sleep(50e-3)
    self._logger.debug('Serial thread stopped')
