"""As cameras are now subjects, we want a way to capture the notifications emitted by a camera.

Trick is to have it happen in a separate thread, so that logging to disk does not cause any delays
to the operation of the camera.
"""

import os
import threading
from datetime import datetime
from logging import Formatter, FileHandler, DEBUG, getLogger
from support.basic import Observer, ThreadedLogger


class cameraLoggingObserver(Observer, ThreadedLogger):
    """Observer for an abstract_camera camera, logs notification in separate thread."""

    def __init__(self, log_fp: str, subject_cameras=None):
        """Constructor, instantiate log file and handler with optional subject attachment."""
        super(cameraLoggingObserver, self).__init__(subject_cameras)

        handler = FileHandler(filename=log_fp)
        handler.setLevel(DEBUG)
        handler.setFormatter(Formatter("%(message)s "))
        self._logger = getLogger(log_fp)
        self._logger.propagate = False
        self._logger.addHandler(handler)
        self._logger.info('Rate Logging Started')

        _, filename = os.path.split(log_fp)
        getLogger().info('Rate logging file instantiated for camera at %s.', filename)

        self.start_thread()

    def update(self, subject_camera):
        """Update function called by the subject camera."""
        self._messages.append('%s : %d : %s' % (str(datetime.now()).replace('.', ','),
                                                subject_camera.get_cam_image_count(),
                                                subject_camera.update_message))
        self._log_event.set()
