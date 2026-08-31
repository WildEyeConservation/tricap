"""The initial script run on accessing the flask app the first time.

Lots of instantiation going on here, not recommended to run this unnecessarily when unit testing.
"""

import logging
import os

from threading import Lock
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, request

from sensors.cam_manager import TriCapCamsManager
from sensors.grf500_altimeter import Grf500Altimeter
from sensors.unavailable_altimeter import UnavailableAltimeter
from support.session_logger import SessionLogger
from support.configure import TricapConfig
from support.git_info import GitData

from sensors.toggle_switch import ToggleSwitchObserver, ToggleSwitchMonitor
from sensors.toggle_switch import CamManagerMonitor, LEDController, CamErrorMonitor, CamCaptureMonitor

from support.system_monitor import generate_system_monitor, SystemMonitorLogger

from config import FALLBACK_TELEMETRY_DIR, MOUNT_POINT, SERVER_LOG_DIR
from enum import Enum

from serial_comms.SerialInterface import SerialInterface

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
        if first_return is None and last_return is None:
            return
        try:
            from datetime import datetime
            now = datetime.now()
            day = now.strftime('%Y_%m_%d')
            if os.path.ismount(MOUNT_POINT):
                log_dir = os.path.join(MOUNT_POINT, day)
            else:
                log_dir = os.path.join(FALLBACK_TELEMETRY_DIR, day)
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


@app.after_request
def set_http_headers(response):
    response.headers['Permissions-Policy'] = 'geolocation=()'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith(('/api/', '/portal/')):
        response.headers['Cache-Control'] = 'no-store'
    return response

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

# Instantiate the config setting management
init_config = TricapConfig()
misc_settings = init_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
cam_settings = init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)

code_inf = GitData()

storage_lock = Lock()

tricap_manager = TriCapCamsManager(misc_settings, cam_settings, storage_lock)
tricap_cameras = tricap_manager.get_cameras_as_list()
tricap_length = len(tricap_cameras)

gps_ser = SerialInterface(
    '/dev/gps',
    921600,
    capturing_lock=storage_lock,
    cam_manager=tricap_manager,
)

image_manager = tricap_manager

rootlogger.debug('Cameras have been configured.')

alti_settings = init_config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER)
web_settings = init_config.get_section_dict(TricapConfig.WEB_SECTION_HEADER)

try:
    rootlogger.debug('Connecting to the GRF-500 altimeter.')
    altimeter = Grf500Altimeter(alti_settings)
    altimeter.available = True
    altimeter.configured_type = 'grf500'
except Exception as exc:
    rootlogger.warning(
        'GRF-500 altimeter is unavailable; continuing without altitude data: %s',
        exc,
        exc_info=True,
    )
    altimeter = UnavailableAltimeter('grf500', exc)

rootlogger.debug('Altimeter has been configured.')

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
session_logger = SessionLogger(log_names_to_track=log_names_to_track)
alti_observer = AltiMeasurementObserver(session_logger)
altimeter.attach(alti_observer)
altimeter.attach(AltitudeLogObserver())

# Capture controls measurement when an altimeter is present. The unavailable
# placeholder implements the same no-op interface, so capture remains usable.
tricap_manager.altimeter = altimeter

rootlogger.info("Git version: " + code_inf.code_id())

toggle_switch_monitor = ToggleSwitchMonitor(period=0.3)
toggle_switch_observer = ToggleSwitchObserver(
    tricap_manager,
    session_logger,
    toggle_switch_monitor,
)
toggle_switch_monitor.start()

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

led_controller = LEDController(
    cam_man_state_monitor,
    cam_error_monitors,
    cam_capture_monitors,
)
cam_man_state_monitor.start()


def stop_all_threads():
    """Helper function for a clean exit."""
    for sm in sys_mons:
        if sm is not None:
            sm.stop()

    tricap_manager.stop_capturing()
    altimeter.stop_measuring()


# Configure the Flask Blueprints
from .views.portal import portal_bp
from .views.api import api_bp

app.register_blueprint(portal_bp)
app.register_blueprint(api_bp)

rootlogger.info('New instance of TriCap app has been initiated.')
