"""The initial script run on accessing the flask app the first time.

Lots of instantiation going on here, not recommended to run this unnecessarily when unit testing.
"""

import logging
import os

from threading import Lock
from logging.handlers import TimedRotatingFileHandler

from flask import Flask

from sensors.cam_manager import TriCapCamsManager
from sensors.trusense_altimeter import TrusenseAltimeter
from sensors.dummy_alti import DummyAlti
from sensors.camera_logger import cameraLoggingObserver

from support.session_logger import SessionLogger
from support.configure import TricapConfig
from support.talkbox import TalkBox
from support.log_list import LogListAccessor

from support.connection_monitor import generate_net_monitor, NetworkMonitorLogger
from support.connection_monitor import generate_ip_monitor, IPMonitorLogger

from support.system_monitor import generate_system_monitor, SystemMonitorLogger

from config import SERVER_LOG_DIR


class AltiMeasurementObserver():
    """A custom observer to link the alti to the session logger."""

    def __init__(self, session_logger):
        """Construct."""
        self.session_logger = session_logger

    def update(self, alti):
        """Update."""
        self.session_logger.log('Alti Measurement: %f' % alti.measurement)


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
rootlogger.info('Initiating new instance of TriCap app.')

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
app.logger.info('Initiated flask logger for new instance of TriCap app.')

# Instantiate the system log message tracker
log_list = LogListAccessor(3)

# Instantiate the sensors
init_config = TricapConfig()
misc_settings = init_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
cam_settings = init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)

if init_config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) == 'dummy':
    use_dummy_cams = True
else:
    use_dummy_cams = False

tricap_manager = TriCapCamsManager(misc_settings, cam_settings, use_dummy_cams)
tricap_cameras = tricap_manager.get_cameras_as_list()
camera_loggers = []
for index, cam in enumerate(tricap_cameras):
    if use_dummy_cams is True:
        cam_log_fp = os.path.join(SERVER_LOG_DIR, 'dummycam_%d_rates.txt' % index)
    else:
        filename = 'gphotocam_%s_rate.txt' % cam._camera._address.replace(':', '_').replace(',', '_')
        cam_log_fp = os.path.join(SERVER_LOG_DIR, filename)

    camera_loggers.append(cameraLoggingObserver(log_fp=cam_log_fp, subject_cameras=cam._camera))

image_manager = tricap_manager

alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)

if init_config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) == 'dummy':
    altimeter = DummyAlti(alti_settings)
else:
    altimeter = TrusenseAltimeter(alti_settings)

talkbox = TalkBox(Lock(), 3)
talkbox.clear()

# Setup monitor and logger for wireless network connection
wlan_mon = generate_net_monitor(period=26)
net_mon_logger = NetworkMonitorLogger(wlan_mon)
wlan_mon.start()

# Setup monitor and logger for vpn and internet connection
vpn_mon = generate_ip_monitor('192.168.88.1', period=27)
internet_mon = generate_ip_monitor('8.8.8.8', period=32)
ip_mon_logger = IPMonitorLogger([vpn_mon, internet_mon])
vpn_mon.start()
internet_mon.start()

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
log_names_to_track = [rootlogger.name, app.logger.name]
log_names_to_track += [cam_log._logger.name for cam_log in camera_loggers]
session_logger = SessionLogger(log_names_to_track=log_names_to_track)
alti_observer = AltiMeasurementObserver(session_logger)
altimeter.attach(alti_observer)


def stop_all_threads():
    """Helper function for a clean exit."""
    wlan_mon.stop()
    vpn_mon.stop()
    internet_mon.stop()

    for sm in sys_mons:
        if sm is not None:
            sm.stop()

    tricap_manager.stop_capturing()
    altimeter.stop_measuring()


# Configure the Flask Blueprints
from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp

app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
