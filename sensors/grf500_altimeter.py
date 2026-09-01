"""LightWare GRF-500 laser rangefinder used as the SkySeeker altimeter.

The GRF-500 is a native USB-CDC device (``04d8:ed57``) speaking LightWare's
LWNX binary protocol. We poll command 44 (Distance data) at the sensor's
update rate, retain both first and last returns, and publish the last-return
distance as the live altitude.
"""
# coding=utf-8

import logging
import struct
import threading
from time import sleep

import serial
import serial.tools.list_ports

from config import ALTIMETER_STATE
from support.basic import Subject


# --- LWNX protocol constants ------------------------------------------------
# GRF-500 enumerates as a Microchip USB-CDC device.
GRF500_USB_IDS = {(0x04D8, 0xED57)}          # (idVendor, idProduct)

_CMD_PRODUCT_NAME = 0
_CMD_DISTANCE_OUTPUT = 27                     # bitmask: which fields cmd44 returns
_CMD_STREAM = 30                              # 0=off, 5=stream cmd44
_CMD_DISTANCE_DATA = 44                       # the measurement record
_CMD_UPDATE_RATE = 74                         # Hz (0.1 Hz units: 50 -> 5.0 Hz)
_CMD_LASER_FIRING = 50                        # 0=off, 1=on -- fire only during capture

# cmd27 bits 0/2 (first raw/strength) + bits 3/5 (last raw/strength).
# => cmd44 payload is exactly four int32s in bit order:
# [first_distance, first_strength_dB, last_distance, last_strength_dB].
_DISTANCE_OUTPUT_MASK = 0b00101101

# GRF-500 "Distance data" (cmd44) reports the raw distance in units of 0.1 m
# per count (decimetres) -- i.e. the "10 cm resolution" of the spec.  Verified
# on bench against known targets: min-range floor reads raw=2 (=0.2 m) and a
# ~2 m target reads raw=22 (=2.2 m).  (The product guide's "in cm" label for
# cmd44 is incorrect.)
_DIST_TO_M = 0.1
_LOST_SIGNAL = -10                            # cmd44 sentinel: no valid return


class GrfError(Exception):
    pass


