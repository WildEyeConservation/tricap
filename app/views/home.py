"""The 'controller' code for the landing page, which is currently the default Pilot view."""

import os
import io
import pdb

from flask import Blueprint, render_template, send_from_directory, current_app, request, jsonify
from flask import send_file, redirect, url_for

from app import tricap_manager, altimeter, session_logger, talkbox, log_list

from support.configure import TricapConfig

from config import BUTTON_CODE, CAM_MANAGER_STATES, ALTIMETER_STATE

home_bp = Blueprint('home', __name__)

# Using a dummy colour entry because Enum starts indexing from 1, and not from zero
# CAMERA_STATES = Enum("CamState", ["UNINITIALISED", "INITIALISED", "CAPTURING", "ERROR_CONFIG", "ERROR_CAPTURE"])
CAM_STATE_COLOURS = ['dummy', 'red', 'orange', 'green', 'red', 'red']
# CAM_MANAGER_STATES = Enum("CamManagerState", ["STOPPED", "STARTED", "ERROR_NO_CAMS", "ERROR_CONFIG"])
CAM_MAN_STATE_COLOURS = ['dummy', 'orange', 'green', 'red', 'red']
# ALTIMETER_STATE = Enum("AltiState", ["NOT_CONNECTED", "CONNECTED", "MEASURING", "ERROR"])
ALTI_STATE_COLOURS = ['dummy', 'red', 'orange', 'green', 'red']


@home_bp.route('/', methods=['GET'])
def index_slash():
    """Redirect request to the proper index page."""
    return index()


@home_bp.route('/index', methods=['GET'])
def index():
    """The Main GUI interface page."""
    config = TricapConfig()
    js_data = {
        'refresh_rate': config.get('refresh_rate', TricapConfig.WEB_SECTION_HEADER),
        'img_too_old_count': config.get('img_too_old_count', TricapConfig.WEB_SECTION_HEADER),
        'timeout_period': config.get('timeout_period', TricapConfig.WEB_SECTION_HEADER),
        'alti_target': config.get('alti_target', TricapConfig.WEB_SECTION_HEADER),
        'alti_range': config.get('alti_range', TricapConfig.WEB_SECTION_HEADER),
        'vibrate': config.get('vibrate', TricapConfig.WEB_SECTION_HEADER)
    }

    cams_start_display = config.get('cams_start_display', TricapConfig.WEB_SECTION_HEADER)
    alti_start_display = config.get('alti_start_display', TricapConfig.WEB_SECTION_HEADER)

    return render_template('/home/index.html', num_cams=tricap_manager.get_num_cams(),
                           cams_start_display=cams_start_display,
                           alti_start_display=alti_start_display, python_data=js_data)


# def reset_device_objects():
#     """Reset all the handlers that can be reset."""
#     config = TricapConfig()
#     misc_settings = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
#     cam_settings = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
#     tricap_manager.reset(misc_settings, cam_settings)
#     altimeter.reset(config.get_section_dict(TricapConfig.ALTI_SECTION_HEADER))


def _determine_overall_cam_state_colour():
    config = TricapConfig()

    cams_required = config.get('cams_required', TricapConfig.WEB_SECTION_HEADER)

    cams = tricap_manager.get_cameras_as_list()
    cam_state_colours = [CAM_STATE_COLOURS[cam.state.value] for cam in cams]

    # check if all the colours are the same
    if len(set(cam_state_colours)) == 1:
        return cam_state_colours[0]

    # if any of them are red, return red
    if 'red' in cam_state_colours:
        if cams_required == 'yes':
            return 'red'
        else:
            return 'orange'
    elif 'orange' in cam_state_colours:
        return 'orange'
    else:
        return 'green'


def _determine_alti_state_colour():
    config = TricapConfig()
    alti_required = config.get('alti_required', TricapConfig.WEB_SECTION_HEADER)

    alti_state_colour = ALTI_STATE_COLOURS[altimeter.state.value]
    if alti_state_colour == 'red' and alti_required != 'yes':
        return 'orange'

    return alti_state_colour


