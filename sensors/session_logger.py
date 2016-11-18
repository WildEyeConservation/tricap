import logging
import time
import os
import shutil

from random import randint

from config import SESSION_ROOT_DIR, CONFIG_FP

""" D Joubert - Innoventix Consulting - 18 November 2016 - session_logger.py
    Logger for data, to be used for importing the data into the larger system """

class SessionLogger():
    """ The session logger is responsible for creating a session folder, a session data file
        (which will most likely only contain the data from the altimeter), copying the config file
        and creating any additional data structures. The log file is converted in the end to XML
        format, so that whatever program in whatever language can use it. """

    def __init__(self, description = 'Default Description', root_folder = SESSION_ROOT_DIR):

        self._root_folder = root_folder

        # TODO This was implemented during the testing bug thing gosh darn
        # session_name = 'session_logger%s%d' % (time.strftime("%H%M%S"), randint(1, 1000))
        session_name = 'session_logger'
        self._logger = logging.getLogger(session_name)
        self._logger.setLevel(logging.DEBUG)

        self._session_count = None
        self._log_fp = None
        self._session_folder = None
        self._fh = None

        self._ready = False

        # self.create_new_session(description)
        # TODO Build in checks so that you don't try to write to an emptry file

    def __del__(self):
        self._fh.close()
        self._logger.removeHandler(self._fh)

    def create_new_session(self, description = 'Default Description'):
        if self._fh is not None:
            self._fh.close()
            self._logger.removeHandler(self._fh)

        self._session_folder = self._create_folder()
        self._prep_folder()

        self._fh = self._create_file_handler()
        self._logger.addHandler(self._fh)

        self._ready = True
        self.log("Session Description : %s" % description)

    def get_session_folder(self):
        if self._ready is True:
            return self._session_folder
        else:
            return None

    def get_log_fp(self):
        if self._ready is True:
            return self._log_fp
        else:
            return None

    def _create_file_handler(self):
        session_filename = "%s_session%.2d.log" %(time.strftime("%Y_%m_%d"), self._session_count)
        self._log_fp = os.path.join(self._session_folder, session_filename)
        fh = logging.FileHandler(self._log_fp)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt='%I:%M:%S %p'))
        fh.setLevel(logging.DEBUG)
        return fh

    def _create_folder(self):
        if os.path.isdir(self._root_folder) is False:
            os.mkdir(self._root_folder)

        date_str = time.strftime("%Y_%m_%d")
        date_folder = os.path.join(self._root_folder, date_str)
        if os.path.isdir(date_folder) is False:
            os.mkdir(date_folder)

        session_count = 0
        session_folder = os.path.join(date_folder, '%s_session%.2d' %(date_str, session_count))
        while os.path.isdir(session_folder) is True:
            session_count += 1
            session_folder = os.path.join(date_folder, '%s_session%.2d' %(date_str, session_count))

        os.mkdir(session_folder)
        self._session_count = session_count

        return session_folder

    def _prep_folder(self):
        if os.path.isdir(os.path.join(self._session_folder, 'images')) is False:
            os.mkdir(os.path.join(self._session_folder, 'images'))

        shutil.copyfile(CONFIG_FP, os.path.join(self._session_folder, 'initial.cfg'))

    def log(self, msg):
        if self._ready is True:
            self._logger.info(msg)

    def convert_file_to_xml(self):
        pass