class Grf500Altimeter(Subject):
    """Handles LWNX communication with the LightWare GRF-500 laser rangefinder."""

    _logger = logging.getLogger(__name__)

    def __init__(self, settings, supported_devices=GRF500_USB_IDS):
        super().__init__()

        # The [Altimeter] section of the config file. No options are consumed
        # yet; the retired Trusense driver's keys were removed from it.
        self._settings = settings

        self.state = ALTIMETER_STATE.NOT_CONNECTED
        self._kill_pill = None
        self._read_thread = None
        self._measurement = None
        self._io_lock = threading.Lock()

        # Bring the alti in line with the other monitors (observer surface).
        self.type_id = 'Altitude'
        self.value = 0
        self.unit = 'm'
        self.first_return = None
        self.last_return = None
        self.first_strength = 0
        self.last_strength = 0
        # Backwards-compatible aliases represent the return shown live.
        self.strength = 0
        self.error = ""
        self.error_start = False
        self.alti_code = 2 * [""]

        self._ser = None
        self._ser = serial.Serial(port=self._get_correct_port_name(supported_devices),
                                  baudrate=115200, timeout=0.2, write_timeout=1.0)
        self._logger.info('GRF-500 serial port opened.')
        self.state = ALTIMETER_STATE.CONNECTED
        self._configure()

    # --- properties ---------------------------------------------------------
    @property
    def measurement(self):
        return self._measurement

    # --- port discovery -----------------------------------------------------
    @staticmethod
    def _get_correct_port_name(supported_devices):
        for port in serial.tools.list_ports.comports():
            if (port.vid, port.pid) in supported_devices:
                return port.device
        raise GrfError('Could not find GRF-500 USB serial port.')

    # --- LWNX framing -------------------------------------------------------
    @staticmethod
    def _crc16(data):
        crc = 0
        for byte in data:
            code = (crc >> 8) & 0xFFFF
            code ^= byte; code &= 0xFFFF
            code ^= (code >> 4); code &= 0xFFFF
            crc = (crc << 8) & 0xFFFF
            crc ^= code; crc &= 0xFFFF
            code = (code << 5) & 0xFFFF
            crc ^= code; crc &= 0xFFFF
            code = (code << 7) & 0xFFFF
            crc ^= code; crc &= 0xFFFF
        return crc & 0xFFFF

    def _build(self, cmd_id, write=False, data=b''):
        payload = bytes([cmd_id]) + data
        flags = (len(payload) << 6) | (1 if write else 0)
        hdr = bytes([0xAA, flags & 0xFF, (flags >> 8) & 0xFF]) + payload
        crc = self._crc16(hdr)
        return hdr + bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    def _txn(self, cmd_id, write=False, data=b'', wait=0.6):
        """Send a request/command and return (payload_without_cmd_id, crc_ok)."""
        with self._io_lock:
            self._ser.reset_input_buffer()
            self._ser.write(self._build(cmd_id, write, data))
            self._ser.flush()
            buf = bytearray()
            deadline = wait
            while deadline > 0:
                chunk = self._ser.read(256)
                if not chunk:
                    deadline -= self._ser.timeout or 0.2
                    continue
                buf += chunk
                for pkt_cmd, pkt_payload, ok in self._extract(buf):
                    if pkt_cmd == cmd_id:
                        return pkt_payload, ok
            return None, False

    @classmethod
    def _extract(cls, buf):
        out = []
        while True:
            idx = buf.find(b'\xAA')
            if idx < 0:
                buf.clear(); break
            if idx > 0:
                del buf[:idx]
            if len(buf) < 3:
                break
            flags = buf[1] | (buf[2] << 8)
            plen = flags >> 6
            if plen < 1 or plen > 1023:
                del buf[0]; continue
            total = 3 + plen + 2
            if len(buf) < total:
                break
            pkt = bytes(buf[:total])
            ok = (cls._crc16(pkt[:-2]) == (pkt[-2] | (pkt[-1] << 8)))
            out.append((pkt[3], pkt[4:3 + plen], ok))
            del buf[:total]
        return out

    # --- configuration ------------------------------------------------------
    def _configure(self):
        name, ok = self._txn(_CMD_PRODUCT_NAME)
        if ok and name:
            product = name.split(b'\x00')[0].decode('ascii', 'replace')
            self._logger.info('GRF-500 identified as "%s".', product)
        # Deterministic distance-data layout:
        # [first distance, first strength, last distance, last strength].
        self._txn(_CMD_DISTANCE_OUTPUT, write=True,
                  data=struct.pack('<I', _DISTANCE_OUTPUT_MASK))
        # Make sure any leftover streaming is off; we poll on demand.
        self._txn(_CMD_STREAM, write=True, data=struct.pack('<I', 0))
        # Laser only fires while actively measuring (i.e. during capture).
        self._set_laser(False)

    def _set_laser(self, on):
        """Enable/disable laser firing (cmd 50) so it fires only during capture."""
        try:
            self._txn(_CMD_LASER_FIRING, write=True, data=struct.pack('<B', 1 if on else 0))
        except Exception:
            pass

    # --- error surface -------------------------------------------------------
    def set_error(self, error_code=""):
        self.error = error_code

    def get_error(self):
        return self.error

    def get_error_start(self):
        return self.error_start

    def set_error_start(self, error_code):
        self.error_start = error_code

    def get_state_as_string(self):
        return self.state.name

    # --- lifecycle ----------------------------------------------------------
    def disconnect(self):
        if self._ser and self._ser.is_open:
            try:
                self._set_laser(False)
                self._txn(_CMD_STREAM, write=True, data=struct.pack('<I', 0))
            except Exception:
                pass
            self._ser.close()
            self._logger.info('Comms with GRF-500 have been closed')
        self.state = ALTIMETER_STATE.NOT_CONNECTED

    def _update_rate_hz(self):
        payload, ok = self._txn(_CMD_UPDATE_RATE)
        if ok and payload and len(payload) >= 4:
            tenths = int.from_bytes(payload[:4], 'little', signed=True)
            if tenths > 0:
                return tenths / 10.0
        return 5.0

    @staticmethod
    def _distance_metres(raw):
        if raw == _LOST_SIGNAL or raw < 0:
            return None
        return round(raw * _DIST_TO_M, 1)

    def _read(self, stop_event):
        period = 1.0 / max(self._update_rate_hz(), 1.0)
        consecutive_fails = 0
        while not stop_event.is_set():
            payload, ok = self._txn(_CMD_DISTANCE_DATA)
            if ok and payload and len(payload) >= 16:
                consecutive_fails = 0
                (first_raw, self.first_strength,
                 last_raw, self.last_strength) = struct.unpack_from('<iiii', payload)
                self.first_return = self._distance_metres(first_raw)
                self.last_return = self._distance_metres(last_raw)

                # The dashboard and legacy altitude consumers intentionally use
                # the last reflection, while observers can log both returns.
                self._measurement = self.last_return
                self.value = self.last_return
                self.strength = self.last_strength
                if self.last_return is None:
                    self.set_error('No target')
                else:
                    self.set_error("")
                self.notify()
            else:
                consecutive_fails += 1
            if consecutive_fails >= 5:
                self.state = ALTIMETER_STATE.ERROR
                self._logger.error('GRF-500 Error: too many read failures, comms lost.')
                raise GrfError('Communications with GRF-500 lost (5 consecutive failures).')
            stop_event.wait(period)
        self.state = ALTIMETER_STATE.CONNECTED

    def start_measuring(self):
        """Start the measuring thread."""
        if self._read_thread is not None and self._read_thread.is_alive():
            return
        self._set_laser(True)
        self._kill_pill = threading.Event()
        self._read_thread = threading.Thread(target=self._read,
                                              args=(self._kill_pill,), daemon=True)
        self._read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING
        self._logger.debug("GRF-500 - started measuring.")

    def stop_measuring(self):
        if self._read_thread and self._read_thread.is_alive():
            self._kill_pill.set()
            self._read_thread.join()
            self._logger.debug("GRF-500 - stopped measuring.")
        self._set_laser(False)
        self.state = ALTIMETER_STATE.CONNECTED
