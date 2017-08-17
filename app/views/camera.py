from flask import Blueprint, redirect, url_for, render_template, request
from support.camera_data import ParseData

camera_bp = Blueprint('camera', __name__)

@camera_bp.route('/camera')
def camera():
    serial_number = [""]*3
    free_space = [""]*3
    battery = [""]*3

    camera_data = ParseData()
    for camera_number in range(3):
        # serial_number[camera_number], free_space[camera_number], battery[camera_number] = 1*(camera_number+1), \
        #                                                                                   2*(camera_number+1), \
        #                                                                                   3*(camera_number+1)
        serial_number[camera_number], free_space[camera_number], battery[camera_number] = camera_data.parse_camera(camera_number)
    return render_template('/camera/camera.html', serial_number = serial_number, free_space = free_space,
                           battery = battery)