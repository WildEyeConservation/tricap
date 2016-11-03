# D Joubert Innoventix Consulting 27 October 2016

import os

import logging
from logging.handlers import TimedRotatingFileHandler

from flask import Flask

# from tricap_cameras import create_tricap_cameras_and_manager
# from image_manager import QueueImageManager
from image_manager import DummyImageManager, DummyTricapManager
from trusense_altimeter import TrusenseAltimeter

from config import SERVER_LOG_DIR

# logging (server side errors)
format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
formatter = logging.Formatter(format_str)
log_fp = os.path.join(SERVER_LOG_DIR, 'tricap_server.log')
handler = TimedRotatingFileHandler(filename=log_fp, when='midnight',
                                   backupCount=10)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)

# Setup the Flask Server, configuring it using the config.py file
app = Flask(__name__)

app.config.from_object('config')

# setup flask logging
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)  # Set this also, so as to get info messages as well

# Custom Setup
# tricap_cameras, tricap_manager = create_tricap_cameras_and_manager()
# image_manager = QueueImageManager(tricap_manager.get_cam_fp_queue())
image_manager = DummyImageManager()
tricap_manager = DummyTricapManager(2)

# setup altimeter
altimeter = TrusenseAltimeter()

# Blueprints
from .views.home import home_bp
app.register_blueprint(home_bp)
