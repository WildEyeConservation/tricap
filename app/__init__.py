# D Joubert Innoventix Consulting 27 October 2016

import os


import logging
from logging.handlers import TimedRotatingFileHandler

from flask import Flask

from .tricap_cameras import GPHOTO2_IMPORTED

if GPHOTO2_IMPORTED is True:
    import gphoto2 as gp
    from .cam_manager import TriCapCamsManager
    from .image_manager import  SameFileImageManager
else:
    from .cam_manager import DummyTricapManager
    from .image_manager import DummyImageManager
from .trusense_altimeter import TrusenseAltimeter

from config import SERVER_LOG_DIR

# logging (server side errors)
format_str = "%(asctime)s | %(pathname)s:%(lineno)d | %(funcName)s | %(levelname)s | %(message)s "
formatter = logging.Formatter(format_str)
log_fp = os.path.join(SERVER_LOG_DIR, 'tricap_server.log')
handler = TimedRotatingFileHandler(filename=log_fp, when='midnight', backupCount=10)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)

# Setup the Flask Server, configuring it using the config.py file
app = Flask(__name__)

app.config.from_object('config')

# setup flask logging
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)  # Set this also, so as to get info messages as well
app.logger.info('Initiated logger for new instance of TriCap app.')

# Custom Setup
if GPHOTO2_IMPORTED is True:
    tricap_manager = TriCapCamsManager(app.logger, gp.Context())
    tricap_cameras = tricap_manager.get_cameras_as_list()
    image_manager = SameFileImageManager()
else:
    app.logger.info('Gphoto2 not found, probably in windows. Loading dummy cam managers')
    tricap_manager = DummyTricapManager(2)
    tricap_cameras = tricap_manager.get_cameras_as_list()
    image_manager = DummyImageManager()

# setup altimeter
altimeter = TrusenseAltimeter(app.logger)

# Blueprints
from .views.home import home_bp
from .views.showlog import showlog_bp
from .views.settings import settings_bp
app.register_blueprint(home_bp)
app.register_blueprint(showlog_bp)
app.register_blueprint(settings_bp)
