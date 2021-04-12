"""Dummy Camera - Helps to test the TriCap interface when no cameras are connected."""

# coding=utf-8
import os
import pickle
import threading
import time
from io import BytesIO
from collections import namedtuple
from glob import glob
from datetime import datetime
import rawpy, base64
from PIL import Image
import subprocess, hashlib

from anytree import PreOrderIter, RenderTree

from config import CAMERA_STATES, SERVER_LOG_DIR
from .abstract_cam import AbstractCamera, CameraException
from .base_setting import BaseSetting, SettingSpec

# TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
CameraSpec = namedtuple("cam", ["name", "model"])


class DummyConfig:
    """Dummy Configuration Class."""

    dictkeys = ["_tree"]

    def __init__(self, tree):
        """Construct."""
        self._tree = tree

    def __repr__(self):
        """Representation."""
        return str(RenderTree(self._tree))

    def __dir__(self):
        """Dir."""
        return [node.name for node in PreOrderIter(self.get_tree()) if node.is_leaf]

    def _get_child_by_name(self, key):
        config_widget = [widget for widget in PreOrderIter(self._tree)
                         if widget._name == key and widget.is_leaf]
        if len(config_widget) == 0:            
            raise CameraException("%s does not have an entry!" % key)
        elif len(config_widget) != 1:
            raise CameraException("%s does not uniquely identify a single item" % key)

        def set_value(value):
            config_widget[0].value = value

        set_spec = SettingSpec(choices=config_widget[0].choices,
                               set_value=set_value,
                               get_value=lambda: config_widget[0].value)
        return BaseSetting(set_spec)

    def __setattr__(self, key, value):
        """__setattr__."""
        if key in DummyConfig.dictkeys:
            self.__dict__[key] = value
        else:
            config_widget = self._get_child_by_name(key)
            config_widget.set(str(value))

    def __getattr__(self, key):
        """__getattr__."""
        return self._get_child_by_name(key)

    __setitem__ = __setattr__
    __getitem__ = __getattr__

    def get_tree(self):
        """Return the underlying tree."""
        return self._tree


# TODO Bad Coding, bad oop
def external_dummy_calibrate_func():
    """Dummy calibrate function, should be removed."""
    print('Calibrate!')


