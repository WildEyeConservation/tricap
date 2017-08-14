"""The 'controller' code for the landing page, which is currently the default Pilot view."""

import os
import io
from urllib.request import urlopen
from flask import Blueprint, render_template, send_from_directory, current_app, request, jsonify
from flask import send_file, redirect, url_for

from app import tricap_manager, altimeter, altimeter_switch, session_logger, talkbox, log_list, stop_all_threads
from app import rootlogger, fetch_stopper, manual_override

from support.configure import TricapConfig
from support.sms_sender import SMSSender

from config import BUTTON_CODE, CAM_MANAGER_STATES, ALTIMETER_STATE
from config import OverrideState

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
    rootlogger.info('Home Page Requested.')

    config = TricapConfig()
    js_data = {
        'refresh_rate': config.get('refresh_rate', TricapConfig.WEB_SECTION_HEADER),
        'img_too_old_count': config.get('img_too_old_count', TricapConfig.WEB_SECTION_HEADER),
        'timeout_period': config.get('timeout_period', TricapConfig.WEB_SECTION_HEADER),
        'alti_target': config.get('alti_target', TricapConfig.WEB_SECTION_HEADER),
        'alti_range': config.get('alti_range', TricapConfig.WEB_SECTION_HEADER),
        'alti_convert_to_feet': config.get('alti_convert_to_feet', TricapConfig.WEB_SECTION_HEADER),
        'vibrate': config.get('vibrate', TricapConfig.WEB_SECTION_HEADER),
        'default_session_description': session_logger.get_description()
    }

    cams_start_display = config.get('cams_start_display', TricapConfig.WEB_SECTION_HEADER)
    alti_start_display = config.get('alti_start_display', TricapConfig.WEB_SECTION_HEADER)

    if cams_start_display.lower() == 'open':
        for cam in tricap_manager.get_cameras_as_list():
            cam._camera.fetch_state = True

    return render_template('/home/index.html', num_cams=tricap_manager.get_num_cams(),
                           cams_start_display=cams_start_display,
                           alti_start_display=alti_start_display, python_data=js_data)


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


@home_bp.route('/_set_image_fetching_state')
def _set_image_fetching_state():

    image_fetch_state_str = str(request.args.get('image_fetching_state'))
    # TODO Do something with the new image fetch state
    if image_fetch_state_str == 'True':
        new_state = True
    elif image_fetch_state_str == 'False':
        new_state = False

    for cam in tricap_manager.get_cameras_as_list():
        cam._camera.fetch_state = new_state

    return jsonify()


@home_bp.route('/_get_state_data')
def provide_state_data():
    """Jsonify all the data pertaining to the state of the system."""

    altimeter_switch.set_altitude_switch_state(override = manual_override)

    alti_data = {'state_colour': _determine_alti_state_colour(),
                 'measurement': str(altimeter.measurement),
                 'switch_state': str(altimeter_switch.get_altitude_switch_state()),
                 'override': str(manual_override),
                 'error': str(altimeter.get_error())}

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


@home_bp.route('/_check_gps')
def _check_gps():
    gps_status_of_cams = tricap_manager.check_camera_gps_status()
    data = {}
    list_of_status = []
    for index, stat in enumerate(gps_status_of_cams):
        if stat is True:
            list_of_status.append('True')
        else:
            list_of_status.append('False')
    data['gps_status_of_cams'] = list_of_status
    return jsonify(data)


@home_bp.route('/_send_sms')
def _send_sms():
    sms_sender = SMSSender()
    flag = sms_sender.send('Test Message from TriCap.')
    data = {}
    data['success'] = flag
    if flag:
        data['message'] = "Test message sent to %s through %s" % (sms_sender.number, sms_sender.ip)
    else:
        data['message'] = 'Error sending message'

    return jsonify(data)


@home_bp.route('/_submit_talkbox_msg')
def _receive_talkbox_msg():
    msg = request.args.get('msg', '', type=str)
    talkbox.add_message(msg)
    return jsonify()


