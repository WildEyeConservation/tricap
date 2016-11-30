""" D Joubert - Innoventix Consulting - 18 November 2016 - session_logger.py
    Logger for data, to be used for importing the data into the larger system """

import logging
import os
import shutil
import time

from config import SESSION_ROOT_DIR, CONFIG_FP, RET_OK, SERVER_LOG_DIR

class SessionLogger:
    """ The session logger is responsible for creating a session folder, a session data file
        (which will most likely only contain the data from the altimeter), copying the config file
        and creating any additional data structures. """

    def __init__(self, description='Default Description', root_folder=SESSION_ROOT_DIR):

        self._root_folder = root_folder

        self._logger = logging.getLogger('session_logger')
        self._logger.setLevel(logging.DEBUG)
         # The session_logger is not an error logger, messages logged to it should not be pushed to
         #  the rootlogger
        self._logger.propagate = False

        self._session_count = None
        self._log_fp = None
        self._session_folder = None
        self._fh = None
        self._server_fh = None
        self._description = description

        self._ready = False

    def __del__(self):
        if self._fh is not None:
            self._fh.close()
            self._logger.removeHandler(self._fh)

        if self._server_fh is not None:
            self._server_fh.close()
            logging.getLogger('').removeHandler(self._server_fh)

    def set_description(self, description):
        self._description = description
        return RET_OK

    def get_description(self):
        return self._description

    def create_new_session(self, description=None):
        if self._fh is not None:
            self._fh.close()
            self._logger.removeHandler(self._fh)

        if description is not None:
            self._description = description

        self._session_folder = self._create_folder()
        self._prep_folder()

        self._fh = self._create_file_handler()
        self._logger.addHandler(self._fh)

        self._copy_and_link_to_root_logger()

        self._ready = True
        self.log("Session Description : %s" % self._description)

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
        session_filename = "%s_session%.2d.log" % (time.strftime("%Y_%m_%d"), self._session_count)
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
        session_folder = os.path.join(date_folder, '%s_session%.2d' % (date_str, session_count))
        while os.path.isdir(session_folder) is True:
            session_count += 1
            session_folder = os.path.join(date_folder, '%s_session%.2d' % (date_str, session_count))

        os.mkdir(session_folder)
        self._session_count = session_count

        return session_folder

    def _prep_folder(self):
        if os.path.isdir(os.path.join(self._session_folder, 'images')) is False:
            os.mkdir(os.path.join(self._session_folder, 'images'))

        shutil.copyfile(CONFIG_FP, os.path.join(self._session_folder, 'initial.cfg'))

    def _copy_and_link_to_root_logger(self):
        root_log = os.path.join(SERVER_LOG_DIR, 'tricap_server.log')
        if os.path.isfile(root_log):
            # Don't care if it overwrites any existing pre-session_server log, it will contain same
            #  info anyway
            shutil.copyfile(root_log, os.path.join(self._session_folder, 'pre_session_server.log'))

        # create a file handler so that all messages to root log are also sent to the session log
        format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
        log_fp = os.path.join(self._session_folder, 'session_server.log')
        self._server_fh = logging.FileHandler(filename=log_fp)
        self._server_fh.setLevel(logging.DEBUG)
        self._server_fh.setFormatter(logging.Formatter(format_str))
        rootlogger = logging.getLogger('')
        rootlogger.addHandler(self._server_fh)

    def log(self, msg):
        if self._ready is True:
            self._logger.info(msg)

    def convert_file_to_xml(self):
        """ Not implemented yet, might be usefull"""
        pass
