""" D Joubert 16 November 2016 - Camera managers for Tricap app"""

import threading
import time
import traceback

try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    print("Error import gphoto2, switching over dummmy cam managers")
    GPHOTO2_IMPORTED = False

from .cameras import Canon6DCam, Cam

from config import CAM_MANAGER_STATES, DEFAULT_IMAGE_CAPTURE_INTERVAL
from config import RET_OK, RET_ERROR

class CamsManager():
    """Abstract base class for all camera managers. Camera managers handle the starting, stopping
    and other administration of cameras. Also servers as dummy class."""
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

    def get_shutter_speed_as_string(self):
        return "1/Dummy"

    def set_shutterspeed(self, val_str):
        return RET_OK

    def set_image_capture_interval(self, val):
        return RET_OK

    def get_image_capture_interval(self):
        return DEFAULT_IMAGE_CAPTURE_INTERVAL

    def get_choices_for_config(self, config_str):
        choices = None

        if config_str == 'shutterspeed':
            choices = ['1/4', '1/640', '1/2500']
        elif config_str == 'iso':
            choices = ['auto', '100', '200']

        return choices

    def get_setting(self, setting_str):
        ret_val = None
        if setting_str == 'shutterspeed':
            ret_val = '1/640'
        elif setting_str == 'iso':
            ret_val = '100'
        else:
            ret_val = 'setting_str'

        return ret_val

class TriCapCamsManager(CamsManager):
    """TriCapCamsManager manages TriCap camera objects"""

    def __init__(self, logger, context):
        self.state = CAM_MANAGER_STATES.STOPPED

        self._context = context

        self._capture_thread = None
        self._kill_pill = None
        self._image_capture_interval = None

        self._logger = logger
        self._logger.info('GPHOTO2 version info: ' + str(gp.gp_library_version(True)))

        self._cameras = None
        self._cam_threads = None
        self._capture_thread = None
        self._image_capture_interval = None
        self._kill_pill = None

        self._initialise()

    def _initialise(self):
        self._find_cameras()

        # clear the threads
        self._cam_threads = []
        self._capture_thread = None

        # TODO This should be read from the init config file
        self._image_capture_interval = DEFAULT_IMAGE_CAPTURE_INTERVAL

    def _find_cameras(self):
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
        if self.state == CAM_MANAGER_STATES.STARTED:
            self.stop_capturing()

        self._initialise()

    def _cap_thread_generator(self):
        for index, cam in enumerate(self._cameras):
            thread = threading.Thread(target=cam.create_single_capture_func(),
                                      args=[index])
            yield thread


    def _start_capture_with_wait_thread(self):
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

    def get_shutter_speed_as_string(self):
        # TODO Should do some error checking here, like if there are no cameras!
        if len(self._cameras) == 0:
            self.state = CAM_MANAGER_STATES.ERROR_NO_CAMS
            return "No Cams Detected"
        else:
            # Assuming that all cameras are set to the same shutter speed, should probably do
            #  an error check here
            return self._cameras[0].get_shutter_speed_as_string()

    def set_shutterspeed(self, val_str):
        ret_val = 0
        for cam in self._cameras:
            ret_val += cam.set_shutterspeed(val_str)

        if ret_val > 0:
            self._logger.error('Error setting the shutterspeed of the cameras %s' % val_str)
            return RET_ERROR

        return RET_OK

    def set_image_capture_interval(self, val):
        if isinstance(val, float) is False or isinstance(val, int):
            self._logger.error('Incorrect type of val for setting the image cap int')
            return RET_ERROR

        self._image_capture_interval = val

        return RET_OK

    def get_image_capture_interval(self):
        return self._image_capture_interval

    def get_choices_for_config(self, config_str):
        choices = None

        if self.get_num_cams() > 0:
            choices = self._cameras[0].get_choices_for_config(config_str)

        return choices
