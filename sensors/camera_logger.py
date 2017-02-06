"""As cameras are now subjects, we want a way to capture the notifications emitted by a camera.

Trick is to have it happen in a separate thread, so that logging to disk does not cause any delays
to the operation of the camera.
"""

import os
import threading
from datetime import datetime
from logging import Formatter, FileHandler, DEBUG, getLogger
from support.basic import Observer


class cameraLoggingObserver(Observer):
    """Observer for an abstract_camera camera, logs notification in separate thread."""

    def __init__(self, log_fp: str, subject_cameras=None):
        """Constructor, instantiate log file and handler with optional subject attachment."""
        super(cameraLoggingObserver, self).__init__(subject_cameras)

        handler = FileHandler(filename=log_fp)
        handler.setLevel(DEBUG)
        handler.setFormatter(Formatter("%(message)s "))
        self._logger = getLogger(log_fp)
        self._logger.propragate = False
        self._logger.addHandler(handler)
        self._logger.info('Rate Logging Started')

        _, filename = os.path.split(log_fp)
        getLogger().info('Rate logging file instantiated for camera at %s.', filename)

        self._stop_event = threading.Event()
        self._log_event = threading.Event()
        self._messages = []

        thread = threading.Thread(target=self._log_message, daemon=True,
                                  kwargs={"log_event": self._log_event,
                                          "stop_event": self._stop_event})
        thread.start()

    def __del__(self):
        """Destructor."""
        self._stop_event.set()

    def _log_message(self, log_event: threading.Event, stop_event: threading.Event):
        """Log message, to be called by threaded function."""
        while True:
            if stop_event.is_set():
                return

            if log_event.wait(5):
                for message in self._messages:
                    self._logger.info(message)
                self._messages.clear()
                log_event.clear()

    def update(self, subject_camera):
        """Update function called by the subject camera."""
        self._messages.append('%s : %d : %s' % (str(datetime.now()).replace('.', ','),
                                                subject_camera.get_cam_image_count(),
                                                subject_camera.update_message))
        self._log_event.set()
