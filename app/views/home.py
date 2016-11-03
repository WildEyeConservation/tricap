# D Joubert 27 October 2016 Innoventix Consulting

import os

from flask import Blueprint, render_template, send_from_directory, current_app, request, jsonify
from flask import send_file

from app import tricap_manager, image_manager, altimeter

from config import BUTTON_CODES

home_bp = Blueprint('home', __name__)


@home_bp.route('/', methods=['GET'])
def index_slash():
    return index()


@home_bp.route('/index', methods=['GET'])
def index():
    """The home page. Handles the login form and redirects to the verification page after a
    successfull login."""
    col_size_cam_img = 12/tricap_manager.get_num_cams()
    if col_size_cam_img < 2:
        col_size_cam_img = 2
    return render_template('/home/index.html', num_cams=tricap_manager.get_num_cams(),
                           col_size_cam_img=col_size_cam_img,
                           alti_state=altimeter.get_state_as_string())


@home_bp.route('/_check_cam_image<cam_num_str>')
def is_cam_image_fresh(cam_num_str):
    data = {'new_image': image_manager.is_cam_image_fresh(int(cam_num_str)),
            'cam_num': int(cam_num_str)}
    return jsonify(data)

@home_bp.route('/_get_alti_data')
def provide_alti_data():
    data = {'alti_state': altimeter.get_state_as_string(),
            'alti_measurement': altimeter.get_measurement_as_string()}
    return jsonify(data)


@home_bp.route('/cam_img<cam_num_str>')
def serve_cam_img(cam_num_str):
    print 'serving cam img ' + cam_num_str
    cam_img_fp = image_manager.get_cam_image_fp(int(cam_num_str))
    # cam_img0_fp = '/home/deon/tmp/09_49_04_835.jpg'

    if cam_img_fp is None:
        cam_img_fp = '/home/deon/tmp/deepdream/frame1.jpg'

    return send_file(cam_img_fp, attachment_filename='image.bmp', as_attachment=True)



@home_bp.route('/_button_click')
def handle_button_click():

    button_code = request.args.get('buttonCode', 0, type=int)

    if button_code == BUTTON_CODES.START:
        tricap_manager.start_capturing()
        altimeter.start_measuring()
    elif button_code == BUTTON_CODES.STOP:
        tricap_manager.stop_capturing()
        altimeter.stop_measuring()

    return jsonify()


@home_bp.route('/favicon.ico')
def provide_favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/img'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')
