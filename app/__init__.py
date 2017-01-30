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

from support.session_logger import SessionLogger
from support.configure import TricapConfig
from support.talkbox import TalkBox
from support.log_list import LogListAccessor

from support.network_monitor import generate_net_monitor, NetworkMonitorLogger

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
image_manager = tricap_manager

session_logger = SessionLogger()

alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)

if init_config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) == 'dummy':
    altimeter = DummyAlti(alti_settings, session_logger)
else:
    altimeter = TrusenseAltimeter(alti_settings)
    alti_observer = AltiMeasurementObserver(session_logger)
    altimeter.attach(alti_observer)

talkbox = TalkBox(Lock(), 3)
talkbox.clear()

# Setup the network monitors and loggers
net_mon = generate_net_monitor(period=60)
net_mon_logger = NetworkMonitorLogger(net_mon)
net_mon.start()


def stop_all_threads():
    """Helper function for a clean exit."""
    net_mon.stop()
    tricap_manager.stop_capturing()
    altimeter.stop_measuring()


# Configure the Flask Blueprints
from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp

app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
