""" D Joubert 16 November 2016 - Camera managers for Tricap app"""

import threading
import time

from abc import abstractmethod, ABCMeta

try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    print("Error import gphoto2, switching over dummmy cam managers")
    GPHOTO2_IMPORTED = False

from .cameras import Canon6DCam, Cam

from config import CAM_MANAGER_STATES, DEFAULT_IMAGE_CAPTURE_INTERVAL, DEFAULT_SHUTTER_SPEED

class CamsManager():
    """Abstract base class for all camera managers. Camera managers handle the starting, stopping
    and other administration of cameras."""
    __metaclass__ = ABCMeta

    def __init__(self):
        self.state = -1

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def start_capturing(self):
        pass

    @abstractmethod
    def stop_capturing(self):
        pass

    @abstractmethod
    def get_num_cams(self):
        pass

    @abstractmethod
    def get_cam_ids(self):
        pass

    @abstractmethod
    # TODO Fix naming convention on shutter speeds
    def get_shutter_speed_as_string(self):
        pass

    @abstractmethod
    def set_shutterspeed(self, val_str):
        pass

    @abstractmethod
    def get_image_capture_interval(self):
        pass

    @abstractmethod
    def set_image_capture_interval(self, val):
        pass

class TriCapCamsManager(CamsManager):
    """TriCapCamsManager manages TriCap camera objects"""

    def __init__(self, logger, context):
        CamsManager.__init__(self)

        self.state = CAM_MANAGER_STATES.STOPPED

        self._context = context

        self._capture_thread = None
        self._kill_pill = None
        self._image_capture_interval = None

        self._logger = logger
        self._logger.info('GPHOTO2 version info: ' + str(gp.gp_library_version(True)))

        self.reset()

    def _get_cameras(self):
        cameras = []

        port_info_list = gp.PortInfoList()
        port_info_list.load()

        for name, addr in self._context.camera_autodetect():

            if name == "Canon EOS 6D":
                self._logger.debug('Adding camera %s at port %s ' %(name, addr))
                idx = port_info_list.lookup_path(addr)
                tricap_cam = Canon6DCam(self._context, port_info_list[idx], self._logger)
                cameras.append(tricap_cam)

        return cameras

    def get_cameras_as_list(self):
        return self._cameras

    def reset(self):
        if self.state == CAM_MANAGER_STATES.STARTED:
            self.stop_capturing()

        self._cameras = self._get_cameras()

        self._cam_threads = []
        self._capture_thread = None

        # TODO This should be read from the init config file
        self._image_capture_interval = DEFAULT_IMAGE_CAPTURE_INTERVAL

        self._kill_pill = None

    def _cap_thread_generator(self):
        for index, cam in enumerate(self._cameras):
            thread = threading.Thread(target=cam.create_single_capture_func(),
                                      args=[index])
            yield thread


    def _start_capture_with_wait_thread(self):
        # define a worker function to run in a separate thread
        def worker(stop_event):
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
                    time.sleep(self._image_capture_interval- current_time_diff)


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
        return self._cameras[0].get_shutter_speed_as_string()

    def set_shutterspeed(self, val_str):
        ret_val = 0
        for cam in self._cameras:
            ret_val += cam.set_shutterspeed(val_str)

        if ret_val > 0:
            self._logger.error('Error setting the shutterspeed of the cameras %s' % val_str)
            return -1

        return 0

    def set_image_capture_interval(self, val):
        if isinstance(val, float) is False or isinstance(val, int):
            self._logger.error('Incorrect type of val for setting the image cap int')
            return -1

        self._image_capture_interval = val

        return 0

    def get_image_capture_interval(self):
        return self._image_capture_interval


class DummyTricapManager(CamsManager):
    """DummyTricapManager fakes the handling of dummy cameras"""

    def __init__(self, num_cams):
        CamsManager.__init__(self)

        self._num_cams = num_cams
        self.state = CAM_MANAGER_STATES.STOPPED
        self._cameras = []

        for _ in range(self._num_cams):
            self._cameras.append(Cam())

    def reset(self):
        pass

    def start_capturing(self):
        self.state = CAM_MANAGER_STATES.STARTED

    def stop_capturing(self):
        self.state = CAM_MANAGER_STATES.STOPPED

    def get_cam_fp_queue(self):
        return None

    def get_num_cams(self):
        return self._num_cams

    def get_cam_ids(self):
        return range(self._num_cams)

    def get_cameras_as_list(self):
        return self._cameras

    def get_shutter_speed_as_string(self):
        return DEFAULT_SHUTTER_SPEED

    def set_shutterspeed(self, val_str):
        pass

    def set_image_capture_interval(self, val):
        pass

    def get_image_capture_interval(self):
        return DEFAULT_IMAGE_CAPTURE_INTERVAL

# def create_tricap_cameras_and_manager(logger):
#     gp_context = gp.Context()
#     tricap_cameras = _get_cameras(gp_context, logger)
#     tricap_manager = TriCapCamsManager(tricap_cameras, logger)
#     return tricap_cameras, tricap_manager
