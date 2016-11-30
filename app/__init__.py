# coding=utf-8
""" D Joubert Innoventix Consulting 27 October 2016
    The initial script run on accessing the flask app the first time.
    Lots of instantiation going on here, not recommended to run this unnecessarily when
    unit testing"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from flask import Flask
# Check if gphoto2 could be imported by the cameras - if not, you are probably in windows

from sensors.cam_manager import TriCapCamsManager

from sensors.trusense_altimeter import TrusenseAltimeter
from sensors.session_logger import SessionLogger
from sensors.configure import TricapConfig

from config import SERVER_LOG_DIR

# Set up rotating log file
format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
formatter = logging.Formatter(format_str)
log_fp = os.path.join(SERVER_LOG_DIR, 'tricap_server.log')
handler = TimedRotatingFileHandler(filename=log_fp, when='midnight', backupCount=10)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)

# Setup the Flask Server, configuring it using the config.py file
app = Flask(__name__)
app.config.from_object('config')

# Add logger to the flask app
rootlogger = logging.getLogger('')
rootlogger.addHandler(handler)
rootlogger.setLevel(logging.DEBUG)
app.logger.info('Initiated logger for new instance of TriCap app.')

# Instantiate a config object, and delete again, as a startup test to validate the config file
init_config = TricapConfig()

# Instantiate the sensors
tricap_manager = TriCapCamsManager(init_config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER))
tricap_cameras = tricap_manager.get_cameras_as_list()
image_manager = tricap_manager

session_logger = SessionLogger()
altimeter = TrusenseAltimeter(session_logger)

# Configure the Flask Blueprints
from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp

app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
