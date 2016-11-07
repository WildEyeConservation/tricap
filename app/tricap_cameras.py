import threading

from Queue import LifoQueue
import gphoto2 as gp

import os

import time
from time import sleep


import pdb

from config import CANON_EOS_6D_CAPTURE_TARGET_SD_CARD, CANON_EOS_6D_SHUTTER_SPEED_1_OVER_2500
from config import CANON_EOS_6D_IMAGEFORMAT_RAW_AND_TINY_JPEG
from config import CANON_EOS_6D_IMAGEFORMAT_RAW
from config import TRICAP_CAMS_MANAGER_STATES, DISPLAY_DOWNLOAD_DIR
from config import CAM_IMAGE_PREFIX, IMAGE_CAPTURE_INTERVAL


class TriCapCam(object):

    def __init__(self, context, port_info):
        self._context = context

        self._gp_camera = gp.Camera()

        self.serial_num = None

        self._setup_camera(port_info)

    #TODO setup from config values

    def _config_capture_target(self, config):
        # find the capture target config item
        capture_target = gp.check_result(gp.gp_widget_get_child_by_name(config, 'capturetarget'))
        # set capture target to SD CARD
        value = gp.check_result(gp.gp_widget_get_choice(capture_target,
                                                        CANON_EOS_6D_CAPTURE_TARGET_SD_CARD))
        gp.check_result(gp.gp_widget_set_value(capture_target, value))
        # set config
        gp.check_result(gp.gp_camera_set_config(self._gp_camera, config, self._context))

    def _config_image_format(self, config):
        # set camera to capture RAW + Tiny JPEG
        image_format_config = gp.check_result(gp.gp_widget_get_child_by_name(config, 'imageformat'))
        image_format = gp.check_result(gp.gp_widget_get_choice(image_format_config,
                                                               CANON_EOS_6D_IMAGEFORMAT_RAW))
        gp.check_result(gp.gp_widget_set_value(image_format_config, image_format))
        gp.check_result(gp.gp_camera_set_config(self._gp_camera, config, self._context))

    def _setup_camera(self, port_info):

        self._gp_camera.set_port_info(port_info)
        self._gp_camera.init(self._context)

        # get configuration tree
        config = gp.check_result(gp.gp_camera_get_config(self._gp_camera, self._context))

        self._config_capture_target(config)

        # set shutter speed to 1/2500
        shutter_speed_config = gp.check_result(gp.gp_widget_get_child_by_name(config, 'shutterspeed'))
        shutter_speed = gp.check_result(gp.gp_widget_get_choice(shutter_speed_config,
                                                                CANON_EOS_6D_SHUTTER_SPEED_1_OVER_2500))
        gp.check_result(gp.gp_widget_set_value(shutter_speed_config, shutter_speed))
        gp.check_result(gp.gp_camera_set_config(self._gp_camera, config, self._context))

        self._config_image_format(config)

        # get serial number
        eossernum_config = gp.check_result(gp.gp_widget_get_child_by_name(config, 'eosserialnumber'))
        eossernum = gp.check_result(gp.gp_widget_get_value(eossernum_config))
        self.serial_num = eossernum

    def create_single_capture_func(self):
        def worker(cam_num):
            # Capture an image
            file_path = gp.check_result(gp.gp_camera_capture(self._gp_camera, gp.GP_CAPTURE_IMAGE, self._context))

            # Download the jpg image
            img_name, img_ext = os.path.splitext(file_path.name)
            ret_code = -1
            # try to get the jpg, camera might still be converting
            # ret_code, camera_file = gp.gp_camera_file_get(self._gp_camera,
            #                                               file_path.folder,
            #                                               img_name+'.JPG',
            #                                               gp.GP_FILE_TYPE_NORMAL,
            #                                               self._context)
            # if ret_code == 0:
            #     download_fp = os.path.join(DISPLAY_DOWNLOAD_DIR,
            #                                CAM_IMAGE_PREFIX+str(cam_num)+'.JPG')
            #     if os.path.isfile(download_fp) is True:
            #         os.remove(download_fp)
            #
            #     gp.check_result(gp.gp_file_save(camera_file, download_fp))

            self._gp_camera.exit(self._context)

        return worker

    def create_thread_func(self):
        def capture_worker(stop_event, cam_fp_queue, cam_num):
            while not stop_event.wait(1):

                # Capture an image
                file_path = gp.check_result(gp.gp_camera_capture(self._gp_camera, gp.GP_CAPTURE_IMAGE, self._context))

                # Download the jpg image
                img_name, img_ext = os.path.splitext(file_path.name)
                ret_code = -1
                # try to get the jpg, camera might still be converting
                attempt_count = 0
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

                    gp.check_result(gp.gp_file_save(camera_file, download_fp))

                    cam_fp_queue.put((cam_num, download_fp))

                self._gp_camera.exit(self._context)

            self._gp_camera.exit(self._context)

        return capture_worker


