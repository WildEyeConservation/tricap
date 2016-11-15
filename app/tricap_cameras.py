import os
import time
import threading
import pdb

from abc import ABCMeta, abstractmethod

# As their is no gphoto2 for windows, we have to switch to using dummmies while working under
#  windows.
try:
    import gphoto2 as gp
    GPHOTO2_IMPORTED = True
except ImportError:
    print("Error import gphoto2, switching over dummy camera handler")
    GPHOTO2_IMPORTED = False

from queue import LifoQueue

from config import CE6D_CAP_TARGET_SD_CARD, CE6D_SHUT_SPEED_1_4, CE6D_SHUT_SPEED_1_2500
from config import CE6D_FORMAT_RAW_AND_TINY_JPEG, CE6D_SHUT_SPEED_1_640
from config import TRICAP_CAMS_MANAGER_STATES, DISPLAY_DOWNLOAD_DIR, TRICAP_CAM_STATES
from config import CAM_IMAGE_PREFIX, IMAGE_CAPTURE_INTERVAL, TRICAP_CAM_STATE_STRINGS

#TODO setup from config file
#TODO currently, we are coding in a mess of C vs C++ styles. Fix this.

class Cam():
    """ Abstract base class for all camera handlers."""

    def __init__(self):
        self.state = -1

    @abstractmethod
    def get_state_as_string(self):
        pass


class TriCapCam(Cam):

    def __init__(self, context, port_info, logger):
        Cam.__init__(self)
        self._context = context
        self._gp_camera = gp.Camera()

        self.serial_num = None

        self._logger = logger

        self.state = TRICAP_CAM_STATES.UNINITIALISED

        ret_val = self._setup_camera(port_info)

        if ret_val == 0:
            self.state = TRICAP_CAM_STATES.INITIALISED

    def _check_for_error(self, ret_code, error_message):
        if ret_code != 0:
            error_message += ' : ret_code %d' % ret_code
            self._logger.error(error_message)

        return ret_code

    def _get_config_value(self, config_str):
        # get configuration tree
        config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))

        ret_code, config_widget = gp.gp_widget_get_child_by_name(config, config_str)
        if self._check_for_error(ret_code, 'Error retrieving config widget %s' % config_str):
            self.state = TRICAP_CAM_STATES.ERROR_CONFIG
            return ret_code

        # set the actual value
        ret_code, value = gp.gp_widget_get_value(config_widget)
        if self._check_for_error(ret_code, 'Error getting widget %s value' % config_str):
            self.state = TRICAP_CAM_STATES.ERROR_CONFIG
            return ret_code

        return value

    def _config_cam_value(self, config, config_str, config_value):
        # find the capture target config item
        ret_code, config_widget = gp.gp_widget_get_child_by_name(config, config_str)
        if self._check_for_error(ret_code, 'Error retrieving config widget %s' % config_str):
            self.state = TRICAP_CAM_STATES.ERROR_CONFIG
            return ret_code

        # get the config choice data structure
        ret_code, value = gp.gp_widget_get_choice(config_widget, config_value)
        if self._check_for_error(ret_code,
                                 'Error retrieving choice %d for %s' % (config_value, config_str)):
            self.state = TRICAP_CAM_STATES.ERROR_CONFIG
            return ret_code

        # set the actual value
        ret_code = gp.gp_widget_set_value(config_widget, value)
        if self._check_for_error(ret_code, 'Error setting widget %s value' % config_str):
            self.state = TRICAP_CAM_STATES.ERROR_CONFIG
            return ret_code

        # set config
        ret_code = gp.gp_camera_set_config(self._gp_camera, config, self._context)
        if self._check_for_error(ret_code,
                                 'Could not set config for %s' % config_str):
            return ret_code

        self._logger.debug('Succesfully set %s on camera.' % config_str)

        return 0

    def _obtain_serial_num(self, config):
        # get serial number
        ret_code, eossernum_config = gp.gp_widget_get_child_by_name(config, 'eosserialnumber')
        if self._check_for_error(ret_code, 'Could not get widget to retrieve serial number'):
            return ret_code

        ret_code, eossernum = gp.gp_widget_get_value(eossernum_config)
        if self._check_for_error(ret_code, 'Could not get retrieve serial number'):
            return ret_code

        self._logger.info('Succesfully retrieved camera serial number %s' % eossernum)

        self.serial_num = eossernum

        return 0

    def _setup_camera(self, port_info):
        self._gp_camera.set_port_info(port_info)
        self._gp_camera.init(self._context)

        # get configuration tree
        config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))

        ret_val = 0

        ret_val += self._config_cam_value(config, 'capturetarget', CE6D_CAP_TARGET_SD_CARD)
        ret_val += self._config_cam_value(config, 'shutterspeed', CE6D_SHUT_SPEED_1_4)
        ret_val += self._config_cam_value(config, 'imageformat', CE6D_FORMAT_RAW_AND_TINY_JPEG)
        ret_val += self._obtain_serial_num(config)

        return ret_val

    def get_shutter_speed_as_string(self):
        shutter_speed_code = self._get_config_value('shutterspeed')

        # CE6D_SHUT_SPEED_1_2500 = 49
        # CE6D_SHUT_SPEED_1_640 = 43
        # CE6D_SHUT_SPEED_1_4 = 21

        if shutter_speed_code == CE6D_SHUT_SPEED_1_2500:
            return '1/2500'
        elif shutter_speed_code == CE6D_SHUT_SPEED_1_640:
            return '1/640'
        elif shutter_speed_code == CE6D_SHUT_SPEED_1_4:
            return '1/4'
        else:
            self._logger.error('Shutter speed code unkown: %s' % shutter_speed_code)
            return '? %s' % shutter_speed_code

    # TODO We are not letting the user know there was an error downloading an image, should we?

    def create_single_capture_func(self):
        def worker(cam_num):
            if self.state == TRICAP_CAM_STATES.INITIALISED:
                self.state = TRICAP_CAM_STATES.CAPTURING
                # Capture an image
                ret_code, file_path = gp.gp_camera_capture(self._gp_camera,
                                                           gp.GP_CAPTURE_IMAGE,
                                                           self._context)

                if self._check_for_error(ret_code,
                                         'Error capturing cam %d image ' % cam_num):
                    self.state = TRICAP_CAM_STATES.ERROR_CAPTURE

                # Download the jpg image
                img_name, _ = os.path.splitext(file_path.name)
                # try to get the jpg, camera might still be converting
                ret_code, camera_file = gp.gp_camera_file_get(self._gp_camera,
                                                              file_path.folder,
                                                              img_name+'.JPG',
                                                              gp.GP_FILE_TYPE_NORMAL,
                                                              self._context)
                if ret_code == 0:
                    download_fp = os.path.join(DISPLAY_DOWNLOAD_DIR,
                                               CAM_IMAGE_PREFIX+str(cam_num)+'.JPG')
                    if os.path.isfile(download_fp) is True:
                        os.remove(download_fp)

                    ret_code = gp.gp_file_save(camera_file, download_fp)
                    if self._check_for_error(ret_code,
                                             'Error saving cam %d image' %cam_num):
                        self.state = TRICAP_CAM_STATES.ERROR_CAPTURE
                else:
                    self._logger.error('Failed to download cam %d image : ret_code %d'
                                       % (cam_num, ret_code))
                    self.state = TRICAP_CAM_STATES.ERROR_CAPTURE

                self._gp_camera.exit(self._context)

                if self.state == TRICAP_CAM_STATES.CAPTURING:
                    self.state = TRICAP_CAM_STATES.INITIALISED

        return worker

    def get_state_as_string(self):
        return TRICAP_CAM_STATE_STRINGS[self.state]

