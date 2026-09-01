"""The initial script run on accessing the flask app the first time.

Lots of instantiation going on here, not recommended to run this unnecessarily when unit testing.
"""

import logging
import os

from threading import Lock, Timer
from logging.handlers import TimedRotatingFileHandler

from flask import Flask

from sensors.cam_manager import TriCapCamsManager
from sensors.trusense_altimeter import TrusenseAltimeter
from sensors.unavailable_altimeter import UnavailableAltimeter
#from sensors.dummy_alti import DummyAlti
from sensors.alti_simulator import SimulatorAlti
from sensors.camera_logger import cameraLoggingObserver
from support.session_logger import SessionLogger
from sensors.altitude_switch import AltiSwitch
from support.configure import TricapConfig
from support.talkbox import TalkBox
from support.log_list import LogListAccessor
from support.basic import TimeMonitor, PeriodicMonitor
from support.sms_sender import SMSObserver
from support.git_info import GitData
from support import flight_log

from sensors.toggle_switch import ToggleSwitchObserver, ToggleSwitchMonitor
from sensors.toggle_switch import CamManagerMonitor, LEDController, CamErrorMonitor, CamCaptureMonitor

# from support.connection_monitor import generate_net_monitor, NetworkMonitorLogger
# from support.connection_monitor import generate_ip_monitor, IPMonitorLogger

from support.system_monitor import generate_system_monitor, SystemMonitorLogger

from config import SERVER_LOG_DIR, ALTIMETER_STATE
from enum import Enum

from serial_comms.SerialInterface import SerialInterface
from serial_comms.berryIMU import BerryImu

class AltiMeasurementObserver():
    """A custom observer to link the alti to the session logger."""

    def __init__(self, session_logger):
        """Construct."""
        self.session_logger = session_logger

    def update(self, alti):
        """Update."""
        if alti.measurement is not None:
            self.session_logger.log('Alti Measurement: %f' % alti.measurement)


class AltitudeLogObserver():
    """Log available altitude readings beside the GPS data."""
    _logger = logging.getLogger(__name__)

    def update(self, alti):
        legacy_strength = getattr(alti, 'strength', 0)
        first_return = getattr(alti, 'first_return', alti.measurement)
        last_return = getattr(alti, 'last_return', alti.measurement)
        first_strength = getattr(alti, 'first_strength', legacy_strength)
        last_strength = getattr(alti, 'last_strength', legacy_strength)
        # Publish the last return for the live flight log even when it is None,
        # so a lost target clears the value rather than leaving a stale reading.
        flight_log.record_laser_altitude(last_return)
        if first_return is None and last_return is None:
            return
        try:
            from datetime import datetime
            from config import MOUNT_POINT
            now = datetime.now()
            day = now.strftime('%Y_%m_%d')
            if os.path.ismount(MOUNT_POINT):
                log_dir = os.path.join(MOUNT_POINT, day)
            else:
                log_dir = os.path.join('/home/radxa/GPS_IMU_Data', day)
            if not os.path.isdir(log_dir):
                os.makedirs(log_dir)
            dest = os.path.join(log_dir, 'altitudeData.csv')
            new_file = not os.path.exists(dest)
            with open(dest, 'ta') as f:
                if new_file:
                    f.write('pi_timestamp,altitude_m,strength_db,'
                            'first_return_m,last_return_m,'
                            'first_strength_db,last_strength_db\n')
                values = (
                    now.timestamp(),
                    last_return,
                    last_strength,
                    first_return,
                    last_return,
                    first_strength,
                    last_strength,
                )
                f.write(','.join('' if value is None else str(value)
                                 for value in values) + '\n')
        except Exception as e:
            self._logger.debug(f"altitude log failed: {e}")


class AltitudeMonitor(PeriodicMonitor):
    """Monitor how high the altitude is."""

    def __init__(self, period: float, alti):
        """Constructor."""
        super(AltitudeMonitor, self).__init__(period)

        self.alti = alti

        self.type_id = 'Altitude'
        self.value = 0
        self.unit = 'm'

    def monitor_step(self):
        """Update the value."""
        self.value = self.alti.value


class CamImgNumMonitor(PeriodicMonitor):
    """Monitor how many images a camera has taken."""

    def __init__(self, period: float, cam):
        """Constructor."""
        super(CamImgNumMonitor, self).__init__(period)

        self.cam = cam

        self.type_id = 'Images'
        self.value = 0
        self.unit = 'ims'

    def monitor_step(self):
        """Update the value with the current time as a string."""
        self.value = 0
        for cam in self.cam:
            self.value = self.value + cam.get_cam_image_count()


