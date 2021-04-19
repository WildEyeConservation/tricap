"""Camera driver for a generic camera that can be accessed using the libgphoto2
library."""

import os
import logging
import threading
from io import BytesIO
import pyexifinfo
import tempfile
import numpy as np
import rawpy, base64
from PIL import Image

from time import sleep
from datetime import datetime

import gphoto2 as gp
from anytree import Node, PreOrderIter, RenderTree

from config import CAMERA_STATES
from .abstract_cam import AbstractCamera, CamConfigType
from .base_setting import BaseSetting

import subprocess, hashlib, json

# Max attempts that can be made to trigger a photo during the capture process
MAX_TRIGGER_ATTEMPTS = 5
IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH = 10
IMAGE_COUNT_DELTA_FOR_FETCH = 5

PREVIEW_FROM_CR2 = False

class GPhotoSetting(BaseSetting):
    """Setting handler for gphoto cameras."""

    def __init__(self, widget):
        """Constructor."""
        widget.name = widget.get_name()
        super().__init__(widget)

    @property
    def choices(self):
        """Access the choices for a widget as a list."""
        try:
            return [self._widget.get_choice(i) for i in range(self._widget.count_choices())]
        except gp.GPhoto2Error:
            return None


class GPhotoConfig:
    """Configuration handler for gphoto cameras."""

    dictkeys = ["_camera", "_context"]

    def __init__(self, camera, context):
        """Constructor."""
        self._camera = camera
        self._context = context

    def __repr__(self):
        """Represent the configuration settings as a tree."""
        return str(RenderTree(self.get_tree()))

    def __dir__(self):
        """dir."""
        return [node.name for node in PreOrderIter(self.get_tree()) if node.is_leaf]

    def __setattr__(self, key, value):
        """Set a configuration setting to a new value."""
        if key in GPhotoConfig.dictkeys:
            self.__dict__[key] = value
        else:
            config = self._camera.get_config(self._context)
            GPhotoSetting(config.get_child_by_name(key)).set(value)
            self._camera.set_config(config, self._context)

    def __getattr__(self, key):
        """Get a configuration setting from the camera."""
        return GPhotoSetting(self._camera.get_config(self._context).get_child_by_name(key))

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    @staticmethod
    def _get_config(node, parent=None):
        children = [node.get_child(i) for i in range(node.count_children())]
        if len(children):
            thisnode = Node(node.get_name(), parent=parent, label=node.get_label(),
                            type=CamConfigType(node.get_type()))
            for child in children:
                GPhotoConfig._get_config(child, thisnode)
            return thisnode
        else:
            if node.get_type() == CamConfigType.Radio:
                choices = [node.get_choice(i) for i in range(node.count_choices())]
            else:
                choices = None
            return Node(node.get_name(), parent=parent, label=node.get_label(), type=CamConfigType(node.get_type()),
                        value=node.get_value(), choices=choices)

    def get_tree(self):
        """Return the configuration tree."""
        config = self._camera.get_config(self._context)
        return GPhotoConfig._get_config(config)


