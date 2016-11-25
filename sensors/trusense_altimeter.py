""" D Joubert 2 November 2016 - TruSense S100 Altimeter handler."""

import serial
import serial.tools.list_ports
from time import sleep

import threading

from config import ALTIMETER_STATE, RET_OK, RET_ERROR, ALTI_STATE_STRINGS

# TODO How to deal with disconnect?

class AltiError(Exception):
    pass

class TrusenseAltimeter(object):
    """Handles serial communication with the TruSense S100 Laser Altimeter"""

    def __init__(self, logger, data_logger):
        self._ser = serial.Serial()

        self._ser.baudrate = 115200
        self._ser.timeout = 1.0
        self._ser.write_timeout = 1.0

        # SETTINGS
        # default values
        self._measurement_timeout = 2
        self._num_frames_to_avg = 2
        self._setting_strings = ['alti_measurement_timeout', 'alti_num_frames_to_avg']

        self._data_logger = data_logger

        self._logger = logger

        self.measurement = 0

        self.read_thread = None
        self._kill_pill = threading.Event()

        self.state = ALTIMETER_STATE.NOT_CONNECTED

        try:
            self._ser.port = self._get_correct_port_name()
            self._connect()
            self._configure()
        except (AltiError,serial.SerialException) as err:
            self._logger.error(err)
            self.state = ALTIMETER_STATE.ERROR

    def _get_correct_port_name(self):
        ports = list(serial.tools.list_ports.comports())
        correct_port = None
        for port in ports:
            if 'Prolific' in port[1] or 'USB-Serial Controller' in port[1]:
                correct_port = port[0]
                break

        if correct_port == None:
            raise AltiError('Could not find supported USB serial port.')

        return correct_port

    def _connect(self):
        self._ser.open()
        self._logger.info('Altimeter serial port opened.')
        self.state = ALTIMETER_STATE.CONNECTED

        # toggle dtr line, to get the altimeter in the correct state
        self._ser.dtr = 1
        self._ser.rts = 0
        sleep(0.001)
        self._ser.dtr = 0

        # Check for the okay signal
        self._check_ok('Alti did not send OK on startup')

    def get_setting(self,setting_str):
        ret_val = None
        # self._setting_strings = ['alti_measurement_timeout', 'alti_num_frames_to_avg']
        if setting_str in self._setting_strings:
            if setting_str == 'alti_measurement_timeout':
                ret_val = self._measurement_timeout
            elif setting_str == 'alti_num_frames_to_avg':
                ret_val = self._num_frames_to_avg
        return ret_val

    def set_setting(self, setting_str, val_str):
        try:
            if setting_str in self._setting_strings:
                if setting_str == 'alti_measurement_timeout':
                    self._measurement_timeout = int(val_str)
                elif setting_str == 'alti_num_frames_to_avg':
                    self._num_frames_to_avg = int(val_str)
            else:
                return RET_ERROR
        except ValueError:
            self._logger.error('Cannot convert string to setting value: %s for %s'
                               %(setting_str, val_str))
            return RET_ERROR

        # implement the changed settings
        self._configure()

        return RET_OK

    def _check_for_known_error(self, reply):
        if reply[0:2] == b'$ER':
            err_code = str(reply[4:5])
            if err_code == '00':
                self._logger.error('S100 Error 00: Invalid Command')
            elif err_code == '01':
                self._logger.error('S100 Error 01: No Target')
            elif err_code == '10':
                self._logger.error('S100 Error 10: Bad Data Checksum')
            elif err_code == '11':
                self._logger.error('S100 Error 11: Already Measuring')
            elif err_code == '12':
                self._logger.error('S100 Error 12: Invalid Parameter')
            elif err_code == '21':
                self._logger.error('S100 Error 21: User Settings Checksum')
            elif err_code == '22':
                self._logger.error('S100 Error 22: Factory Settings Checksum')
            elif err_code == '23':
                self._logger.error('S100 Error 23: BIST Test')
            elif err_code == '24':
                self._logger.error('S100 Error 24: PLL Test')
            elif err_code == '25':
                self._logger.error('S100 Error 25: Tx Power')
            elif err_code == '26':
                self._logger.error('S100 Error 26: Higher Precision')
            elif err_code == '27':
                self._logger.error('S100 Error 27: Receiver')
            elif err_code == '28':
                self._logger.error('S100 Error 28: Supply Voltage too High')
            elif err_code == '29':
                self._logger.error('S100 Error 29: Supply Voltage too Low')
            elif err_code == '30':
                self._logger.error('S100 Error 30: Temperature too High')
            elif err_code == '31':
                self._logger.error('S100 Error 31: Temperature too Low')

    def _check_ok(self, error_msg):
        reply = self._ser.readline()
        if reply != b'$OK\r\n':
            self._check_for_known_error(reply)
            raise AltiError(error_msg + ' : ' + reply.decode())

    def _write(self, command_str, command_error_str):
        message = '$'+command_str+'\r\n'
        message_bytes = message.encode()
        self._ser.write(message_bytes)
        self._check_ok(command_error_str)

    def _configure(self):
        self._write('MM,FCO', 'Error setting measurement mode')
        self._write('TM,FA', 'Error setting target mode')
        self._write('DU,M', 'Error setting distance unit')
        self._write('MT,%d' % self._measurement_timeout, 'Error setting measurement timeout')
        self._write('CA,%d' % self._num_frames_to_avg, 'Error setting continous mode frame averaging')
        self._write('FA,%d' % self._num_frames_to_avg, 'Error setting fast mode frame averaging')

    def reset(self):
        """Get the altimeter object to re-initialise, establishing comms again, etc"""
        if self.state == ALTIMETER_STATE.MEASURING:
            self.stop_measuring()

        self.__init__(self._logger, self._data_logger)

    def get_state_as_string(self):
        return ALTI_STATE_STRINGS[self.state]

    def get_measurement_as_string(self):
        return str(self.measurement)

    def disconnect(self):
        assert self._ser.is_open, 'Trying to close already closed alti serial port'

        try:
            self._ser.close()
        except serial.SerialException as ex:
            self._logger.error('Error closing altimeter port : %s' % str(ex.args))
            self.state = ALTIMETER_STATE.ERROR
            return RET_ERROR
        self._logger.info('Comms with altimeter have been closed')
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        return RET_OK

    def _create_read_worker(self):
        def worker(stop_event, temp):
            while not stop_event.wait(1):
                msg = self._ser.readline()
                if len(msg) > 0:
                    dist_str = msg[4:].split(b',')[0]
                    self.measurement = float(dist_str)
                    self._data_logger.log("Alti measure: %s" %dist_str)
                else:
                    self._logger.error('Empty message read from alti port, indicates a timeout')

        return worker

    def start_measuring(self):
        assert self._ser.is_open
        try:
            self._write('GO', 'Error starting measuring mode')
            # TODO Are there exceptions when starting a thread?
            self._kill_pill = threading.Event()
            self.read_thread = threading.Thread(target=self._create_read_worker(),
                                                args=(self._kill_pill, 1))
            self.read_thread.start()
            self.state = ALTIMETER_STATE.MEASURING
            return RET_OK
        except Exception as err:
            self._logger.error(err)
            return RET_ERROR

    def stop_measuring(self):
        assert self._ser.is_open
        assert self.state == ALTIMETER_STATE.MEASURING
        try:
            self._kill_pill.set()
            self.read_thread.join()
            self._write('ST', 'Error stopping measuring mode');
            self.state = ALTIMETER_STATE.CONNECTED
            return RET_OK
        except Exception as e:
            self._logger.error(e);
            return RET_ERROR