# TODO Bad metaphor
class GateCloser():
    """Manages a timer, which if triggered will run a piece of code, unless kept open."""

    def __init__(self, delay: float, close_function):
        """Construct."""
        """Delay - time to wait until the close_function action is called."""
        self.delay = delay
        self.close_function = close_function

        self.timer = None

        self.start_timer()

    def __del__(self):
        """Deconstructor."""
        if self.timer:
            self.timer.cancel()
            self.timer.join()

    def start_timer(self):
        """Create the timer and start it."""
        self.timer = Timer(self.delay, self.close_function)
        self.timer.daemon = True
        self.timer.start()

    def keep_open(self):
        """Keep the gate open, or open it."""
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
        self.start_timer()


# Set up rotating log file for the overall log
format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
formatter = logging.Formatter(format_str)
master_log_fp = os.path.join(SERVER_LOG_DIR, 'tricap_master.log')
master_handler = TimedRotatingFileHandler(filename=master_log_fp, when='midnight', backupCount=10)
master_handler.setLevel(logging.DEBUG)
master_handler.setFormatter(formatter)
rootlogger = logging.getLogger('')
rootlogger.addHandler(master_handler)
rootlogger.setLevel(logging.DEBUG)
rootlogger.info('Initiating new instance of the TriCap app.')

# Setup the Flask Server, configuring it using the config.py file
app = Flask(__name__)
app.config.from_object('config')

# Setup a rotating log file for the HTTP requests (and whatever flask does)
# werkzeug messages always come from the same function, log, using a different formatter for clarity
wz_formatter = logging.Formatter("%(asctime)s | %(funcName)s | %(levelname)s | %(message)s ")
flask_log_fp = os.path.join(SERVER_LOG_DIR, 'tricap_flask.log')
flask_handler = TimedRotatingFileHandler(filename=flask_log_fp, when='midnight', backupCount=10)
flask_handler.setLevel(logging.DEBUG)
flask_handler.setFormatter(wz_formatter)

wz_log = logging.getLogger('werkzeug')
wz_log.propagate = False
wz_log.addHandler(flask_handler)

app.logger.addHandler(flask_handler)
app.logger.setLevel(logging.DEBUG)
app.logger.info('Initiated flask logger for new instance of the TriCap app.')

# Instantiate the system log message tracker
log_list = LogListAccessor(3)

# Instantiate the config setting management
init_config = TricapConfig()
misc_settings = init_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
cam_settings = init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)

# Instantiate the sensors
if init_config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) == 'dummy':
    use_dummy_cams = True
    rootlogger.debug('Dummy cams will be used, in accordance to configuration.')
else:
    use_dummy_cams = False
    rootlogger.debug('Real cams will be used, in accordance to configuration')
    code_inf = GitData()

# TODO ALKMAAR Get from config
use_gpio_cams = False
use_sony_cam = True

imu_lock = Lock()

tricap_manager = TriCapCamsManager(misc_settings, cam_settings, use_dummy_cams, imu_lock, use_gpio_cams, use_sony_cam)
tricap_cameras = tricap_manager.get_cameras_as_list()
tricap_length = len(tricap_cameras)
camera_loggers = []

gps_ser = SerialInterface('/dev/gps', 921600, False, False, imu_lock, tricap_manager)
accel_ser = BerryImu(imu_lock)

for index, cam in enumerate(tricap_cameras):
    if use_dummy_cams is True:
        cam_log_fp = os.path.join(SERVER_LOG_DIR, 'dummycam_%d_rates.txt' % index)
    else:
        # filename = 'gphotocam_%s_rate.txt' % cam._camera._address.replace(':', '_').replace(',', '_')
        filename = 'canon6dcam_%s_rate.txt' % cam.serial_num
        cam_log_fp = os.path.join(SERVER_LOG_DIR, filename)

    camera_loggers.append(cameraLoggingObserver(log_fp=cam_log_fp, subject_cameras=cam._camera))

image_manager = tricap_manager

rootlogger.debug('Cameras have been configured.')

alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
web_settings = init_config.get_section_dict(TricapConfig.WEB_SECTION_HEADER)

alti_choice_str = init_config.get('alti_required', TricapConfig.WEB_SECTION_HEADER)
try:
    if alti_choice_str == 'dummy':
        rootlogger.debug('Using a dummy altimeter.')
        altimeter = SimulatorAlti(alti_settings)  # DummyAlti(alti_settings)
    elif alti_choice_str == 'grf500':
        rootlogger.debug('Using a GRF-500 altimeter.')
        from sensors.grf500_altimeter import Grf500Altimeter
        altimeter = Grf500Altimeter(alti_settings)
    else:
        rootlogger.debug('Using a real altimeter.')
        altimeter = TrusenseAltimeter(alti_settings)
    altimeter.available = True
