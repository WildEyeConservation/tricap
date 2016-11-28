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
from sensors.image_manager import SameFileImageManager

from sensors.trusense_altimeter import TrusenseAltimeter
from sensors.session_logger import SessionLogger

from config import SERVER_LOG_DIR

# Set up logger
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
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)  # Set this also, so as to get info messages as well
app.logger.info('Initiated logger for new instance of TriCap app.')

# Instantiate the sensors
tricap_manager = TriCapCamsManager(app.logger)
tricap_cameras = tricap_manager.get_cameras_as_list()
image_manager = SameFileImageManager()

session_logger = SessionLogger()
altimeter = TrusenseAltimeter(app.logger, session_logger)

# Configure the Flask Blueprints
from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp

app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