# noinspection PyUnresolvedReferences
class GPhotoCam(AbstractCamera):
    """Handler for a generic gphoto2 based cameras. Uses this library to handle communication."""

    _port_info_list = gp.PortInfoList()
    _port_info_list.load()
    _context = gp.Context()
    _logger = logging.getLogger(__name__)

    def __init__(self, address, settings: dict):
        """Constructor, requires address and camera settings dict."""
        super().__init__(address, settings)

        self._gp_camera = None
        self.data = None
        self._fresh_capture = False
        self.state = CAMERA_STATES.INITIALISED
        self._address = address

        self._image_count = 0

        self.calibrate_step = 0

        self._image_path = None
        self._old_image_count = 0
        self._images_to_delete = list()
        self._preview_images = list()
        self._exif_info = {}
        self._im_aspect_ratio = 1.0
        self._generating_preview = False
        self._num_images_to_copy = 0
        self._num_images_copied = 0
        self._prev_im_timestamp = None
        self._session_idx = 0

        self._setup_camera(settings)

    def is_cam_image_fresh(self):
        """Check if the camera image is new."""
        return self._fresh_capture

    @staticmethod
    def autodetect():
        """Run gphoto2 camera autodetection."""
        return GPhotoCam._context.camera_autodetect()

    def _setup_camera(self, settings):
        # In case this is a re-setup. Make sure our previous gp_camera handle gets destroyed.
        if self._gp_camera:
            del self._gp_camera
        self._gp_camera = gp.Camera()
        port_info = GPhotoCam._port_info_list[GPhotoCam._port_info_list.lookup_path(self._address)]
        self._gp_camera.set_port_info(port_info)
        self._gp_camera.init(GPhotoCam._context)
        # Do not catch exceptions here. Camera init is mission critical. If camera initialisation fails, we want top
        # level code to know about it.
        for key, value in settings.items():
            self.config[key] = value
        self.state = CAMERA_STATES.INITIALISED

    @property
    def config(self):
        """Return a GPhotoConfig object for the camera."""
        return GPhotoConfig(self._gp_camera, self._context)

    def _fetch_preview_camera_file(self, file_path: str):
        camera_file = None
        try:
            camera_file = self._gp_camera.file_get(file_path.folder,
                                                   file_path.name,
                                                   gp.GP_FILE_TYPE_PREVIEW,
                                                   GPhotoCam._context)
        except gp.GPhoto2Error:
            self._logger.error('Error retrieving preview, is the capturetarget correctly set?')
            raise

        return camera_file

    def get_current_folder(self):
        """Get the latest folder from the camera."""
        folder = '/'
        done_flag = False
        while done_flag is False:
            cam_folders = self._gp_camera.folder_list_folders(folder, self._context)
            if len(cam_folders) == 0:
                done_flag = True
            else:
                target_folder = cam_folders[-1][0]
                if cam_folders[-1][0] == 'MISC':
                    target_folder = cam_folders[-2][0]
                folder += target_folder + '/'
                for name, value in cam_folders:
                    print(name)

        return folder

    def calibrate_func(self):
        print('running the calibration function.')
        # get the latest folder and file
        # folder = self.get_current_folder()
        # print(folder)
        # cam_files = self._gp_camera.folder_list_files('/', self._context)
        # cam_files = self._gp_camera.folder_list_files(folder, self._context)
        # print(cam_files)
        # print(len(cam_files))
        # fname = cam_files[-1][0]
        # print(fname)

        # capturing image
        MAX_FOCUS_ATTEMPTS = 3
        focus_flag = False
        focus_attempts = 0
        while focus_flag is False and focus_attempts < MAX_FOCUS_ATTEMPTS: 
            trigger_attempts = 0
            cam_fp = None
            done_flag = False
            while trigger_attempts < MAX_TRIGGER_ATTEMPTS and done_flag is False:
                try:
                    cam_fp = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
                    done_flag = True
                except gp.GPhoto2Error as ex:
                    self._logger.warning('Exception when trying to trigger a capture: %s', ex)
                    trigger_attempts += 1
                    sleep(1)

            if done_flag is False:
                print("could not successfully capture.")                
                self._logger.error('Calibration: could not autofocus.')
                return -1

            print("successfully captured.")

            # get the exif data from that file
            buf = bytearray(128*1024)
            self._gp_camera.file_read(cam_fp.folder, cam_fp.name, 
                                      gp.GP_FILE_TYPE_NORMAL, 0, 
                                      buf, GPhotoCam._context)
            tfile = tempfile.NamedTemporaryFile('wb', delete=True)
            tfile.write(buf)
            exif_data = pyexifinfo.get_json(tfile.name)[0]

            print(exif_data['MakerNotes:FocusDistanceLower'])
            fdl = float(exif_data['MakerNotes:FocusDistanceLower'][:-2])
            if fdl != 11.9:
                print('not in focus')
                focus_attempts += 1
            else:
                print('focussed')
                focus_flag = True

        if focus_flag is False:
            print("impossible to focus")
            
            self._logger.error('Calibration: could not autofocus.')
        else:
            self._logger.info('Calibration: focus a success.')



        # react to it, i.e. use autofocus to correct?


    def _update_image(self, camera_file):
        file_data = camera_file.get_data_and_size()
        # Make a copy, so that we can release the file_data object
        self.data = memoryview(file_data).tobytes()
        self._fresh_capture = True

    def _run_calibrate_if_needed(self):
        if self.calibrate_func is not None:
            if self.calibrate_step > 0:
                print(self._image_count)
                if self._image_count == 1 or self._image_count % self.calibrate_step == 0:
                    self.calibrate_func()

    def _wait_for_image_path(self, before_capture_ts=None):
        image_path = None

        event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
        count = 0

        if before_capture_ts is None:
            while event[0] != gp.GP_EVENT_FILE_ADDED and count < 1000:
                sleep(0.01)
                event = self._gp_camera.wait_for_event(100, GPhotoCam._context)
                count += 1
        else:
            while event[0] != gp.GP_EVENT_FILE_ADDED and (datetime.now() - before_capture_ts).total_seconds() < 1.2:
                sleep(0.01)
                event = self._gp_camera.wait_for_event(100, GPhotoCam._context)

        if event[0] == gp.GP_EVENT_FILE_ADDED:
            image_path = event[1]

        return image_path

    def capture_and_download(self, target_folder: str, target_name: str = None):
        """Capture an image and download it."""
        file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
        camera_file = self._gp_camera.file_get(file_path.folder,
                                               file_path.name,
                                               gp.GP_FILE_TYPE_NORMAL,
                                               GPhotoCam._context)
        if target_name is None:
            target_name = file_path.name

        target_fp = os.path.join(target_folder, target_name)

        gp.gp_file_save(camera_file, target_fp)

        return target_fp

    def cam_trigger(self):
        """Trigger using either normal function or the eos remote release."""
        if self.calibrate_step > 0: 
            # full press (bypass focus)
            config = self._gp_camera.get_config(GPhotoCam._context)
            GPhotoSetting(config.get_child_by_name('eosremoterelease')).set('Press Full')
            self._gp_camera.set_config(config, GPhotoCam._context)

            # release full press
            config = self._gp_camera.get_config(GPhotoCam._context)
            GPhotoSetting(config.get_child_by_name('eosremoterelease')).set('Release Full')
            self._gp_camera.set_config(config, GPhotoCam._context)
        else:
            self._gp_camera.trigger_capture(GPhotoCam._context)

    def _trigger_capture(self):
        """Make the camera capture an image but don't wait for it to return.

        If a gphoto2 exception is triggered, try up to MAX_TRIGGER_ATTEMPTS again.

        Return True if successful, or False if too many exceptions were caused.
        """

        trigger_attempts = 0
        while trigger_attempts < MAX_TRIGGER_ATTEMPTS:
            try:
                # file_path = self._gp_camera.capture(gp.GP_CAPTURE_IMAGE, GPhotoCam._context)
                # self._gp_camera.trigger_capture(GPhotoCam._context)
                self.cam_trigger()
                return True
            except gp.GPhoto2Error as ex:
                self._logger.warning('Exception when trying to trigger a capture: %s', ex)
                trigger_attempts += 1

        self._logger.warning('Trigger failed')
        return False

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        """Start capturing photos, typically called by a thread."""
        self.state = CAMERA_STATES.INITIALISED
        while True:
            if stop_event and stop_event.is_set():
                return

            disk_info = self.get_disk_info()
            if "freeMB" in disk_info:
                space_available = disk_info['freeMB'] > 45
            else:
                space_available = False

            if barrier:
                barrier.wait()

            self.update_message = 'before capture'
            self.notify()
            before_capture_ts = datetime.now()

            if space_available and self._trigger_capture():  # Checks to see if something went wrong with the cameras
                self._image_count += 1
                self.state = CAMERA_STATES.CAPTURING
            else:
                self._logger.error('Could not successfully trigger a capture.')
                self.state = CAMERA_STATES.ERROR_CAPTURE

            if self.fetch_state:
                # check if we need to get a new image path
                if self._image_path is None or self._image_count - self._old_image_count >= IMAGE_COUNT_DELTA_FOR_WAIT_FOR_PATH:
                    self._image_path = self._wait_for_image_path(before_capture_ts)
                    if self._image_path:
                        self._old_image_count = self._image_count

                self.update_message = 'before preview fetch'
                self.notify()

                # check if we need to fetch the image from the camera
                camera_file = None
                if self._image_path and self._image_count - self._old_image_count == IMAGE_COUNT_DELTA_FOR_FETCH:
                    camera_file = self._fetch_preview_camera_file(self._image_path)

                self.update_message = 'after preview fetch'
                self.notify()

                if camera_file:
                    self._update_image(camera_file)
                    del camera_file
            else:
                # update the timing info
                self.update_message = 'before preview fetch'
                self.notify()
                self.update_message = 'after preview fetch'
                self.notify()

            self._run_calibrate_if_needed()

            if not continuous:
                return self.data

    # def reset(self, settings: dict):
    #     """Reset the camera."""
    #     self.state = CAMERA_STATES.UNINITIALISED
    #     self._setup_camera(settings)

    def get_state_as_string(self):
        """Return the state of the camera as a string."""
        return self.state.name

    def get_cam_image_count(self):
        """Return the number of images captured by the camera, as tracked by this object."""
        return self._image_count

    def get_cam_context(self):
        return GPhotoCam._context

    def get_cam(self):
        return self._gp_camera

    def get_disk_info(self):
        # start_get_storageinfo = datetime.now()
        # sifs = self._gp_camera.get_storageinfo(GPhotoCam._context)
        # print('get_storageinfo delay={:.2f}ms'.format((datetime.now()-start_get_storageinfo).total_seconds()*1000))
        # approximately 2.7ms to get storage info
        info = {}
        try:
            sifs = self._gp_camera.get_storageinfo(GPhotoCam._context)[0]
            info['freeMB'] = round(sifs.freekbytes / 1024, 2)
            info['freeGB'] = round(sifs.freekbytes / 1048576, 2)
            info['capacityGB'] = round(sifs.capacitykbytes / 1048576, 2)
            info['usedGB'] = round(info['capacityGB'] - info['freeGB'], 2)
        except IndexError as ex:
            self._logger.warning('Exception: no storage info: %s', ex)
            pass
        except AttributeError:
            self._logger.warning('Exception: invalid storage info: %s', ex)
            pass

        return info

    def get_session_dir(self, timestamp, session_idx):
        return "{}/{}".format(timestamp.strftime('%Y_%m_%d'), session_idx)

    def get_complete_session_dir(self, mount_point, session_dir):
        return os.path.join(mount_point, session_dir, str(self.config.eosserialnumber))

    def find_session_dir(self, mount_point, timestamp, session_idx):
        i = session_idx
        session_dir = self.get_session_dir(timestamp, i)
        complete_dir = self.get_complete_session_dir(mount_point, session_dir)
        while os.path.exists(complete_dir):
            i += 1
            session_dir = self.get_session_dir(timestamp, i)
            complete_dir = self.get_complete_session_dir(mount_point, session_dir)
        return session_dir, complete_dir, i

    def get_im_target_dir(self, timestamp, mount_point):
        session_dir = self.get_session_dir(timestamp, self._session_idx)
        complete_dir = self.get_complete_session_dir(mount_point, session_dir)
        if self._prev_im_timestamp == None:
            # first save after reboot -> always start new session idx
            session_dir, complete_dir, self._session_idx = self.find_session_dir(mount_point, timestamp, self._session_idx)
        elif (timestamp - self._prev_im_timestamp).total_seconds() > 120:
            # x seconds passed between captures -> save as new capture session
            session_dir, complete_dir, self._session_idx = self.find_session_dir(mount_point, timestamp, self._session_idx)
        if not self._prev_im_timestamp == None:
            self._logger.debug('Seconds diff {}'.format((timestamp - self._prev_im_timestamp).total_seconds()))
        self._prev_im_timestamp = timestamp
        return complete_dir

    def list_camera_files(self, path='/'):
        result = []
        # get files
        gp_list = self._gp_camera.folder_list_files(path, GPhotoCam._context)
        for name, value in gp_list:
            result.append(os.path.join(path, name))
        # read folders
        folders = []
        gp_list = self._gp_camera.folder_list_folders(path, GPhotoCam._context)
        for name, value in gp_list:
            folders.append(name)
        # recurse over subfolders
        for name in folders:
            result.extend(self.list_camera_files(os.path.join(path, name)))
        return result

    def get_camera_file_info(self, path):
        folder, name = os.path.split(path)
        return self._gp_camera.file_get_info(folder, name, GPhotoCam._context)

    def refresh_camera(self):
        self._gp_camera.exit()
        sleep(500e-3)
        self._gp_camera.init(GPhotoCam._context)

    def append_exif_info(self, cam_file, name, dest_dir):
        file_data = cam_file.get_data_and_size()
        tfile = tempfile.NamedTemporaryFile('wb', delete=True)
        data_bytes = memoryview(file_data).tobytes()
        tfile.write(data_bytes)
        exif_data = pyexifinfo.get_json(tfile.name)[0]
        filtered_exif = {}
        KEYS_TO_SAVE = ('Composite:SubSecDateTimeOriginal','EXIF:ExifImageHeight','EXIF:ExifImageWidth','Composite:GPSAltitude','EXIF:GPSDateStamp','Composite:GPSLatitude','Composite:GPSLongitude','EXIF:GPSTimeStamp','EXIF:ISO', 'EXIF:ShutterSpeedValue','MakerNotes:FocusMode','MakerNotes:Quality')
        if 'EXIF:SerialNumber' not in exif_data:
            return
        for key in KEYS_TO_SAVE:
            if key in exif_data:
                formatted_key = key[key.index(':')+1:]
                filtered_exif[formatted_key] = exif_data[key]

        # do not save temporary filename
        filtered_exif['FileName'] = name
        filtered_exif['FileDir'] = dest_dir
        filtered_exif['md5'] = hashlib.md5(data_bytes).hexdigest() # 170ms for MD5 calc

        if dest_dir not in self._exif_info:
            self._exif_info[dest_dir] = []
        self._exif_info[dest_dir].append(filtered_exif)

    def save_exif_info(self):
        # Save exif info
        for exif_dir in self._exif_info:
            filename = os.path.join(exif_dir, 'exif_cam.json')
            if not os.path.exists(filename):
                # no existing file
                self._logger.debug('no existing file')
                new_data = {}
                new_data['serialNumber'] = str(self.config.eosserialnumber)
                new_data['exifInfo'] = self._exif_info[exif_dir]

                # find session index from dest_dir
                dir_split = exif_dir.split('/')
                new_data['sessionId'] = dir_split[-3] + "#" + dir_split[-2] # date (YYYY_MM_DD) + session idx
                
                with open(filename, 'w') as f:
                    json.dump(new_data, f, sort_keys=True)
            else:
                # existing file
                self._logger.debug('existing file')
                exisiting_data = {}
                with open(filename, 'r') as f:
                    exisiting_data = json.load(f)
                exisiting_data['exifInfo'].append(self._exif_info[exif_dir])
                with open(filename, 'w') as f:
                    json.dump(exisiting_data, f, sort_keys=True)   

    def cpy_images(self, computer_files, mount_point, stop_event, pause_event):
        self._num_images_copied = 0
        self._num_images_to_copy = 0
        sleep(500e-3)
        self.refresh_camera()
        camera_files = self.list_camera_files()
        self._num_images_to_copy = len(camera_files)
        paused = False
        if not camera_files:
            self._logger.debug('No files found')
            self._gp_camera.exit()
            return

        self._logger.debug('Copying %d files to %s' % (len(camera_files), mount_point))
        for path in camera_files:
            while pause_event and pause_event.is_set():
                # wait for all threads to pause before flushing external drive
                if not paused:
                    self._logger.debug("Paused")
                paused = True
                sleep(500e-3)

            if stop_event and stop_event.is_set():
                self._gp_camera.exit()
                return

            if paused:
                # external drive has been flushed -> delete from SD card
                paused = False
                self.delete_images()

            info = self.get_camera_file_info(path)
            timestamp = datetime.fromtimestamp(info.file.mtime)
            folder, name = os.path.split(path)
            dest_dir = self.get_im_target_dir(timestamp, mount_point)
            dest = os.path.join(dest_dir, name)
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir)

            if any(x[0] == folder and x[1] == name for x in self._images_to_delete):
                # file already copied and waiting to be deleted from SD card
                continue
            
            while dest in computer_files:
                # file exists -> add in /copy/
                dest = "{0}_{2}.{1}".format(*dest.rsplit(".", 1), "copy")
            
            self._logger.debug('%s -> %s' % (path, dest))
            camera_file = self._gp_camera.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL, GPhotoCam._context)
            try:
                gp.check_result(gp.gp_file_save(camera_file, dest))
                self._images_to_delete.append((folder, name, dest))
                self.append_exif_info(camera_file, name, dest_dir)
                self._num_images_copied += 1
            except:
                self._logger.warning("Save exception %s %s -> %s" % (folder, name, dest))

        self._gp_camera.exit()
        self._logger.debug('Copy thread completed.')

    def get_camera_image_hash(self, folder, name):
        h = "cam"
        for i in range(3):
            try:
                camera_file = self._gp_camera.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL, GPhotoCam._context)
                h = hashlib.sha256(memoryview(camera_file.get_data_and_size())).hexdigest()
                return h
            except:
                self._logger.warning("Failed to get %s %s hash" % (folder, name))
                sleep(1)
        return h

    def get_external_image_hash(self, path):
        h = "ext"
        for i in range(3):
            try:
                f = open(path, "rb")
                h = hashlib.sha256(f.read()).hexdigest()
                f.close()
                return h
            except:
                self._logger.warning("Failed to get %s hash" % (path))
                sleep(1)
        return h

    def delete_images(self):
        # verify first and last file hash
        if len(self._images_to_delete) > 0:
            self._logger.debug("Delete {} files".format(len(self._images_to_delete)))
            folder, name, dest = self._images_to_delete[0]
            folderLast, nameLast, destLast = self._images_to_delete[-1]

            if (self.get_camera_image_hash(folder, name) == self.get_external_image_hash(dest) and
                self.get_camera_image_hash(folderLast, nameLast) == self.get_external_image_hash(destLast)):
                # first and last image hash match -> delete copied files from SD card
                self.save_exif_info()
                for folder, name, _  in self._images_to_delete:
                    try:
                        # self._logger.debug("Delete %s %s" % (folder, name))
                        self._gp_camera.file_delete(folder, name, GPhotoCam._context)
                    except:
                        self._logger.warning("Delete exception for folder: %s, name: %s" % (folder, name))
            else:
                self._logger.warning("Hash mismatch")
            self._logger.debug("Delete done")
            self._images_to_delete = list()
            self._exif_info = {}

    def cr2_to_jpeg(self, path):
        with rawpy.imread(path) as raw:
            self._im_aspect_ratio = raw.sizes.width / float(raw.sizes.height)
            rgb = raw.postprocess()

        im = Image.fromarray(rgb)

        bytes_io = BytesIO()
        im.save(bytes_io, format='JPEG')
        if len(bytes_io.getvalue()) < 5000000:
            # avoid memory crash on app
            self._preview_images.append(base64.b64encode(bytes_io.getvalue()).decode("utf-8"))
        self._logger.debug(len(bytes_io.getvalue()))

    def load_preview(self, stop_event, index):
        self._generating_preview = True
        sleep(2)

        self.refresh_camera()
        camera_files = self.list_camera_files()
        if not camera_files:
            self._logger.debug('No files found')
            self._gp_camera.exit()
            return

        im_preview_idxs = list()
        im_preview_idxs.append((len(camera_files)-1) // 10)
        im_preview_idxs.append((len(camera_files)-1) // 2)
        im_preview_idxs.append(((9*len(camera_files)-1)) // 10)

        self._preview_images = list()
        for preview_idx in im_preview_idxs:
            if stop_event and stop_event.is_set():
                self._gp_camera.exit()
                return

            try:
                folder, name = os.path.split(camera_files[preview_idx])
                if PREVIEW_FROM_CR2:
                    camera_file = self._gp_camera.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL , GPhotoCam._context)
                    file_data = camera_file.get_data_and_size()
                    data = memoryview(file_data).tobytes()
                    with open('/tmp/im{}.cr2'.format(index), 'wb') as f:
                        f.write(memoryview(file_data).tobytes())

                    self.cr2_to_jpeg('/tmp/im{}.cr2'.format(index))
                else:
                    camera_file = self._gp_camera.file_get(folder, name, gp.GP_FILE_TYPE_PREVIEW , GPhotoCam._context)
                    file_data = camera_file.get_data_and_size()
                    data = memoryview(file_data).tobytes()
                    self._preview_images.append(base64.b64encode(data).decode("utf-8"))
            except:
                self._logger.debug('get_image failed')

        self._generating_preview = False

    def get_preview_images(self):
        if self._generating_preview:
            return []
        return self._preview_images

    def get_aspect_ratio(self):
        return self._im_aspect_ratio

    def get_copy_info(self):
        if self._num_images_to_copy == 0:
            # invalid
            return 0

        return round(self._num_images_copied / self._num_images_to_copy, 2)