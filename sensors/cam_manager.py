""" D Joubert 16 November 2016 - Camera managers for Tricap app"""

# TODO Wrong place, but the overall logger should be attached to the session logger, so that those
# error messages get captured to the session folder as well. Or mmaybe separetely, so you can still
# read the alti messages?

# TODO Settings page should show warnning for all incorrectly formatted settings

import threading
import time
import traceback

# gphoto2 importing is wrapped in a try/except as it is not available in Windows, but I still want
#  to be able to code and test in windows
try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    print("Error import gphoto2, switching over dummmy cam managers")
    GPHOTO2_IMPORTED = False

from .cameras import Canon6DCam, Cam
from .configure import TricapConfig

from config import CAM_MANAGER_STATES, DEFAULT_IMAGE_CAPTURE_INTERVAL
from config import RET_OK, RET_ERROR

class CamsManager():
    """Base class for all camera managers. Camera managers handle the starting, stopping
    and other administration of cameras. Also servers as dummy class when testing on windows."""
    def __init__(self, num_cams):
        self._num_cams = num_cams
        self.state = CAM_MANAGER_STATES.STOPPED
        self._cameras = []

        for _ in range(self._num_cams):
            self._cameras.append(Cam())

    def reset(self):
        self.state = CAM_MANAGER_STATES.STOPPED

    def start_capturing(self):
        self.state = CAM_MANAGER_STATES.STARTED

    def stop_capturing(self):
        self.state = CAM_MANAGER_STATES.STOPPED

    def get_num_cams(self):
        return self._num_cams

    def get_cam_ids(self):
        return range(self._num_cams)

    def get_cameras_as_list(self):
        return self._cameras

    def get_choices_for_setting(self, setting_str):
        return self._cameras[0].get_choices_for_setting(setting_str)

    def get_setting(self, setting_str):
        return self._cameras[0].get_setting(setting_str)

    def set_setting(self, setting_str, setting_value):
        return self._cameras[0].set_setting(setting_str, setting_value)


class TriCapCamsManager(CamsManager):
    """TriCapCamsManager manages the Canon EOS 6D camera objects"""

    def __init__(self, logger, context):
        self.state = CAM_MANAGER_STATES.STOPPED

        self._context = context

        self._image_capture_interval = None

        self._capture_thread = None
        self._kill_pill = None

        # Log the Gphoto2 version info, so we can check if we set it correctly
        self._logger = logger
        self._logger.info('GPHOTO2 version info: ' + str(gp.gp_library_version(True)))

        self._cameras = None

        # threading members
        self._cam_threads = None
        self._capture_thread = None
        self._kill_pill = None  # Each thread is halted by setting the kill pill event

        self._initialise()

    def _initialise(self):
        self._find_cameras()

        # clear the threads
        self._cam_threads = []
        self._capture_thread = None

        # TODO Check that this fits in with the reset/changing of settings protocol
        tricap_config = TricapConfig(self._logger)
        ici = tricap_config.get('image_capture_interval', TricapConfig.FLOAT)
        if ici is None:
            ici = DEFAULT_IMAGE_CAPTURE_INTERVAL
        self._image_capture_interval = ici

    def set_image_capture_interval(self, interval):
        if isinstance(interval, str):
            interval = float(interval)

        self._image_capture_interval = interval

        return RET_OK

    def get_image_capture_interval(self):
        return self._image_capture_interval

    def _find_cameras(self):
        """ Use gphoto2 to detect cameras and keep track of them """
        self._cameras = []

        try:
            port_info_list = gp.PortInfoList()
            port_info_list.load()

            for name, addr in self._context.camera_autodetect():

                if name == "Canon EOS 6D":
                    self._logger.info('Adding camera %s at port %s ' %(name, addr))
                    idx = port_info_list.lookup_path(addr)
                    tricap_cam = Canon6DCam(self._context, port_info_list[idx], self._logger)
                    self._cameras.append(tricap_cam)

        except gp.GPhoto2Error as ex:
            self.state = CAM_MANAGER_STATES.ERROR_CONFIG
            self._logger.error('Error finding cameras')
            self._logger.error('GPhoto2 Error: %d : %s' %(ex.code, ex.string))
        except Exception:  # Catches most exceptions, except KeyboardInterrupt and SystemExit
            self._logger.error(traceback.format_exc())
            return RET_ERROR

        return RET_OK

    def reset(self):
        """ Reset the manager by calling _initialise again, which will redetect the cameras """
        if self.state == CAM_MANAGER_STATES.STARTED:
            self.stop_capturing()

        self._initialise()

    def _cap_thread_generator(self):
        """ Generate the threads for the capture functions for each camera """
        for index, cam in enumerate(self._cameras):
            thread = threading.Thread(target=cam.create_single_capture_func(),
                                      args=[index])
            yield thread


    def _start_capture_with_wait_thread(self):
        """ Start the overall capturing threads, which instantiates the camera threads over and
            over"""

        # define a worker function to run in a separate thread
        def worker(stop_event):
            # TODO How long do we need to wait for a stop event? Is there another way to do this?
            while not stop_event.wait(0.01):
                prev_time = time.time()

                cam_threads = list(self._cap_thread_generator())
                for t in cam_threads:
                    t.start()
                for t in cam_threads:
                    t.join()

                current_time_diff = time.time() - prev_time

                self._logger.debug('Capture time: ' + str(current_time_diff))
                if current_time_diff < self._image_capture_interval:
                    time.sleep(self._image_capture_interval - current_time_diff)

        self._capture_thread = threading.Thread(target=worker, args=[self._kill_pill])
        self._capture_thread.start()

    def start_capturing(self):
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
        elif self.state == CAM_MANAGER_STATES.STOPPED:
            self._kill_pill = threading.Event()
            self._start_capture_with_wait_thread()
            self.state = CAM_MANAGER_STATES.STARTED

    def stop_capturing(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            self._capture_thread.join()
            self.state = CAM_MANAGER_STATES.STOPPED

    def get_num_cams(self):
        return len(self._cameras)

    def get_cam_ids(self):
        cam_ids = []
        for cam in self._cameras:
            if cam.serial_num is not None:
                cam_ids.append(cam.serial_num)
            else:
                cam_ids.append('Unknown')

        return cam_ids

    def get_choices_for_setting(self, setting_str):
        choices = None

        if self.get_num_cams() > 0:
            choices = self._cameras[0].get_choices_for_setting(setting_str)

        return choices

    def get_setting(self, setting_str):
        # TODO I don't like throwing an exception for every value that is not from the camera

        # check first if it's an cam manager setting
        if setting_str == 'image_capture_interval':
            return self._image_capture_interval

        return self._cameras[0].get_setting(setting_str)

    def set_setting(self, setting_str, val_str):
        # check first if it's an cam manager setting
        if setting_str == 'image_capture_interval':
            self._image_capture_interval = float(val_str)
            return RET_OK

        ret_val = RET_OK
        for camera in self._cameras:
            if camera.set_setting(setting_str, val_str) != RET_OK:
                ret_val = RET_ERROR
        return ret_val