class DummyCam(Cam):
    def __init__(self):
        Cam.__init__(self)
        self.state = TRICAP_CAM_STATES.INITIALISED

    def get_state_as_string(self):
        return "Dummy cam is stateless."


class CamsManager():
    """Abstract base class for all camera managers. Camera managers handle the starting, stopping
    and other administration of cameras."""
    __metaclass__ = ABCMeta

    def __init__(self):
        self.state = -1

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
    def get_shutter_speed_as_string(self):
        pass

    @abstractmethod
    def get_image_capture_interval(self):
        pass

class TriCapCamsManager(CamsManager):
    """TriCapCamsManager manages TriCap camera objects"""

    def __init__(self, cameras, logger):
        CamsManager.__init__(self)

        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

        self._cameras = cameras

        self._cam_threads = []
        self._capture_thread = None

        self._image_capture_interval = IMAGE_CAPTURE_INTERVAL

        self._kill_pill = None

        self._logger = logger
        self._logger.info('GPHOTO2 version info: ' + str(gp.gp_library_version(True)))

        self._cam_fp_queue = LifoQueue(maxsize=0)

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
            self.state = TRICAP_CAMS_MANAGER_STATES.ERROR_NO_CAMS
        elif self.state == TRICAP_CAMS_MANAGER_STATES.STOPPED:
            self._kill_pill = threading.Event()
            self._start_capture_with_wait_thread()
            self.state = TRICAP_CAMS_MANAGER_STATES.STARTED

    def stop_capturing(self):
        if self.state == TRICAP_CAMS_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            self._capture_thread.join()
            self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

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
        # TODO Should do some error checking here
        return self._cameras[0].get_shutter_speed_as_string()

    def get_image_capture_interval(self):
        return self._image_capture_interval


class DummyTricapManager(CamsManager):
    """DummyTricapManager fakes the handling of dummy cameras"""

    def __init__(self, num_cams):
        CamsManager.__init__(self)

        self._num_cams = num_cams
        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED
        self._cameras = []

        for _ in range(self._num_cams):
            self._cameras.append(DummyCam())

    def start_capturing(self):
        self.state = TRICAP_CAMS_MANAGER_STATES.STARTED

    def stop_capturing(self):
        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

    def get_cam_fp_queue(self):
        return None

    def get_num_cams(self):
        return self._num_cams

    def get_cam_ids(self):
        return range(self._num_cams)

    def get_cameras_as_list(self):
        return self._cameras

    def get_shutter_speed_as_string(self):
        return CE6D_SHUT_SPEED_1_2500

    def get_image_capture_interval(self):
        return IMAGE_CAPTURE_INTERVAL


def _get_cameras(context, logger):
    cameras = []

    port_info_list = gp.PortInfoList()
    port_info_list.load()

    for name, addr in context.camera_autodetect():

        if name == "Canon EOS 6D":
            logger.debug('Adding camera %s at port %s ' %(name, addr))
            idx = port_info_list.lookup_path(addr)
            tricap_cam = TriCapCam(context, port_info_list[idx], logger)
            cameras.append(tricap_cam)

    return cameras

def create_tricap_cameras_and_manager(logger):
    gp_context = gp.Context()
    tricap_cameras = _get_cameras(gp_context, logger)
    tricap_manager = TriCapCamsManager(tricap_cameras, logger)
    return tricap_cameras, tricap_manager
