"""The 'controller' code for the landing page, which is currently seen as the default Pilot view."""

import os
import io
import pdb

from flask import Blueprint, render_template, send_from_directory, current_app, request, jsonify
from flask import send_file

from app import tricap_manager, tricap_cameras, image_manager, altimeter, session_logger

from sensors.configure import TricapConfig

from config import BUTTON_CODE

home_bp = Blueprint('home', __name__)


@home_bp.route('/', methods=['GET'])
def index_slash():
    """Redirect request to the proper index page."""
    return index()


@home_bp.route('/index', methods=['GET'])
def index():
    """The Main GUI interface page."""
    # TODO Get the params from the config
    return render_template('/home/index.html', num_cams=tricap_manager.get_num_cams(),
                           refresh_rate=1000, img_too_old_count=5)


def reset_device_objects():
    """Reset all the handlers that can be reset."""
    config = TricapConfig()
    misc_settings = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
    cam_settings = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
    tricap_manager.reset(misc_settings, cam_settings)
    altimeter.reset(config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER))


@home_bp.route('/_get_cam_data<img_str>')
def provide_cam_data(img_str):


    data = {'new_image': image_manager.is_cam_image_fresh(int(cam_num_str)),
            'cam_num': int(cam_num_str),
            'cam_state': tricap_cameras[int(cam_num_str)].get_state_as_string()
            }
    return jsonify(data)


@home_bp.route('/_get_alti_data')
def provide_alti_data():
    data = {'alti_state': altimeter.get_state_as_string(),
            'alti_measurement': altimeter.get_measurement_as_string()}
    return jsonify(data)


@home_bp.route('/cam_img<img_str>')
def serve_cam_img(img_str):
    """Serve the image as described by the img_str = camera id + image id."""
    cam_num = int(img_str[0])
    img_num = int(img_str[1:])

    return send_file(io.BytesIO(tricap_manager.get_data(cam_num)), attachment_filename='image.jpg',
                     as_attachment=True)


@home_bp.route('/_button_click')
def handle_button_click():
    button_code = request.args.get('buttonCode', 0, type=int)

    if button_code == BUTTON_CODE.START:
        session_logger.create_new_session()
        tricap_manager.start_capturing()
        altimeter.start_measuring()
    elif button_code == BUTTON_CODE.STOP:
        print('stopping - view')
        tricap_manager.stop_capturing()
        altimeter.stop_measuring()
        print('stopping - view - stopped')
    elif button_code == BUTTON_CODE.RESET:
        reset_device_objects()

    return jsonify()


@home_bp.route('/favicon.ico')
def provide_favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/img'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')