class DummyCam(AbstractCamera):
    """Serves as a fake camera for testing purposes."""

    cameras = [CameraSpec(name="Dummy Cam", model=None) for i in range(3)]

    # For easy reference, the Canon6Dmodel is shown at the end of this document

    @staticmethod
    def configure(cameras):
        """Configue."""
        DummyCam.cameras = cameras

    @staticmethod
    def autodetect():
        """Return a list of tuples that contain a camera name and a dummmy address.

        Imitates the autodetect funcionality of the gphoto2 cameras.
        """
        return [(cam.name, index) for index, cam in enumerate(DummyCam.cameras)]

    def __init__(self, address, settings=None):
        """Construct."""
        super().__init__(address, settings)
        if settings is None:
            settings = {}
        self.state = CAMERA_STATES.INITIALISED
        # TODO : Check if this camera has already been claimed and raise an exception.
        self._camera = DummyCam.cameras[address]
        cam_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '../camModels/Canon 6D - 413051000325.pkl')
        with open(cam_file, 'rb') as f:
            self._model = pickle.load(f)
        self._config = DummyConfig(self._model)
        self._fresh_capture = False
        self._address = address  # if we ever want to do anything with this later
        fnames = glob(os.path.join(os.path.dirname(__file__), '..', 'camModels', 'captureSequence', '*.jpg'))
        # TODO : raise an exception if this list does not contain at least 2 images
        self._imgs = []
        self._counter = 0
        self.data = None
        self.serial_num = 0
        for filename in fnames:
            with open(filename, 'rb') as f:
                self._imgs.append(f.read())
        self.data = self._imgs[0]
        for setting_name, setting_value in settings.items():
            self.config[setting_name] = setting_value

        self.generation_period = 1
        self._preview_images = list()
        self._im_aspect_ratio = 1.0

    @property
    def config(self):
        """Return the private config attribute."""
        return self._config
    #
    # def reset(self, settings=None):
    #     self.__init__(self._address, settings)

    def is_cam_image_fresh(self):
        """Return true if the latest camera images has not been copied yet."""
        cache = self._fresh_capture
        self._fresh_capture = False
        return cache

    def get_state_as_string(self):
        """Get the state of the camera in string format."""
        return self.state.name

    def capture_and_download(self, target_folder: str, target_name: str = None):
        """Return the filepath to an image just 'captured' and downloaded to target folder.

        User must specify the target to download to, but target_name defaults to cam index.
        """
        if target_name is None:
            target_name = str(self._address)

        target_fp = os.path.join(target_folder, target_name)

        data = self._imgs[self._counter % len(self._imgs)]

        with open(target_fp, 'wb') as im_f:
            im_f.write(data)

        return target_fp

    def capture(self, continuous=False, barrier: threading.Barrier = None, stop_event=None):
        """Start capturing photos, typically called by a thread."""
        while True:
            if stop_event:
                if stop_event.is_set():
                    return
            self.state = CAMERA_STATES.CAPTURING
            time.sleep(self.generation_period)
            if barrier:
                barrier.wait()

            self._counter += 1
            self.update_message = 'before capture'
            self.notify()
            self.data = self._imgs[self._counter % len(self._imgs)]
            self.update_message = 'before preview fetch'
            self.notify()
            if self.fetch_state is True:
                self._fresh_capture = True
            self.state = CAMERA_STATES.INITIALISED

            if self.calibrate_func is not None:
                if self.calibrate_step > 0:
                    if self._counter % self.calibrate_step == 0:
                        self.calibrate_func()

            if not continuous:
                return
            self.update_message = 'after preview fetch'
            self.notify()

    def get_cam_image_count(self):
        """Get the number of images captured so far."""
        return self._counter

    def cr2_to_jpeg(self, path):
        with rawpy.imread(path) as raw:
            self._im_aspect_ratio = raw.sizes.width / float(raw.sizes.height)
            rgb = raw.postprocess()

        im = Image.fromarray(rgb)

        bytes_io = BytesIO()
        im.save(bytes_io, format='JPEG')
        if len(bytes_io.getvalue()) < 3000000:
            # avoid memory crash on app
            self._preview_images.append(base64.b64encode(bytes_io.getvalue()).decode("utf-8"))

    def cpy_images(self):
        pass

    def delete_images(self):
        pass

    def load_preview(self, stop_event, index):
        self._generating_preview = True

        for preview_idx in range(1):
            if stop_event and stop_event.is_set():
                return
            try:
                self.cr2_to_jpeg('/home/pi/Pictures/07_24_23_000.cr2')
            except:
                pass

        self._generating_preview = False

    def get_disk_info(self):
        info = {}
        info['freeMB'] = 131072
        info['freeGB'] = 128
        info['capacityGB'] = 256
        info['usedGB'] = info['capacityGB'] - info['freeGB']
        return info

    def get_preview_images(self):
        if self._generating_preview:
            return []
        return self._preview_images

    def get_aspect_ratio(self):
        return self._im_aspect_ratio