@home_bp.route('/_get_state_data')
def provide_state_data():
    """Jsonify all the data pertaining to the state of the system."""
    alti_data = {'state_colour': _determine_alti_state_colour(),
                 'measurement': str(altimeter.measurement)}

    cam_image_counts = [cam.get_cam_image_count() for cam in tricap_manager.get_cameras_as_list()]
    cam_data = {'image_counts': cam_image_counts,
                'overall_cam_state_colour': _determine_overall_cam_state_colour(),
                'capture_started': _has_capture_started()}

    talk_msgs_strs = [talk_msg.msg for talk_msg in talkbox.talk_msgs]
    talk_msgs_reply_codes = [talk_msg.reply.value for talk_msg in talkbox.talk_msgs]
    talk_data = {'msgs': talk_msgs_strs,
                 'reply_codes': talk_msgs_reply_codes}

    sys_msgs = log_list.get_msgs()
    sys_data = {'msgs': sys_msgs}

    data = {'alti': alti_data,
            'cams': cam_data,
            'talk': talk_data,
            'sys': sys_data}

    return jsonify(data)


@home_bp.route('/_submit_talkbox_msg')
def _receive_talkbox_msg():
    msg = request.args.get('msg', '', type=str)
    talkbox.add_message(msg)
    return jsonify()


@home_bp.route('/_change_message_reply')
def _change_message_reply():
    msg = request.args.get('msg', type=str)
    reply_code = request.args.get('reply_code', type=int)
    talkbox.change_reply(msg, reply_code)
    return jsonify()


@home_bp.route('/cam_img<img_str>')
def serve_cam_img(img_str):
    """Serve the image as described by the img_str = camera id + image id."""
    cam_num = int(img_str[0])
    img_num = int(img_str[1:])

    return send_file(io.BytesIO(tricap_manager.get_data(cam_num)), attachment_filename='image.jpg',
                     as_attachment=True)


def _has_capture_started():
    # if we are in the stop state and want to get started

    config = TricapConfig()

    cams_started = tricap_manager.state == CAM_MANAGER_STATES.STARTED
    alti_started = altimeter.state == ALTIMETER_STATE.MEASURING

    cams_a_must = False
    if config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) == 'yes':
        cams_a_must = True

    alti_a_must = False
    if (config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) == 'yes'):
        alti_a_must = True

    # if non of the sensors are required, then at least one has had to have started
    if not(alti_a_must or cams_a_must) and (cams_started or alti_started):
        return True
    else:
        return False

    # if a sensor is required, then capture has not started
    if (alti_a_must and not alti_started):
        return False

    if (cams_a_must and not cams_started):
        return False

    return True


@home_bp.route('/_reset')
def reset():
    """Stop the server."""
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return redirect(url_for('home.index'))


@home_bp.route('/_button_click', methods=['GET', 'POST'])
def handle_button_click():
    button_code = int(request.args.get('buttonCode'))

    if button_code == BUTTON_CODE.START:
        session_logger.create_new_session()
        tricap_manager.start_capturing()
        altimeter.start_measuring()
        return jsonify(capture_started=_has_capture_started())
    elif button_code == BUTTON_CODE.STOP:
        tricap_manager.stop_capturing()
        altimeter.stop_measuring()
        return jsonify(capture_started=_has_capture_started())
    elif button_code == BUTTON_CODE.RESET:
        # reset_device_objects()
        reset()
    elif button_code == BUTTON_CODE.STARTSTOP:
        # get current state
        started = _has_capture_started()
        if started:
            # we want to stop
            tricap_manager.stop_capturing()
            altimeter.stop_measuring()
        else:  # we want to start
            session_logger.create_new_session()
            config = TricapConfig()
            if (config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) != 'no'):
                tricap_manager.start_capturing()
            if (config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) != 'no'):
                altimeter.start_measuring()
        # send back the real state of the system
        return jsonify(capture_started=_has_capture_started())

    return jsonify()


@home_bp.route('/favicon.ico')
def provide_favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/img'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')
