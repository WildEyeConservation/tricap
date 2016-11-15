# D Joubert 2 November 2016

import serial
import serial.tools.list_ports

import threading

import pdb

from config import ALTIMETER_STATE

# TODO How to deal with disconnect?

class TrusenseAltimeter(object):
    def __init__(self):
        self._ser = serial.Serial()

        self._ser.port=self._get_correct_port_name()
        self._ser.baudrate = 115200
        self._ser.timeout = 1.0
        self._ser.write_timeout = 1.0

        self.measurement = 0

        self.read_thread = None
        self._kill_pill = threading.Event()

        self.state = ALTIMETER_STATE.NOT_CONNECTED

        if self._ser.port == None:
            self.state = ALTIMETER_STATE.ERROR

        if self.state != ALTIMETER_STATE.ERROR:
            self.connect()

        if self.state != ALTIMETER_STATE.ERROR:
            self.configure()

    def reset(self):
        if self.state == ALTIMETER_STATE.MEASURING:
            self.stop_measuring()
            
        self.__init__()

    # def __del__(self):
    #     if self.read_thread is not None:
    #         if self.read_thread.is_alive() is True:
    #             self._kill_pill.set()
    #             self.read_thread.join()
    #
    #     self.disconnect()

    def _get_correct_port_name(self):
        ports = list(serial.tools.list_ports.comports())
        correct_port = None
        for p in ports:
            if 'Prolific' in p[1] or 'USB-Serial Controller' in p[1]:
                correct_port = p[0]
                break

        if correct_port == None:
            self.state = ALTIMETER_STATE.ERROR

        print(correct_port)

        return correct_port

    def connect(self):
        self._ser.open()
        if self._ser.is_open == True:
            print('Comms with serial port of the altimeter have been opened')
            self.state = ALTIMETER_STATE.CONNECTED
        else:
            print('Comms with serial port of the altimeter are not open - ERROR.')
            self.state = ALTIMETER_STATE.ERROR
            return -1

        # toggle dtr and rts lines, to get the altimeter in the correct state
        self._ser.dtr = 1
        self._ser.rts = 0
        self._ser.dtr = 0

        # Check for the okay signal
        temp = self._ser.readline()
        if temp != b'$OK\r\n':
            print('Error with opening connection.')
            self.state = ALTIMETER_STATE.ERROR
            return -1

        return 0

    def _check_ok(self, error_msg):
        reply = self._ser.readline()
        if reply != b'$OK\r\n':
            print(error_msg)
            print(reply)
            self.state = ALTIMETER_STATE.ERROR
            return -1
        else:
            return 0

    def configure(self):
        # set to fast continuous
        self._ser.write('$MM,FCO\r\n'.encode())
        if self._check_ok('Error setting measurment mode') != 0:
            return -1

        # set target to farthest
        self._ser.write('$TM,FA\r\n'.encode())
        if self._check_ok('Error setting target mode') != 0:
            return -1

        # set to meters
        self._ser.write('$DU,M\r\n'.encode())
        if self._check_ok('Error setting distance unit') != 0:
            return -1

        # set to measurement timeout
        self._ser.write('$MT,2\r\n'.encode())
        if self._check_ok('Error setting measurement timeout') != 0:
            return -1

        # set continous mode average
        self._ser.write('$CA,2\r\n'.encode())
        if self._check_ok('Error setting continous mode frame averaging') != 0:
            return -1

        # set fast mode averaging
        self._ser.write('$FA,2\r\n'.encode())
        if self._check_ok('Error setting fast mode frame averaging') != 0:
            return -1

        # TODO Proper logging instead of printing
        # TODO There are a bunch of error messages we are not taking advantage of

        return 0

    def get_state_as_string(self):
        if self.state == ALTIMETER_STATE.NOT_CONNECTED:
            return "Not Connected"
        elif self.state == ALTIMETER_STATE.CONNECTED:
            return "Connected"
        elif self.state == ALTIMETER_STATE.MEASURING:
            return "Measuring"
        else:
            return "Error"

    def get_measurement_as_string(self):
        return str(self.measurement) + ' m'

    def disconnect(self):
        if self._ser.is_open == False:
            print('Comms are already closed')
            self.state = ALTIMETER_STATE.NOT_CONNECTED
            return -1

        self._ser.close()
        if self._ser.is_open == False:
            print('Comms with altimeter has been closed')
            self.state = ALTIMETER_STATE.NOT_CONNECTED
            return 0
        else:
            print('Commns with altimeter are still open - ERROR.')
            self.state = ALTIMETER_STATE.ERROR
            return -1

    def _create_read_func(self):
        def worker(stop_event, temp):
            while not stop_event.wait(1):
                msg = self._ser.readline()
                dist_str = msg[4:].split(b',')[0]
                self.measurement = float(dist_str)

        return worker

    def start_measuring(self):
        if self._ser.is_open is False:
            return -1

        self._ser.write('$GO\r\n'.encode())
        if self._check_ok('Error starting measuring mode') != 0:
            return -1
        self._kill_pill = threading.Event()
        self.read_thread = threading.Thread(target=self._create_read_func(),
                                  args=(self._kill_pill, 1))
        self.read_thread.start()
        self.state = ALTIMETER_STATE.MEASURING

    def stop_measuring(self):
        if self._ser.is_open is False:
            return -1

        if self.state == ALTIMETER_STATE.MEASURING:
            self._kill_pill.set()
            self.read_thread.join()

            self._ser.write('$ST\r\n'.encode())
            if self._check_ok('Error stopping measuring mode') != 0:
                return -1

            self.state = ALTIMETER_STATE.CONNECTED
