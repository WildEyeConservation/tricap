# coding=utf-8
import time
from collections import namedtuple

from config import RET_ERROR, RET_OK, CAMERA_STATES, DUMMY_IMAGE_PATH

# TODO Implement a Windows Canon6DCam, which uses the Canon EDSDK to communicate with the camera
# TODO Have the DummyCam load variables from the config file, like the normal camera would
CameraSpec = namedtuple("cam", ["name", "serial_number"])


class DummyCam(object):
    """ Serves as a fake camera for testing purposes."""

    cameras = [CameraSpec(name="Dummy Cam", serial_number=i) for i in range(3)]

    Canon6Dmodel = {'capturesettings': {'exposurecompensation': {'type': 5,
                                                                 'choices': ['-5', '-4.6', 'Unknown value 00dd', '-4',
                                                                             '-3.6', '-3.3',
                                                                             '-3', '-2.6', '-2.3', '-2', '-1.6', '-1.3',
                                                                             '-1.0',
                                                                             '-0.6', '-0.3', '0', '0.3', '0.6', '1.0',
                                                                             '1.3', '1.6',
                                                                             '2', '2.3', '2.6', '3', '3.3', '3.6', '4',
                                                                             '4.3', '4.6',
                                                                             '5'], 'value': '0',
                                                                 'label': 'Exposure Compensation'},
                                        'autoexposuremode': {'type': 5,
                                                             'choices': ['P', 'TV', 'AV', 'Manual', 'Bulb', 'A_DEP',
                                                                         'DEP', 'Custom',
                                                                         'Lock', 'Green', 'Night Portrait', 'Sports',
                                                                         'Portrait',
                                                                         'Landscape', 'Closeup', 'Flash Off'],
                                                             'value': 'TV',
                                                             'label': 'Canon Auto Exposure Mode'},
                                        'bracketmode': {'type': 2, 'choices': None, 'value': '0',
                                                        'label': 'Bracket Mode'},
                                        'picturestyle': {'type': 5,
                                                         'choices': ['Unknown value 0087', 'Standard', 'Portrait',
                                                                     'Landscape',
                                                                     'Neutral', 'Faithful', 'Monochrome',
                                                                     'User defined 1',
                                                                     'User defined 2', 'User defined 3',
                                                                     'Unknown value 0087'],
                                                         'value': 'Unknown value 0087', 'label': 'Picture Style'},
                                        'meteringmode': {'type': 5,
                                                         'choices': ['Evaluative', 'Partial', 'Spot',
                                                                     'Center-weighted average'],
                                                         'value': 'Evaluative', 'label': 'Metering Mode'},
                                        'aeb': {'type': 5,
                                                'choices': ['off',
                                                            '+/- 1/3',
                                                            '+/- 2/3',
                                                            '+/- 1',
                                                            '+/- 1 1/3',
                                                            '+/- 1 2/3',
                                                            '+/- 2',
                                                            '+/- 2 1/3',
                                                            '+/- 2 2/3',
                                                            '+/- 3'],
                                                'value': 'off',
                                                'label': 'Auto Exposure Bracketing'},
                                        'focusmode': {'type': 5, 'choices': ['Manual'], 'value': 'Manual',
                                                      'label': 'Focus Mode'},
                                        'shutterspeed': {'type': 5,
                                                         'choices': ['30', '25', '20', '15', '13', '10', '8', '6', '5',
                                                                     '4', '3.2',
                                                                     '2.5', '2', '1.6', '1.3', '1', '0.8', '0.6', '0.5',
                                                                     '0.4', '0.3',
                                                                     '1/4', '1/5', '1/6', '1/8', '1/10', '1/13', '1/15',
                                                                     '1/20',
                                                                     '1/25', '1/30', '1/40', '1/50', '1/60', '1/80',
                                                                     '1/100', '1/125',
                                                                     '1/160', '1/200', '1/250', '1/320', '1/400',
                                                                     '1/500', '1/640',
                                                                     '1/800', '1/1000', '1/1250', '1/1600', '1/2000',
                                                                     '1/2500',
                                                                     '1/3200', '1/4000'], 'value': '1/2500',
                                                         'label': 'Shutter Speed'},
                                        'drivemode': {'type': 5,
                                                      'choices': ['Single', 'Continuous', 'Single silent',
                                                                  'Continuous silent',
                                                                  'Timer 2 sec', 'Timer 10 sec'], 'value': 'Single',
                                                      'label': 'Drive Mode'}}, 'actions': {
        'manualfocusdrive': {'type': 5, 'choices': ['Near 1', 'Near 2', 'Near 3', 'None', 'Far 1', 'Far 2', 'Far 3'],
                             'value': 'None', 'label': 'Drive Canon DSLR Manual focus'},
        'eosviewfinder': {'type': 4, 'choices': None, 'value': 2, 'label': 'Canon EOS Viewfinder'},
        'autofocusdrive': {'type': 4, 'choices': None, 'value': 0, 'label': 'Drive Canon DSLR Autofocus'},
        'uilock': {'type': 4, 'choices': None, 'value': 2, 'label': 'UI Lock'},
        'eoszoom': {'type': 2, 'choices': None, 'value': '0', 'label': 'Canon EOS Zoom'},
        'eosremoterelease': {'type': 5, 'choices': ['None', 'Press Half', 'Press Full', 'Release Half', 'Release Full',
                                                    'Immediate', 'Press 1', 'Press 2', 'Press 3', 'Release 1',
                                                    'Release 2', 'Release 3'], 'value': 'None',
                             'label': 'Canon EOS Remote Release'},
        'syncdatetime': {'type': 4, 'choices': None, 'value': 0, 'label': 'Synchronize camera date and time with PC'},
        'eoszoomposition': {'type': 2, 'choices': None, 'value': '0,0', 'label': 'Canon EOS Zoom Position'}},
                    'other': {'5001': {'type': 6, 'choices': None, 'value': '50', 'label': 'Battery Level'},
                              'd406': {'type': 2, 'choices': None, 'value': 'Unknown Initiator',
                                       'label': 'PTP Property 0xd406'},
                              'd303': {'type': 2, 'choices': None, 'value': '1', 'label': 'PTP Property 0xd303'},
                              'd402': {'type': 2, 'choices': None, 'value': 'Canon EOS 6D',
                                       'label': 'PTP Property 0xd402'},
                              'd049': {'type': 2, 'choices': None, 'value': '-2147482878', 'label': 'Model ID'},
                              'd407': {'type': 2, 'choices': None, 'value': '1', 'label': 'PTP Property 0xd407'}},
                    'status': {'manufacturer': {'type': 2, 'choices': None, 'value': 'Canon Inc.',
                                                'label': 'Camera Manufacturer'},
                               'lensname': {'type': 2, 'choices': None, 'value': '', 'label': 'Lens Name'},
                               'batterylevel': {'type': 2, 'choices': None, 'value': '50%', 'label': 'Battery Level'},
                               'deviceversion': {'type': 2, 'choices': None, 'value': '3-1.1.6',
                                                 'label': 'Device Version'},
                               'shuttercounter': {'type': 2, 'choices': None, 'value': '517',
                                                  'label': 'Shutter Counter'},
                               'ptpversion': {'type': 2, 'choices': None, 'value': '256', 'label': 'PTP Version'},
                               'cameramodel': {'type': 2, 'choices': None, 'value': 'Canon EOS 6D',
                                               'label': 'Camera Model'},
                               'model': {'type': 2, 'choices': None, 'value': '2147484418', 'label': 'Camera Model'},
                               'availableshots': {'type': 2, 'choices': None, 'value': '292',
                                                  'label': 'Available Shots'},
                               'vendorextension': {'type': 2, 'choices': None, 'value': 'None',
                                                   'label': 'Vendor Extension'},
                               'eosserialnumber': {'type': 2, 'choices': None, 'value': '023052000180',
                                                   'label': 'Serial Number'},
                               'serialnumber': {'type': 2, 'choices': None, 'value': 'f611253f36e142dc981b9b9b29c096af',
                                                'label': 'Serial Number'}}, 'settings': {
            'reviewtime': {'type': 5, 'choices': ['None', '2 seconds', '4 seconds', '8 seconds', 'Hold'],
                           'value': '2 seconds', 'label': 'Quick Review Time'},
            'autopoweroff': {'type': 2, 'choices': None, 'value': '0', 'label': 'Auto Power Off'},
            'customfuncex': {'type': 2, 'choices': None, 'value': '10,c189,d1d9,0,', 'label': 'Custom Functions Ex'},
            'capturetarget': {'type': 5, 'choices': ['Internal RAM', 'Memory card'], 'value': 'Memory card',
                              'label': 'Capture Target'},
            'ownername': {'type': 2, 'choices': None, 'value': '', 'label': 'Owner Name'},
            'capture': {'type': 4, 'choices': None, 'value': 0, 'label': 'Capture'},
            'datetime': {'type': 8, 'choices': None, 'value': 1480523822, 'label': 'Camera Date and Time'},
            'evfmode': {'type': 5, 'choices': ['1', '0'], 'value': '1', 'label': 'EVF Mode'}, 'output': {'type': 5,
                                                                                                         'choices': [
                                                                                                             'Undefined',
                                                                                                             'TFT',
                                                                                                             'PC',
                                                                                                             'TFT + PC',
                                                                                                             'Unknown value 0004',
                                                                                                             'Unknown value 0005',
                                                                                                             'Unknown value 0006',
                                                                                                             'Unknown value 0007',
                                                                                                             'Unknown value 0008',
                                                                                                             'Unknown value 0009',
                                                                                                             'Unknown value 000a',
                                                                                                             'Unknown value 000b'],
                                                                                                         'value': 'Undefined',
                                                                                                         'label': 'Camera Output'},
            'copyright': {'type': 2, 'choices': None, 'value': '', 'label': 'Copyright'},
            'artist': {'type': 2, 'choices': None, 'value': '', 'label': 'Artist'},
            'movierecord': {'type': 5, 'choices': ['Unknown 0'], 'value': 'Unknown 0', 'label': 'Movie Recording'}},
                    'imgsettings': {'imageformatsd': {'type': 5,
                                                      'choices': ['Large Fine JPEG', 'Large Normal JPEG',
                                                                  'Medium Fine JPEG',
                                                                  'Medium Normal JPEG', 'Small Fine JPEG',
                                                                  'Small Normal JPEG',
                                                                  'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG',
                                                                  'RAW + Large Normal JPEG', 'RAW + Medium Fine JPEG',
                                                                  'RAW + Medium Normal JPEG', 'Unknown value 04d3',
                                                                  'Unknown value 04d2', 'Unknown value 04e3',
                                                                  'Unknown value 04f3',
                                                                  'mRAW + Large Fine JPEG', 'mRAW + Large Normal JPEG',
                                                                  'mRAW + Medium Fine JPEG',
                                                                  'mRAW + Medium Normal JPEG',
                                                                  'Unknown value 14d3', 'Unknown value 14d2',
                                                                  'Unknown value 14e3',
                                                                  'Unknown value 14f3', 'sRAW + Large Fine JPEG',
                                                                  'sRAW + Large Normal JPEG', 'sRAW + Medium Fine JPEG',
                                                                  'sRAW + Medium Normal JPEG', 'Unknown value 24d3',
                                                                  'Unknown value 24d2', 'Unknown value 24e3',
                                                                  'Unknown value 24f3',
                                                                  'RAW', 'mRAW', 'sRAW'], 'value': 'RAW',
                                                      'label': 'Image Format SD'},
                                    'imageformatcf': {'type': 5,
                                                      'choices': ['Large Fine JPEG', 'Large Normal JPEG',
                                                                  'Medium Fine JPEG',
                                                                  'Medium Normal JPEG', 'Small Fine JPEG',
                                                                  'Small Normal JPEG',
                                                                  'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG',
                                                                  'RAW + Large Normal JPEG', 'RAW + Medium Fine JPEG',
                                                                  'RAW + Medium Normal JPEG', 'Unknown value 04d3',
                                                                  'Unknown value 04d2', 'Unknown value 04e3',
                                                                  'Unknown value 04f3',
                                                                  'mRAW + Large Fine JPEG', 'mRAW + Large Normal JPEG',
                                                                  'mRAW + Medium Fine JPEG',
                                                                  'mRAW + Medium Normal JPEG',
                                                                  'Unknown value 14d3', 'Unknown value 14d2',
                                                                  'Unknown value 14e3',
                                                                  'Unknown value 14f3', 'sRAW + Large Fine JPEG',
                                                                  'sRAW + Large Normal JPEG', 'sRAW + Medium Fine JPEG',
                                                                  'sRAW + Medium Normal JPEG', 'Unknown value 24d3',
                                                                  'Unknown value 24d2', 'Unknown value 24e3',
                                                                  'Unknown value 24f3',
                                                                  'RAW', 'mRAW', 'sRAW'], 'value': 'RAW',
                                                      'label': 'Image Format CF'},
                                    'whitebalanceadjusta': {'type': 5,
                                                            'choices': ['-9', '-8', '-7', '-6', '-5', '-4', '-3', '-2',
                                                                        '-1', '0', '1',
                                                                        '2', '3', '4', '5', '6', '7', '8', '9'],
                                                            'value': '0',
                                                            'label': 'WhiteBalance Adjust A'},
                                    'imageformat': {'type': 5, 'choices': [
                                        'Large Fine JPEG', 'Large Normal JPEG', 'Medium Fine JPEG',
                                        'Medium Normal JPEG', 'Small Fine JPEG',
                                        'Small Normal JPEG', 'Smaller JPEG', 'Tiny JPEG', 'RAW + Large Fine JPEG',
                                        'RAW + Large Normal JPEG',
                                        'RAW + Medium Fine JPEG', 'RAW + Medium Normal JPEG', 'Unknown value 04d3',
                                        'Unknown value 04d2',
                                        'Unknown value 04e3', 'Unknown value 04f3', 'mRAW + Large Fine JPEG',
                                        'mRAW + Large Normal JPEG',
                                        'mRAW + Medium Fine JPEG', 'mRAW + Medium Normal JPEG', 'Unknown value 14d3',
                                        'Unknown value 14d2',
                                        'Unknown value 14e3', 'Unknown value 14f3', 'sRAW + Large Fine JPEG',
                                        'sRAW + Large Normal JPEG',
                                        'sRAW + Medium Fine JPEG', 'sRAW + Medium Normal JPEG', 'Unknown value 24d3',
                                        'Unknown value 24d2',
                                        'Unknown value 24e3', 'Unknown value 24f3', 'RAW', 'mRAW', 'sRAW'],
                                                    'value': 'RAW',
                                                    'label': 'Image Format'},
                                    'colortemperature': {'type': 2, 'choices': None, 'value': '5200',
                                                         'label': 'Color Temperature'},
                                    'whitebalanceadjustb': {'type': 5,
                                                            'choices': ['-9', '-8', '-7', '-6', '-5', '-4', '-3', '-2',
                                                                        '-1', '0', '1',
                                                                        '2', '3', '4', '5', '6', '7', '8', '9'],
                                                            'value': '0',
                                                            'label': 'WhiteBalance Adjust B'}, 'iso': {'type': 5,
                                                                                                       'choices': [
                                                                                                           'Auto',
                                                                                                           '100',
                                                                                                           '125', '160',
                                                                                                           '200',
                                                                                                           '250', '320',
                                                                                                           '400',
                                                                                                           '500', '640',
                                                                                                           '800',
                                                                                                           '1000',
                                                                                                           '1250',
                                                                                                           '1600',
                                                                                                           '2000',
                                                                                                           '2500',
                                                                                                           '3200',
                                                                                                           '4000',
                                                                                                           '5000',
                                                                                                           '6400',
                                                                                                           '8000',
                                                                                                           '10000',
                                                                                                           '12800',
                                                                                                           'Unknown value 0083',
                                                                                                           'Unknown value 0085',
                                                                                                           '25600'],
                                                                                                       'value': '100',
                                                                                                       'label': 'ISO Speed'},
                                    'whitebalancexb': {'type': 2, 'choices': None, 'value': '0',
                                                       'label': 'WhiteBalance X B'},
                                    'whitebalancexa': {'type': 2, 'choices': None, 'value': '0',
                                                       'label': 'WhiteBalance X A'},
                                    'whitebalance': {'type': 5,
                                                     'choices': ['Auto', 'Daylight', 'Shadow', 'Cloudy', 'Tungsten',
                                                                 'Fluorescent',
                                                                 'Flash', 'Manual', 'Color Temperature'],
                                                     'value': 'Auto',
                                                     'label': 'WhiteBalance'},
                                    'colorspace': {'type': 5, 'choices': ['sRGB', 'AdobeRGB'], 'value': 'sRGB',
                                                   'label': 'Color Space'}}}

    @staticmethod
    def configure(cameras):
        DummyCam.cameras = cameras

    @staticmethod
    def autodetect():
        return [(cam.name, index) for index, cam in enumerate(DummyCam.cameras)]

    def __init__(self, address, settings):
        self.state = CAMERA_STATES.INITIALISED
        self.serial_num = DummyCam.cameras[address].serial_number
        self._fresh_capture = False
        self._address = address  # if we ever want to do anything with this later
        self._settings_dict = settings
        for setting_name, setting_value in settings:
            self._set_config_value_by_string(setting_name, setting_value)

    def reset(self):
        self.state = CAMERA_STATES.INITIALISED

    def is_cam_image_fresh(self):
        return self._fresh_capture

    def get_cam_image_fp(self):
        self._fresh_capture = False
        return DUMMY_IMAGE_PATH

    @staticmethod
    def get_state_as_string():
        return "Base Cam has no state."

    def set_setting(self, setting_str, setting_val):
        self._settings_dict[setting_str] = setting_val
        return RET_OK

    def get_setting(self, setting_str):
        if setting_str in self._settings_dict.keys():
            return self._settings_dict[setting_str]
        else:
            return None

    @staticmethod
    def get_choices_for_setting(setting_str):
        # just a couple of hard coded ones
        if setting_str == 'shutterspeed':
            return ['1/4', '1/640', '1/2500']
        elif setting_str == 'iso':
            return ['100', '200', '500']
        else:
            return None

    def capture(self):
        if self.state == CAMERA_STATES.INITIALISED:
            self.state = CAMERA_STATES.CAPTURING
            # prepare the small jpeg filename
            time.sleep(1)
            self._fresh_capture = True
            self.state = CAMERA_STATES.INITIALISED
            return RET_OK
        else:
            return RET_ERROR
