from flask import Blueprint, redirect, url_for, render_template, request

from support.configure import TricapConfig

camera_bp = Blueprint('camera', __name__)


def using_dummy_camera():
    triconfig = TricapConfig()
    web_settings = triconfig.get_section_dict(TricapConfig.WEB_SECTION_HEADER)
    dummy = web_settings['cams_required']
    if dummy == "dummy":
        return True
    else:
        return False


@camera_bp.route('/camera')
def camera():
    serial_number = [""]*3
    free_space = [""]*3
    battery = [""]*3

    if using_dummy_camera() == False:
        from support.camera_data import ParseData
        camera_data = ParseData()
        for camera_number in range(3):
            serial_number[camera_number], free_space[camera_number], battery[camera_number] =\
                camera_data.parse_camera(camera_number)
    else:
        for camera_number in range(3):
            serial_number[camera_number], free_space[camera_number], battery[camera_number] = 1*(camera_number+1), \
                                                                                              str(100000*(camera_number+1)), \
                                                                                              str(30*(4-(camera_number+1)))

    return render_template('/camera/camera.html', serial_number = serial_number, free_space = free_space,
                           battery = battery)