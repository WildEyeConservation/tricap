# D Joubert 27 October 2016 Innoventix Consulting

import os

from flask import Blueprint, render_template, send_from_directory, current_app, request, jsonify, send_file

from app import tricap_manager, image_manager

from config import BUTTON_CODES

home_bp = Blueprint('home', __name__)


@home_bp.route('/', methods=['GET'])
def index_slash():
    return index()


@home_bp.route('/index', methods=['GET'])
def index():
    """The home page. Handles the login form and redirects to the verification page after a
    successfull login."""
    return render_template('/home/index.html')


@home_bp.route('/_check_cam_image0')
def is_cam_image0_fresh():
    print 'Check cam image 0'
    data = {'new_image': image_manager.is_cam_image_fresh(0)}
    return jsonify(data)


@home_bp.route('/cam_img0')
def serve_cam_img0():
    print 'serving cam img 0'
    cam_img0_fp = image_manager.get_cam_image_fp(0)
    # cam_img0_fp = '/home/deon/tmp/09_49_04_835.jpg'

    if cam_img0_fp is None:
        cam_img0_fp = '/home/deon/tmp/deepdream/frame0.jpg'

    return send_file(cam_img0_fp, attachment_filename='image.bmp', as_attachment=True)


@home_bp.route('/_button_click')
def handle_button_click():

    button_code = request.args.get('buttonCode', 0, type=int)

    if button_code == BUTTON_CODES.START:
        tricap_manager.start_capturing()
    elif button_code == BUTTON_CODES.STOP:
        tricap_manager.stop_capturing()

    return jsonify()


@home_bp.route('/favicon.ico')
def provide_favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/img'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')