class DummyShell():
    """Mimic the Canon6D camera shell for the purposes of testing on system without GPhoto."""

    def __init__(self, camera_driver):
        """Constructor."""
        self._camera = camera_driver
        # self.config.output = 'Undefined'  # Do not be in live mode
        self.config.drivemode = 'Single'
        self.config.reviewtime = 'None'
        self.capture = self._camera.capture
        self.capture_and_download = self._camera.capture_and_download
        self.get_state_as_string = self._camera.get_state_as_string
        self.is_cam_image_fresh = self._camera.is_cam_image_fresh
        self.cpy_images = self._camera.cpy_images
        self.delete_images = self._camera.delete_images
        self.load_preview = self._camera.load_preview
        self.get_disk_info = self._camera.get_disk_info
        self.get_preview_images = self._camera.get_preview_images
        self.get_aspect_ratio = self._camera.get_aspect_ratio

    @property
    def config(self):
        """Config property."""
        return self._camera.config

    @property
    def data(self):
        """Data property."""
        return self._camera.data

    @property
    def serial_num(self):
        """Return the serial number of the underlying camera object."""
        return self._camera.serial_num

    def get_cam_image_count(self):
        """Return the image count for the underlying camera."""
        return self._camera.get_cam_image_count()

    @property
    def state(self):
        """Return the state of the underlying camera."""
        return self._camera.state

    # Node('main', label='Camera and Driver Configuration', type=<CamConfigType.Window: 0>)
    # ├── Node('main/actions', label='Camera Actions', type=<CamConfigType.Section: 1>)
    # │   ├── Node('main/actions/uilock', choices=None, label='UI Lock', type=<CamConfigType.Toggle: 4>, value=2)
    # │   ├── Node('main/actions/syncdatetime', choices=None, label='Synchronize camera date and time with PC', type=<CamConfigType.Toggle: 4>, value=0)
    # │   ├── Node('main/actions/autofocusdrive', choices=None, label='Drive Canon DSLR Autofocus', type=<CamConfigType.Toggle: 4>, value=0)
    # │   ├── Node('main/actions/manualfocusdrive', choices=['Near 1', 'Near 2', 'Near 3', 'None', 'Far 1', 'Far 2', 'Far 3'], label='Drive Canon DSLR Manual focus', type=<CamConfigType.Radio: 5>, value='None')
    # │   ├── Node('main/actions/eoszoom', choices=None, label='Canon EOS Zoom', type=<CamConfigType.Text: 2>, value='0')
    # │   ├── Node('main/actions/eoszoomposition', choices=None, label='Canon EOS Zoom Position', type=<CamConfigType.Text: 2>, value='0,0')
    # │   ├── Node('main/actions/eosviewfinder', choices=None, label='Canon EOS Viewfinder', type=<CamConfigType.Toggle: 4>, value=2)
    # │   └── Node('main/actions/eosremoterelease', choices=['None', 'Press Half', 'Press Full', 'Release Half', 'Release Full', 'Immediate', 'Press 1', 'Press 2', 'Press 3', 'Release 1', 'Release 2', 'Release 3'], label='Canon EOS Remote Release', type=<CamConfigType.Radio: 5>, value='None')
    # ├── Node('main/settings', label='Camera Settings', type=<CamConfigType.Section: 1>)
    # │   ├── Node('main/settings/datetime', choices=None, label='Camera Date and Time', type=<CamConfigType.Date: 8>, value=1480579718)
    # │   ├── Node('main/settings/reviewtime', choices=['None', '2 seconds', '4 seconds', '8 seconds', 'Hold'], label='Quick Review Time', type=<CamConfigType.Radio: 5>, value='2 seconds')
    # │   ├── Node('main/settings/output', choices=['Undefined', 'TFT', 'PC', 'TFT + PC', 'Unknown value 0004', 'Unknown value 0005', 'Unknown value 0006', 'Unknown value 0007', 'Unknown value 0008', 'Unknown value 0009', 'Unknown value 000a', 'Unknown value 000b'], label='Camera Output', type=<CamConfigType.Radio: 5>, value='Undefined')
    # │   ├── Node('main/settings/movierecord', choices=['Unknown 0'], label='Movie Recording', type=<CamConfigType.Radio: 5>, value='Unknown 0')
    # │   ├── Node('main/settings/evfmode', choices=['1', '0'], label='EVF Mode', type=<CamConfigType.Radio: 5>, value='1')
    # │   ├── Node('main/settings/ownername', choices=None, label='Owner Name', type=<CamConfigType.Text: 2>, value='')
    # │   ├── Node('main/settings/artist', choices=None, label='Artist', type=<CamConfigType.Text: 2>, value='')
    # │   ├── Node('main/settings/copyright', choices=None, label='Copyright', type=<CamConfigType.Text: 2>, value='')
    # │   ├── Node('main/settings/customfuncex', choices=None, label='Custom Functions Ex', type=<CamConfigType.Text: 2>, value='10,c189,d1d9,0,')
    # │   ├── Node('main/settings/autopoweroff', choices=None, label='Auto Power Off', type=<CamConfigType.Text: 2>, value='0')
    # │   ├── Node('main/settings/capturetarget', choices=['Internal RAM', 'Memory card'], label='Capture Target', type=<CamConfigType.Radio: 5>, value='Memory card')
    # │   └── Node('main/settings/capture', choices=None, label='Capture', type=<CamConfigType.Toggle: 4>, value=0)
    # ├── Node('main/status', label='Camera Status Information', type=<CamConfigType.Section: 1>)
    # │   ├── Node('main/status/serialnumber', choices=None, label='Serial Number', type=<CamConfigType.Text: 2>, value='f611253f36e142dc981b9b9b29c096af')
    # │   ├── Node('main/status/manufacturer', choices=None, label='Camera Manufacturer', type=<CamConfigType.Text: 2>, value='Canon Inc.')
    # │   ├── Node('main/status/cameramodel', choices=None, label='Camera Model', type=<CamConfigType.Text: 2>, value='Canon EOS 6D')
    # │   ├── Node('main/status/deviceversion', choices=None, label='Device Version', type=<CamConfigType.Text: 2>, value='3-1.1.6')
    # │   ├── Node('main/status/vendorextension', choices=None, label='Vendor Extension', type=<CamConfigType.Text: 2>, value='None')
    # │   ├── Node('main/status/model', choices=None, label='Camera Model', type=<CamConfigType.Text: 2>, value='2147484418')
    # │   ├── Node('main/status/ptpversion', choices=None, label='PTP Version', type=<CamConfigType.Text: 2>, value='256')
    # │   ├── Node('main/status/batterylevel', choices=None, label='Battery Level', type=<CamConfigType.Text: 2>, value='50%')
    # │   ├── Node('main/status/lensname', choices=None, label='Lens Name', type=<CamConfigType.Text: 2>, value='')
    # │   ├── Node('main/status/eosserialnumber', choices=None, label='Serial Number', type=<CamConfigType.Text: 2>, value='023052000180')
    # │   ├── Node('main/status/shuttercounter', choices=None, label='Shutter Counter', type=<CamConfigType.Text: 2>, value='517')
    # │   └── Node('main/status/availableshots', choices=None, label='Available Shots', type=<CamConfigType.Text: 2>, value='290')
    # ├── Node('main/imgsettings', label='Image Settings', type=<CamConfigType.Section: 1>)
    # │   ├── Node('main/imgsettings/imageformat', choices=['Large Fine JPEG', 'Large Normal JPEG', 'Medium Fine JPEG', 'Medium Normal JPEG', 'Small Fine JPEG', 'Small Normal JPEG', 'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG', 'RAW + Large Normal JPEG', 'RAW + Medium Fine JPEG', 'RAW + Medium Normal JPEG', 'Unknown value 04d3', 'Unknown value 04d2', 'Unknown value 04e3', 'Unknown value 04f3', 'mRAW + Large Fine JPEG', 'mRAW + Large Normal JPEG', 'mRAW + Medium Fine JPEG', 'mRAW + Medium Normal JPEG', 'Unknown value 14d3', 'Unknown value 14d2', 'Unknown value 14e3', 'Unknown value 14f3', 'sRAW + Large Fine JPEG', 'sRAW + Large Normal JPEG', 'sRAW + Medium Fine JPEG', 'sRAW + Medium Normal JPEG', 'Unknown value 24d3', 'Unknown value 24d2', 'Unknown value 24e3', 'Unknown value 24f3', 'RAW', 'mRAW', 'sRAW'], label='Image Format', type=<CamConfigType.Radio: 5>, value='RAW')
    # │   ├── Node('main/imgsettings/imageformatsd', choices=['Large Fine JPEG', 'Large Normal JPEG', 'Medium Fine JPEG', 'Medium Normal JPEG', 'Small Fine JPEG', 'Small Normal JPEG', 'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG', 'RAW + Large Normal JPEG', 'RAW + Medium Fine JPEG', 'RAW + Medium Normal JPEG', 'Unknown value 04d3', 'Unknown value 04d2', 'Unknown value 04e3', 'Unknown value 04f3', 'mRAW + Large Fine JPEG', 'mRAW + Large Normal JPEG', 'mRAW + Medium Fine JPEG', 'mRAW + Medium Normal JPEG', 'Unknown value 14d3', 'Unknown value 14d2', 'Unknown value 14e3', 'Unknown value 14f3', 'sRAW + Large Fine JPEG', 'sRAW + Large Normal JPEG', 'sRAW + Medium Fine JPEG', 'sRAW + Medium Normal JPEG', 'Unknown value 24d3', 'Unknown value 24d2', 'Unknown value 24e3', 'Unknown value 24f3', 'RAW', 'mRAW', 'sRAW'], label='Image Format SD', type=<CamConfigType.Radio: 5>, value='RAW')
    # │   ├── Node('main/imgsettings/imageformatcf', choices=['Large Fine JPEG', 'Large Normal JPEG', 'Medium Fine JPEG', 'Medium Normal JPEG', 'Small Fine JPEG', 'Small Normal JPEG', 'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG', 'RAW + Large Normal JPEG', 'RAW + Medium Fine JPEG', 'RAW + Medium Normal JPEG', 'Unknown value 04d3', 'Unknown value 04d2', 'Unknown value 04e3', 'Unknown value 04f3', 'mRAW + Large Fine JPEG', 'mRAW + Large Normal JPEG', 'mRAW + Medium Fine JPEG', 'mRAW + Medium Normal JPEG', 'Unknown value 14d3', 'Unknown value 14d2', 'Unknown value 14e3', 'Unknown value 14f3', 'sRAW + Large Fine JPEG', 'sRAW + Large Normal JPEG', 'sRAW + Medium Fine JPEG', 'sRAW + Medium Normal JPEG', 'Unknown value 24d3', 'Unknown value 24d2', 'Unknown value 24e3', 'Unknown value 24f3', 'RAW', 'mRAW', 'sRAW'], label='Image Format CF', type=<CamConfigType.Radio: 5>, value='RAW')
    # │   ├── Node('main/imgsettings/iso', choices=['Auto', '100', '125', '160', '200', '250', '320', '400', '500', '640', '800', '1000', '1250', '1600', '2000', '2500', '3200', '4000', '5000', '6400', '8000', '10000', '12800', 'Unknown value 0083', 'Unknown value 0085', '25600'], label='ISO Speed', type=<CamConfigType.Radio: 5>, value='100')
    # │   ├── Node('main/imgsettings/whitebalance', choices=['Auto', 'Daylight', 'Shadow', 'Cloudy', 'Tungsten', 'Fluorescent', 'Flash', 'Manual', 'Color Temperature'], label='WhiteBalance', type=<CamConfigType.Radio: 5>, value='Auto')
    # │   ├── Node('main/imgsettings/colortemperature', choices=None, label='Color Temperature', type=<CamConfigType.Text: 2>, value='5200')
    # │   ├── Node('main/imgsettings/whitebalanceadjusta', choices=['-9', '-8', '-7', '-6', '-5', '-4', '-3', '-2', '-1', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'], label='WhiteBalance Adjust A', type=<CamConfigType.Radio: 5>, value='0')
    # │   ├── Node('main/imgsettings/whitebalanceadjustb', choices=['-9', '-8', '-7', '-6', '-5', '-4', '-3', '-2', '-1', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'], label='WhiteBalance Adjust B', type=<CamConfigType.Radio: 5>, value='0')
    # │   ├── Node('main/imgsettings/whitebalancexa', choices=None, label='WhiteBalance X A', type=<CamConfigType.Text: 2>, value='0')
    # │   ├── Node('main/imgsettings/whitebalancexb', choices=None, label='WhiteBalance X B', type=<CamConfigType.Text: 2>, value='0')
    # │   └── Node('main/imgsettings/colorspace', choices=['sRGB', 'AdobeRGB'], label='Color Space', type=<CamConfigType.Radio: 5>, value='sRGB')
    # ├── Node('main/capturesettings', label='Capture Settings', type=<CamConfigType.Section: 1>)
    # │   ├── Node('main/capturesettings/exposurecompensation', choices=['-5', '-4.6', 'Unknown value 00dd', '-4', '-3.6', '-3.3', '-3', '-2.6', '-2.3', '-2', '-1.6', '-1.3', '-1.0', '-0.6', '-0.3', '0', '0.3', '0.6', '1.0', '1.3', '1.6', '2', '2.3', '2.6', '3', '3.3', '3.6', '4', '4.3', '4.6', '5'], label='Exposure Compensation', type=<CamConfigType.Radio: 5>, value='0')
    # │   ├── Node('main/capturesettings/focusmode', choices=['Manual'], label='Focus Mode', type=<CamConfigType.Radio: 5>, value='Manual')
    # │   ├── Node('main/capturesettings/autoexposuremode', choices=['P', 'TV', 'AV', 'Manual', 'Bulb', 'A_DEP', 'DEP', 'Custom', 'Lock', 'Green', 'Night Portrait', 'Sports', 'Portrait', 'Landscape', 'Closeup', 'Flash Off'], label='Canon Auto Exposure Mode', type=<CamConfigType.Radio: 5>, value='TV')
    # │   ├── Node('main/capturesettings/drivemode', choices=['Single', 'Continuous', 'Single silent', 'Continuous silent', 'Timer 2 sec', 'Timer 10 sec'], label='Drive Mode', type=<CamConfigType.Radio: 5>, value='Single')
    # │   ├── Node('main/capturesettings/picturestyle', choices=['Unknown value 0087', 'Standard', 'Portrait', 'Landscape', 'Neutral', 'Faithful', 'Monochrome', 'User defined 1', 'User defined 2', 'User defined 3', 'Unknown value 0087'], label='Picture Style', type=<CamConfigType.Radio: 5>, value='Unknown value 0087')
    # │   ├── Node('main/capturesettings/shutterspeed', choices=['30', '25', '20', '15', '13', '10', '8', '6', '5', '4', '3.2', '2.5', '2', '1.6', '1.3', '1', '0.8', '0.6', '0.5', '0.4', '0.3', '1/4', '1/5', '1/6', '1/8', '1/10', '1/13', '1/15', '1/20', '1/25', '1/30', '1/40', '1/50', '1/60', '1/80', '1/100', '1/125', '1/160', '1/200', '1/250', '1/320', '1/400', '1/500', '1/640', '1/800', '1/1000', '1/1250', '1/1600', '1/2000', '1/2500', '1/3200', '1/4000'], label='Shutter Speed', type=<CamConfigType.Radio: 5>, value='1/2500')
    # │   ├── Node('main/capturesettings/meteringmode', choices=['Evaluative', 'Partial', 'Spot', 'Center-weighted average'], label='Metering Mode', type=<CamConfigType.Radio: 5>, value='Evaluative')
    # │   ├── Node('main/capturesettings/bracketmode', choices=None, label='Bracket Mode', type=<CamConfigType.Text: 2>, value='0')
    # │   └── Node('main/capturesettings/aeb', choices=['off', '+/- 1/3', '+/- 2/3', '+/- 1', '+/- 1 1/3', '+/- 1 2/3', '+/- 2', '+/- 2 1/3', '+/- 2 2/3', '+/- 3'], label='Auto Exposure Bracketing', type=<CamConfigType.Radio: 5>, value='off')
    # └── Node('main/other', label='Other PTP Device Properties', type=<CamConfigType.Section: 1>)
    #     ├── Node('main/other/d049', choices=None, label='Model ID', type=<CamConfigType.Text: 2>, value='-2147482878')
    #     ├── Node('main/other/d402', choices=None, label='PTP Property 0xd402', type=<CamConfigType.Text: 2>, value='Canon EOS 6D')
    #     ├── Node('main/other/d407', choices=None, label='PTP Property 0xd407', type=<CamConfigType.Text: 2>, value='1')
    #     ├── Node('main/other/d406', choices=None, label='PTP Property 0xd406', type=<CamConfigType.Text: 2>, value='Unknown Initiator')
    #     ├── Node('main/other/d303', choices=None, label='PTP Property 0xd303', type=<CamConfigType.Text: 2>, value='1')
    #     └── Node('main/other/5001', choices=None, label='Battery Level', type=<CamConfigType.Menu: 6>, value='50')
