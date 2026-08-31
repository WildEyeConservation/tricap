"""D Joubert - Innoventix Consulting - 18 November 2016 - session_logger.py.

Logger for data, to be used for importing the data into the larger system.
"""

import logging
import os
import shutil
import time

from support.basic import ThreadedLogger

from config import SESSION_ROOT_DIR, CONFIG_FP, SERVER_LOG_DIR


class SessionLogger(ThreadedLogger):
    """The SessionLogger is responsible for recording session data.

    The session logger is responsible for creating a session folder, a session data file
    (which will most likely only contain the data from the altimeter), copying the config file
    and creating any additional data structures.
    If something goes wrong with using the SessionLogger, it is seen as not critical enough to
    halt operation by default. So exceptions should be caught and logged. That said, the
    list of exceptions to catch will be quite restricted, so if something weird happens, it
    is better to break the system (fail early).
    """

    _root_logger = logging.getLogger(__name__)

    def __init__(self, description='Default Description', root_folder=SESSION_ROOT_DIR,
                 log_names_to_track=[]):
        """Constructor, inherits from ThreadedLogger."""
        super(SessionLogger, self).__init__()
        self._root_folder = root_folder

        self._logger = logging.getLogger('session_logger')
        self._logger.setLevel(logging.DEBUG)
        # The session_logger is not an error logger, messages logged to it should not be pushed to
        #  the rootlogger
        self._logger.propagate = False

        # Note: Important to keep equivalency between the log names tracked and the filehandlers
        self.log_names_tracked = log_names_to_track

        self._session_count = None
        self._log_fp = None
        self._session_folder = None
        self._session_fh = None

        self._additional_fhs = None

        self._description = description

        self._ready = False

    def __del__(self):
        """Destructor, have to explicitly remove the handlers from the log file."""
        self._stop_event.set()
        self.thread.join()
        self._remove_handlers()
        super(SessionLogger, self).__del__()

    def _remove_handlers(self):
        if self._session_fh is not None:
            self._logger.removeHandler(self._session_fh)
            self._session_fh.close()

        if self._additional_fhs is not None and len(self._additional_fhs) > 0:
            for index, log_name in enumerate(self.log_names_tracked):
                logging.getLogger(log_name).removeHandler(self._additional_fhs[index])
                self._additional_fhs[index].close()
            self._additional_fhs = []

    def is_ready(self):
        return self._ready

    def set_description(self, description):
        self._description = description

    def get_description(self):
        return self._description

    def create_new_session(self, description=None):
        self._ready = False

        if description is not None:
            self._description = description
        try:
            self._remove_handlers()
            self.start_thread()
            self._session_folder = self._create_folder()
            self._prep_folder()
            self._session_fh = self._create_file_handler()
            self._session_fh.setLevel(logging.DEBUG)
            self._logger.addHandler(self._session_fh)

            # need to set ready to true otherwise the log function won't work.
            self._ready = True
            self.log("Session Description : %s" % self._description)
        except FileNotFoundError as ex:
            self._root_logger.error(ex)
            self._ready = False

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

        date_str = time.strftime("%Y-%m-%d")
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

        if os.path.isdir(os.path.join(self._session_folder, 'pre')) is False:
            os.mkdir(os.path.join(self._session_folder, 'pre'))

        shutil.copyfile(CONFIG_FP, os.path.join(self._session_folder, 'initial.cfg'))

        real_log_names_tracked = []
        self._additional_fhs = []
        for log_name in self.log_names_tracked:
            # the root log is weird: log.name will give 'root', but must be added using ''
            if log_name == 'root':
                log_name = ''
            log = logging.getLogger(log_name)
            if len(log.handlers) == 0:
                logging.getLogger('').warning('No loggers were found named %s', log_name)
                continue

            # need to search the logger for a handler with a file output
            log_file_handler = None
            for handler in log.handlers:
                if hasattr(handler, 'baseFilename'):
                    log_file_handler = handler
                    break
            if log_file_handler is None:
                logging.getLogger('').warning('Logger %s has no file handlers.', log_name)
                continue

            # pre copying
            # assumme that there is only one handler, which is a fileHandler.
            original_fp = log_file_handler.baseFilename
            _, original_filename_with_ext = os.path.split(original_fp)
            shutil.copyfile(original_fp, os.path.join(self._session_folder, 'pre',
                                                      original_filename_with_ext))

            # hook up to the log
            new_handler = logging.FileHandler(filename=os.path.join(self._session_folder,
                                                                    original_filename_with_ext))
            new_handler.setLevel(logging.DEBUG)
            new_handler.setFormatter(log.handlers[0].formatter)
            log.addHandler(new_handler)
            self._additional_fhs.append(new_handler)

            real_log_names_tracked.append(log_name)

        # update the names tracked with those actually tracked
        self.log_names_tracked = real_log_names_tracked

    def log(self, msg):
        """Log the msg to the session log."""
        if self._ready:
            self._messages.append(msg)
            self._log_event.set()
