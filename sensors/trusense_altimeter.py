""" D Joubert 2 November 2016 - TruSense S100 Altimeter handler."""

import serial
import serial.tools.list_ports

import threading

import pdb

from config import ALTIMETER_STATE, RET_OK, RET_ERROR, ALTI_STATE_STRINGS

# TODO How to deal with disconnect?

class TrusenseAltimeter(object):
    """Handles serial communication with the TruSense S100 Laser Altimeter"""

    def __init__(self, logger, data_logger):
        self._ser = serial.Serial()

        self._ser.port = self._get_correct_port_name()
        self._ser.baudrate = 115200
        self._ser.timeout = 1.0
        self._ser.write_timeout = 1.0

        self._data_logger = data_logger

        self._logger = logger

        self.measurement = 0

        self.read_thread = None
        self._kill_pill = threading.Event()

        self.state = ALTIMETER_STATE.NOT_CONNECTED

        if self._ser.port == None:
            self._logger.error('Not able to set port correctly')
            self.state = ALTIMETER_STATE.ERROR
        else:
            self._connect()
            if self.state == ALTIMETER_STATE.ERROR:
                self._logger.error('Unable to connect to the altimeter.')
            else:
                self._configure()
                if self.state == ALTIMETER_STATE.ERROR:
                    self._logger.error('Unable to configure the altimeter')

    def _get_correct_port_name(self):
        ports = list(serial.tools.list_ports.comports())
        correct_port = None
        for port in ports:
            if 'Prolific' in port[1] or 'USB-Serial Controller' in port[1]:
                correct_port = port[0]
                break

        if correct_port == None:
            self.state = ALTIMETER_STATE.ERROR

        return correct_port

    def _connect(self):
        try:
            self._ser.open()
        except serial.SerialException as ex:
            self._logger.error('Exception opening altimeter serial port %s' % str(ex.args))

        if self._ser.is_open == True:
            self._logger.info('Altimeter serial port comms are open.')
            self.state = ALTIMETER_STATE.CONNECTED
        else:
            self._logger.error('Error opening serial port comms.')
            self.state = ALTIMETER_STATE.ERROR
            return RET_ERROR

        # toggle dtr and rts lines, to get the altimeter in the correct state
        self._ser.dtr = 1
        self._ser.rts = 0
        self._ser.dtr = 0

        # Check for the okay signal
        temp = self._ser.readline()
        if temp != b'$OK\r\n':
            self._logger.error('Unable to get OK string from altimeter serial port')
            self.state = ALTIMETER_STATE.ERROR
            return RET_ERROR

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
            self._logger.error(error_msg + ' : ' + reply.decode())
            self._check_for_known_error(reply)
            self.state = ALTIMETER_STATE.ERROR
            return RET_ERROR
        else:
            return RET_OK

    def _write(self, command_str, command_error_str):
        message = '$'+command_str+'\r\n'
        message_bytes = message.encode()
        try:
            self._ser.write(message_bytes)
        except serial.SerialTimeoutException as ex:
            self._logger.error('Timeout writing %s on alti port : %s' % (message, str(ex.args)))
            return RET_ERROR
        except serial.SerialException as ex:
            self._logger.error('Error writing %s on alti port : %s' % (message, str(ex.args)))
            return RET_ERROR

        if self._check_ok(command_error_str) != 0:
            return RET_ERROR

        return RET_OK

    def _configure(self):
        # set to fast continuous
        # self._ser.write('$MM,FCO\r\n'.encode())
        # if self._check_ok('Error setting measurment mode') != 0:
        #     return -1

        if self._write('MM,FCO', 'Error setting measurement mode') != RET_OK:
            return RET_ERROR

        # set target to farthest
        if self._write('TM,FA', 'Error setting target mode') != RET_OK:
            return RET_ERROR

        # set to meters
        if self._write('DU,M', 'Error setting distance unit') != RET_OK:
            return RET_ERROR

        # TODO Set these values from the init config file

        # set to measurement timeout
        if self._write('MT,2', 'Error setting measurement timeout') != RET_OK:
            return RET_ERROR

        # set continous mode average
        if self._write('CA,2', 'Error setting continous mode frame averaging') != RET_OK:
            return RET_ERROR

        # set fast mode averaging
        if self._write('FA,2', 'Error setting fast mode frame averaging') != RET_OK:
            return RET_ERROR

        return 0

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
        if self._ser.is_open == False:
            self._logger.warning('Trying to close already closed alti serial port')
            self.state = ALTIMETER_STATE.NOT_CONNECTED
            return RET_ERROR

        try:
            self._ser.close()
        except serial.SerialException as ex:
            self._logger.error('Error closing altimeter port : %s' % str(ex.args))
            return RET_ERROR

        if self._ser.is_open != False:
            self._logger.error('Commns with altimeter are still open after trying to close.')
            self.state = ALTIMETER_STATE.ERROR
            return RET_ERROR

        self._logger.info('Comms with altimeter have been closed')
        self.state = ALTIMETER_STATE.NOT_CONNECTED
        return RET_OK

    def _create_read_worker(self):
        def worker(stop_event, temp):
            while not stop_event.wait(1):
                try:
                    msg = self._ser.readline()
                except serial.SerialException as ex:
                    self._logger.error('Error reading from altimeter port : %s' % str(ex.args))
                else:
                    if len(msg) > 0:
                        dist_str = msg[4:].split(b',')[0]
                        self.measurement = float(dist_str)
                        self._data_logger.log("Alti measure: %s" %dist_str)
                    else:
                        self._logger.error('Empty message read from alti port, indicates a timeout')

        return worker

    def start_measuring(self):
        if self._ser.is_open is False:
            return -1

        if self._write('GO', 'Error starting measuring mode') != RET_OK:
            return RET_ERROR

        # TODO Are there exceptions when starting a thread?
        self._kill_pill = threading.Event()
        self.read_thread = threading.Thread(target=self._create_read_worker(),
                                            args=(self._kill_pill, 1))
        self.read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING

    def stop_measuring(self):
        if self._ser.is_open is False:
            return RET_ERROR

        if self.state == ALTIMETER_STATE.MEASURING:
            self._kill_pill.set()
            self.read_thread.join()

            if self._write('ST', 'Error stopping measuring mode') != RET_OK:
                return RET_ERROR

            self.state = ALTIMETER_STATE.CONNECTED

        return RET_OK
