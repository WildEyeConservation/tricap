"""The initial script run on accessing the flask app the first time.

Lots of instantiation going on here, not recommended to run this unnecessarily when unit testing.
"""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from threading import Lock

from flask import Flask, abort, request

from config import FALLBACK_TELEMETRY_DIR, MOUNT_POINT, SERVER_LOG_DIR
from sensors.cam_manager import TriCapCamsManager
from sensors.grf500_altimeter import Grf500Altimeter
from sensors.unavailable_altimeter import UnavailableAltimeter
from serial_comms.SerialInterface import SerialInterface
from support import flight_log, system_clock
from support.configure import TricapConfig
from support.git_info import GitData
from support.local_network import web_client_allowed


class AltitudeLogObserver:
    """Log available altitude readings beside the GPS data."""

    _logger = logging.getLogger(__name__)

    def update(self, alti):
        first_return = alti.first_return
        last_return = alti.last_return
        first_strength = alti.first_strength
        last_strength = alti.last_strength
        # Published even when None so a lost target clears the flight-log value
        # rather than leaving a stale reading on later GPS rows.
        flight_log.record_laser_altitude(last_return)
        if first_return is None and last_return is None:
            return
        try:
            now = datetime.now()
            day = now.strftime("%Y_%m_%d")
            if os.path.ismount(MOUNT_POINT):
                log_dir = os.path.join(MOUNT_POINT, day)
            else:
                log_dir = os.path.join(FALLBACK_TELEMETRY_DIR, day)
            if not os.path.isdir(log_dir):
                os.makedirs(log_dir)
            dest = os.path.join(log_dir, "altitudeData.csv")
            new_file = not os.path.exists(dest)
            with open(dest, "a") as f:
                if new_file:
                    f.write(
                        "pi_timestamp,altitude_m,strength_db,"
                        "first_return_m,last_return_m,"
                        "first_strength_db,last_strength_db\n"
                    )
                values = (
                    now.timestamp(),
                    last_return,
                    last_strength,
                    first_return,
                    last_return,
                    first_strength,
                    last_strength,
                )
                f.write(",".join("" if value is None else str(value) for value in values) + "\n")
        except Exception as e:
            self._logger.debug(f"altitude log failed: {e}")


# Set up rotating log file for the overall log
format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
formatter = logging.Formatter(format_str)
os.makedirs(SERVER_LOG_DIR, exist_ok=True)
master_log_fp = os.path.join(SERVER_LOG_DIR, "tricap_master.log")
master_handler = TimedRotatingFileHandler(filename=master_log_fp, when="midnight", backupCount=10)
master_handler.setLevel(logging.DEBUG)
master_handler.setFormatter(formatter)
rootlogger = logging.getLogger("")
rootlogger.addHandler(master_handler)
rootlogger.setLevel(logging.DEBUG)
rootlogger.info("Initiating new instance of the TriCap app.")

# Setup the Flask Server
app = Flask(__name__)

# Instantiate the config setting management
init_config = TricapConfig()
# Dashboard poll rates, rendered into the pages by the dashboard views.
app.config["UI_SETTINGS"] = init_config.ui_settings()


@app.before_request
def restrict_web_access():
    if not web_client_allowed(request.remote_addr):
        abort(403)


@app.after_request
def set_http_headers(response):
    response.headers["Permissions-Policy"] = "geolocation=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Setup a rotating log file for the HTTP requests (and whatever flask does)
# werkzeug messages always come from the same function, log, using a different formatter for clarity
wz_formatter = logging.Formatter("%(asctime)s | %(funcName)s | %(levelname)s | %(message)s ")
flask_log_fp = os.path.join(SERVER_LOG_DIR, "tricap_flask.log")
flask_handler = TimedRotatingFileHandler(filename=flask_log_fp, when="midnight", backupCount=10)
flask_handler.setLevel(logging.DEBUG)
flask_handler.setFormatter(wz_formatter)

wz_log = logging.getLogger("werkzeug")
wz_log.propagate = False
wz_log.addHandler(flask_handler)

app.logger.addHandler(flask_handler)
app.logger.setLevel(logging.DEBUG)
app.logger.info("Initiated flask logger for new instance of the TriCap app.")

misc_settings = init_config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
cam_settings = init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)

code_inf = GitData()

storage_lock = Lock()

tricap_manager = TriCapCamsManager(misc_settings, cam_settings, storage_lock)
tricap_cameras = tricap_manager.get_cameras_as_list()
system_clock.disable_ntp()
clock = system_clock.ClockSync(on_synced=lambda source: tricap_manager.sync_camera_clocks())

gps_ser = SerialInterface(
    "/dev/gps",
    921600,
    capturing_lock=storage_lock,
    on_first_fix=clock.sync_from_gps,
)

rootlogger.debug("Cameras have been configured.")

try:
    rootlogger.debug("Connecting to the GRF-500 altimeter.")
    altimeter = Grf500Altimeter()
except Exception as exc:
    rootlogger.warning(
        "GRF-500 altimeter is unavailable; continuing without altitude data: %s",
        exc,
        exc_info=True,
    )
    altimeter = UnavailableAltimeter("grf500", exc)

rootlogger.debug("Altimeter has been configured.")

altimeter.attach(AltitudeLogObserver())

# Capture controls measurement when an altimeter is present. The unavailable
# adapter keeps capture usable without fabricating readings.
tricap_manager.altimeter = altimeter

rootlogger.info("Git version: " + code_inf.code_id())


def shutdown():
    """Safely stop rig hardware and release mounted storage."""
    rootlogger.info("Shutting down TriCap app.")
    tricap_manager.shutdown()
    try:
        altimeter.stop_measuring()
    except Exception as exc:
        rootlogger.warning("Altimeter shutdown failed: %s", exc, exc_info=True)
    try:
        tricap_manager.unmount_disk()
    except Exception as exc:
        rootlogger.warning("SSD unmount during shutdown failed: %s", exc, exc_info=True)


# Configure the Flask Blueprints
from .views.api import api_bp  # noqa: E402
from .views.dashboard import dashboard_bp  # noqa: E402

app.register_blueprint(dashboard_bp)
app.register_blueprint(api_bp)

rootlogger.info("New instance of TriCap app has been initiated.")
