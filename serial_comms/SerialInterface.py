import logging
from datetime import datetime
from threading import Lock, Thread
from time import sleep

import serial

from .SerialProcess import SerialProcess

logger = logging.getLogger(__name__)


class SerialInterface(SerialProcess):
    def __init__(self, port, baud, capturing_lock=None, on_first_fix=None):
        super().__init__(on_first_fix)
        self.port = port
        self.isConnected = False
        self.killThread = False
        self._baud = baud
        self.serialPort = serial.Serial()
        self.rxThread = Thread(target=self.thread, daemon=True)
        self.mainThread = Thread(target=self.connect, daemon=True)
        self._lock = Lock()
        self._capturing_lock = capturing_lock or Lock()
        self._lastGpsPacketDate = None
        self.mainThread.start()
        self.rxThread.start()

    def connect(self):
        """
        Try to connect every few seconds
        """
        while not self.serialPort.is_open:
            self.open()
            sleep(2)
        self.isConnected = True
        logger.debug("Serial port %s connected", self.port)

    def open(self):
        with self._lock:
            try:
                logger.debug("Serial port try connect")
                self.serialPort = serial.Serial(port=self.port, baudrate=self._baud)
            except (serial.SerialException, OSError) as e:
                logger.warning("Failed to open serial port %s: %s", self.port, e)
                self.serialPort.close()

    def reconnect(self):
        with self._lock:
            logger.debug("Serial port reconnect")
            self.serialPort.close()

        self.connect()

    def hasGps(self):
        if self._lastGpsPacketDate is None:
            return False

        if (datetime.now() - self._lastGpsPacketDate).total_seconds() > 10:
            return False

        with self._lock:
            return self._hasGps

    def thread(self):
        logger.debug("Serial thread started")
        buff = bytearray()
        while not self.killThread:
            if self.isConnected:
                try:
                    bytesWaiting = self.serialPort.in_waiting
                    newData = False
                    while bytesWaiting > 0:
                        newData = True
                        buff += self.serialPort.read(bytesWaiting)
                        sleep(1e-3)
                        bytesWaiting = self.serialPort.in_waiting
                    if newData:
                        with self._lock:
                            items = buff.splitlines(True)
                            buff = bytearray()
                            for item in items:
                                if len(item) > 1:
                                    self.processGpsResponse(item)
                except Exception as e:
                    logger.warning("Serial thread error: %s", e)
                    self._hasGps = False
                    self.isConnected = False
                    self.reconnect()
                    buff = bytearray()

            for request in self._requests:
                try:
                    if request.identity == "GNGGA":
                        with self._capturing_lock:
                            # Do not append telemetry while the internal disk is being mounted.
                            self.saveGga(request)
                            self._lastGpsPacketDate = datetime.now()
                    elif request.identity == "GNRMC":
                        with self._capturing_lock:
                            # Do not append telemetry while the internal disk is being mounted.
                            self.saveRmc(request)
                    elif "GSV" in request.identity:
                        self.process_gsv(request)
                    elif request.identity == "GNGSA":
                        self.process_gsa(request)
                except Exception as e:
                    logger.warning("Serial process error: %s", e)
            self._requests = list()
            sleep(50e-3)
        logger.debug("Serial thread stopped")