except Exception as exc:
    rootlogger.warning(
        'Configured altimeter %s is unavailable; continuing without altitude data: %s',
        alti_choice_str, exc, exc_info=True)
    altimeter = UnavailableAltimeter(alti_choice_str, exc)

# altimeter_switch = AltiSwitch(altimeter, cam_manager=tricap_manager)
# altimeter.attach(altimeter_switch)

# if altimeter.state != ALTIMETER_STATE.MEASURING:
#     altimeter.start_measuring()

rootlogger.debug('Altimeter has been configured.')

talkbox = TalkBox(Lock(), 3)
talkbox.clear()

# Setup monitor and logger for wireless network connection
# wlan_mon = generate_net_monitor(period=26)
# net_mon_logger = NetworkMonitorLogger(wlan_mon)
# wlan_mon.start()

# Setup monitor and logger for vpn and internet connection
# vpn_mon = generate_ip_monitor('192.168.88.1', period=27)
# internet_mon = generate_ip_monitor('8.8.8.8', period=32)
# ip_mon_logger = IPMonitorLogger([vpn_mon, internet_mon])
# vpn_mon.start()
# internet_mon.start()

# Setup monitors for system values
sys_mons = []
sys_mons.append(generate_system_monitor(period=28, type_id='RAM'))
sys_mons.append(generate_system_monitor(period=29, type_id='CPU'))
sys_mons.append(generate_system_monitor(period=30, type_id='Disk'))
sys_mons.append(generate_system_monitor(period=31, type_id='IO'))
sys_mon_logger = SystemMonitorLogger(sys_mons)
for sm in sys_mons:
    if sm is not None:
        sm.start()

# setup the session logger, hook it up to the alti and all the other logs
log_names_to_track = [rootlogger.name, app.logger.name, wz_log.name]
log_names_to_track += [cam_log._logger.name for cam_log in camera_loggers]
session_logger = SessionLogger(log_names_to_track=log_names_to_track)
alti_observer = AltiMeasurementObserver(session_logger)
altimeter.attach(alti_observer)
altimeter.attach(AltitudeLogObserver())

# Capture controls measurement when an altimeter is present. The unavailable
# placeholder implements the same no-op interface, so capture remains usable.
tricap_manager.altimeter = altimeter

# setup a time monitor and the sms sender
time_mon = TimeMonitor(5*60)  # will emit the time every 5 minutes as primary observer
cam_img_num_mon = CamImgNumMonitor(5*59, tricap_cameras) # will update just before time_mon
# alti_mon = AltitudeMonitor(5*59, altimeter)
# sms_observer = SMSObserver(time_mon, [cam_img_num_mon, alti_mon], send_on_start=True)
cam_img_num_mon.start()
# alti_mon.start()
time_mon.start()

if use_dummy_cams == False:
    rootlogger.info("Git version: " + code_inf.code_id())
else:
    rootlogger.info("Git version: " + "DummyGit1234")

if not use_gpio_cams:
    # Toggle switch
    toggle_switch_monitor = ToggleSwitchMonitor(period=0.3)
    toggle_switch_observer = ToggleSwitchObserver(tricap_manager, session_logger, toggle_switch_monitor)
    toggle_switch_monitor.start()

    # LED Lights
    cam_man_state_monitor = CamManagerMonitor(tricap_manager, period=0.5)
    cam_error_monitors = []
    cam_capture_monitors = []
    for idx, cam in enumerate(tricap_cameras):
        cem = CamErrorMonitor(cam, idx)
        cem.start()
        cam_error_monitors.append(cem)

    for idx, cam in enumerate(tricap_cameras):
        ccm = CamCaptureMonitor(cam, idx)
        ccm.start()
        cam_capture_monitors.append(ccm)

    led_controller = LEDController(cam_man_state_monitor, cam_error_monitors, cam_capture_monitors)
    cam_man_state_monitor.start()

# some glue functions, which use the module level functions

def stop_fetching():
    """Turn off fetching for all cameras."""
    for cam in tricap_manager.get_cameras_as_list():
        if not use_sony_cam:
            cam._camera.fetch_state = False  # add pass for testing

if not use_gpio_cams:
    fetch_stopper = GateCloser(20.0, stop_fetching)


def stop_all_threads():
    """Helper function for a clean exit."""
    # wlan_mon.stop()
    # vpn_mon.stop()
    # internet_mon.stop()

    for sm in sys_mons:
        if sm is not None:
            sm.stop()

    tricap_manager.stop_capturing()
    altimeter.stop_measuring()


# Configure the Flask Blueprints
# from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp
from .views.camera import camera_bp
from .views.api import api_bp

# app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(camera_bp)
app.register_blueprint(api_bp)

rootlogger.info('New instance of TriCap app has been initiated.')