@home_bp.route('/_submit_session_description')
def _receive_session_description():
    description = request.args.get('sessionDescription', type=str)
    session_logger.set_description(description)
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
    # img_num = int(img_str[1:])

    # an image was requested, so either turn on fetching, or keep it going.
    fetch_stopper.keep_open()

    return send_file(io.BytesIO(tricap_manager.get_data(cam_num)), attachment_filename='image.jpg',
                     as_attachment=True)


def _has_capture_started():
    # if we are in the stop state and want to get started

    config = TricapConfig()

    # Include here the function to return false if switch is off
    altimeter_switch.set_altitude_switch_state(manual_override)
    if altimeter_switch.get_altitude_switch_state() == False \
            or manual_override == OverrideState.STOPOVERRIDE.value:
        tricap_manager.stop_capturing()
        return False

    cams_started = tricap_manager.state == CAM_MANAGER_STATES.STARTED
    alti_started = altimeter.state == ALTIMETER_STATE.MEASURING

    cams_a_must = False
    if config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) == 'yes':
        cams_a_must = True

    alti_a_must = False
    if (config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) == 'yes'):
        alti_a_must = True

    if manual_override != OverrideState.STOPOVERRIDE.value:  # = 1
        tricap_manager.start_capturing()

    # if non of the sensors are required, then at least one has had to have started
    if not(alti_a_must or cams_a_must):
        if (cams_started or alti_started):
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
    flask_reset_func = request.environ.get('werkzeug.server.shutdown')
    if flask_reset_func is None:
        raise RuntimeError('Not running with the Werkzeug Server')

    stop_all_threads()

    flask_reset_func()
    return redirect(url_for('home.index'))


@home_bp.route('/_button_click', methods=['GET', 'POST'])
def handle_button_click():
    button_code = int(request.args.get('buttonCode'))
    global manual_override

    if button_code == BUTTON_CODE.START:
        rootlogger.info('User requested capture to start.')
        session_logger.create_new_session()
        tricap_manager.start_capturing()
        manual_override = OverrideState.ALTISWITCH.value
        #altimeter.start_measuring()
        return jsonify(capture_started=_has_capture_started())
    elif button_code == BUTTON_CODE.STOP:
        rootlogger.info('User requested capture to stop.')
        tricap_manager.stop_capturing()
        manual_override = OverrideState.STOPOVERRIDE.value
        #altimeter.stop_measuring()
        return jsonify(capture_started=_has_capture_started())
    elif button_code == BUTTON_CODE.RESET:
        rootlogger.info('User requested server reset.')
        # reset_device_objects()
        reset()
    elif button_code == BUTTON_CODE.STARTSTOP:
        # get current state
        started = _has_capture_started()
        if started:
            # we want to stop
            rootlogger.info('User requested capture to stop.')
            tricap_manager.stop_capturing()
            #altimeter.stop_measuring()
            manual_override = OverrideState.STOPOVERRIDE.value  # stop capturing data
        else:  # we want to start
            rootlogger.info('User requested capture to start.')
            session_logger.create_new_session()
            config = TricapConfig()
            if (config.get('cams_required', TricapConfig.WEB_SECTION_HEADER) != 'no'):
                tricap_manager.start_capturing()
                if manual_override == OverrideState.ALTISWITCH.value:
                    manual_override = OverrideState.MANUALSTART.value  # 2 Other state for start override
                    print("Manual override start")
                else:
                    manual_override = OverrideState.ALTISWITCH.value  # Other state for start override
                    print("Altitude switch active")
            # if (config.get('alti_required', TricapConfig.WEB_SECTION_HEADER) != 'no'):
            #      altimeter.start_measuring()
        # send back the real state of the system
        return jsonify(capture_started=_has_capture_started())

    return jsonify()


@home_bp.route('/favicon.ico')
def provide_favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static/img'), 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')