class TriCapCamsManager(object):

    def __init__(self, cameras):
        self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

        self._cameras = cameras

        self._cam_threads = []
        self._main_thread = None

        self._kill_pill = None

        self._cam_fp_queue = LifoQueue(maxsize=0)

    def _cap_thread_generator(self):
        for index, cam in enumerate(self._cameras):
            thread = threading.Thread(target=cam.create_single_capture_func(),
                                      args=[index])
            yield thread


    def _start_capture_with_wait_thread(self):
        def worker(stop_event):
            while not stop_event.wait(0.01):
                prev_time = time.time()
                cam_threads = list(self._cap_thread_generator())
                map(threading.Thread.start, cam_threads)
                map(threading.Thread.join, cam_threads)
                current_time_diff = time.time() - prev_time
                print 'current time diff ' + str(current_time_diff)
                if current_time_diff < IMAGE_CAPTURE_INTERVAL:
                    print 'sleeping for IMAGE_CAPTURE_INTERVAL- current_time_diff'
                    time.sleep(IMAGE_CAPTURE_INTERVAL- current_time_diff)
                else:
                    print 'not sleeping, i am late!'

        self._main_thread = threading.Thread(target=worker, args=[self._kill_pill])
        self._main_thread.start()

    def start_capturing(self):
        if len(self._cameras) == 0:
            self.state = TRICAP_CAMS_MANAGER_STATES.ERROR_NO_CAMS
        elif self.state == TRICAP_CAMS_MANAGER_STATES.STOPPED:
            self._kill_pill = threading.Event()
            self._start_capture_with_wait_thread()
            # self._cam_threads = list(self._cap_thread_generator())
            # map(threading.Thread.start, self._cam_threads)
            self.state = TRICAP_CAMS_MANAGER_STATES.STARTED

    def stop_capturing(self):
        print 'stopping - cam manager'
        if self.state == TRICAP_CAMS_MANAGER_STATES.STARTED:
            self._kill_pill.set()
            # map(threading.Thread.join, self._cam_threads)
            self._main_thread.join()
            self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED

        print 'stopping - cam manager - stopped'

    def get_cam_fp_queue(self):
        return self._cam_fp_queue

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


def _get_cameras(context):
    cameras = []

    port_info_list = gp.PortInfoList()
    port_info_list.load()

    for name, addr in context.camera_autodetect():

        if name == "Canon EOS 6D":
            #TODO Replace these print statements with logging
            print 'Adding a camera'
            print name
            print addr
            idx = port_info_list.lookup_path(addr)
            tricap_cam = TriCapCam(context, port_info_list[idx])
            cameras.append(tricap_cam)

    return cameras

def create_tricap_cameras_and_manager():
    gp_context = gp.Context()
    tricap_cameras = _get_cameras(gp_context)
    tricap_manager = TriCapCamsManager(tricap_cameras)
    return tricap_cameras, tricap_manager

# class VolatileCamsManager(object):
#
#     def __init__(self):
#         self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED
#
#         self._camera_ports = []
#
#         self._cam_threads = []
#
#         self._kill_pill = None
#
#         self._context = gp.Context()
#
#         self._cam_fp_queue = LifoQueue(maxsize=0)
#
#     def _create_thread_func(self, port_info):
#
#         print port_info
#
#         def worker(stop_event, cam_fp_queue, cam_num):
#             while not stop_event.wait(1):
#                 camera = TriCapCam(self._context, port_info)
#                 # # Capture an image
#                 # file_path = gp.check_result(gp.gp_camera_capture(camera, gp.GP_CAPTURE_IMAGE, self._context))
#                 #
#                 # img_name, img_ext = os.path.splitext(file_path.name)
#                 # ret_code = -1
#                 # # try to get the jpg, camera might still be converting
#                 # attempt_count = 0
#                 # while ret_code != 0 and attempt_count < 2:
#                 #     print 'getting jpg ret code ' + str(ret_code)
#                 #     ret_code, camera_file = gp.gp_camera_file_get(camera,
#                 #                                                   file_path.folder,
#                 #                                                   img_name+'.JPG',
#                 #                                                   gp.GP_FILE_TYPE_NORMAL,
#                 #                                                   self._context)
#                 #     if ret_code != 0:
#                 #         sleep(1)
#                 #         attempt_count += 1
#                 # #
#                 # if ret_code == 0:
#                 #     download_fp = os.path.join(DISPLAY_DOWNLOAD_DIR, img_name+'.JPG')
#                 #
#                 #     gp.check_result(gp.gp_file_save(camera_file, download_fp))
#                 #
#                 #     cam_fp_queue.put((cam_num, download_fp))
#                 #
#                 #     print 'Added ' + download_fp + ' to queue'
#
#         return worker
#
#     def _cap_thread_generator(self):
#         port_info_list = gp.PortInfoList()
#         port_info_list.load()
#
#         canon_port_infos = []
#
#         for name, addr in self._context.camera_autodetect():
#
#             if name == "Canon EOS 6D":
#                 idx = port_info_list.lookup_path(addr)
#                 canon_port_infos.append(port_info_list[idx])
#
#         for index, port_info in enumerate(canon_port_infos):
#             print 'Ports Found : ' + str(port_info)
#             thread = threading.Thread(target=self._create_thread_func(port_info),
#                                       args=(self._kill_pill, self._cam_fp_queue, index))
#             yield thread
#
#     def start_capturing(self):
#         if self.state == TRICAP_CAMS_MANAGER_STATES.STOPPED:
#             self._kill_pill = threading.Event()
#
#             self._cam_threads = list(self._cap_thread_generator())
#             map(threading.Thread.start, self._cam_threads)
#             self.state = TRICAP_CAMS_MANAGER_STATES.STARTED
#
#     def stop_capturing(self):
#         if self.state == TRICAP_CAMS_MANAGER_STATES.STARTED:
#             self._kill_pill.set()
#             map(threading.Thread.join, self._cam_threads)
#             self.state = TRICAP_CAMS_MANAGER_STATES.STOPPED
#
#     def get_cam_fp_queue(self):
#         return self._cam_fp_queue
#
#     def get_num_cams(self):
#         port_info_list = gp.PortInfoList()
#         port_info_list.load()
#
#         canon_port_infos = []
#
#         count = 0
#
#         for name, addr in self._context.camera_autodetect():
#
#             if name == "Canon EOS 6D":
#                 count += 1
#
#         return count
