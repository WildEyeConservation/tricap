from flask import Blueprint, redirect, url_for, render_template, request

from support.configure import TricapConfig
from support.git_info import GitData
from app import tricap_manager, use_dummy_cams
from config import CAM_MANAGER_STATES

camera_bp = Blueprint('camera', __name__)


@camera_bp.route('/camera')
def camera():
    serial_number = [""]*3
    free_space = [""]*3
    battery = [""]*3
    serial_number_parse = [""] * 3
    free_space_parse = [""] * 3
    battery_parse = [""] * 3

    if not use_dummy_cams:
        from support.camera_data import ParseData
        camera_data = ParseData()
        code_inf = GitData()
        for camera_number in range(3):
            serial_number_parse[camera_number], free_space_parse[camera_number], battery_parse[camera_number] =\
                camera_data.parse_camera(camera_number)
            # Ensure cameras are always in the correct slot
            if serial_number_parse[camera_number] == "032024003117":  # Middle camera/Left
                serial_number[0] = serial_number_parse[camera_number]
                free_space[0] = free_space_parse[camera_number]
                battery[0] = battery_parse[camera_number]
            elif serial_number_parse[camera_number] == "023052000180":  # Front camera/Centre
                serial_number[1] = serial_number_parse[camera_number]
                free_space[1] = free_space_parse[camera_number]
                battery[1] = battery_parse[camera_number]
            elif serial_number_parse[camera_number] == "413051000325":  # Back camera/Right
                serial_number[2] = serial_number_parse[camera_number]
                free_space[2] = free_space_parse[camera_number]
                battery[2] = battery_parse[camera_number]
        code_id = code_inf.code_id()
        code_date = code_inf.code_date()
    else:
        for camera_number in range(3):
            serial_number[camera_number], free_space[camera_number], battery[camera_number] = 1*(camera_number+1), \
                                                                                              str(100000*(camera_number+1)), \
                                                                                              str(30*(4-(camera_number+1)))
        code_id = "1.6180339887"
        code_date = "8 June 1994"
    if tricap_manager.get_state() == CAM_MANAGER_STATES.STARTED:
        return render_template('/camera/wait.html')  # Adds robustness to not cause any error when cameras are capturing
    else:
        return render_template('/camera/camera.html', serial_number=serial_number, free_space=free_space,
                               battery=battery, id=code_id, date=code_date)
