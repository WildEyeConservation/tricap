from flask import Blueprint, request, jsonify
from app import tricap_manager, use_dummy_cams
import base64, logging, cv2
import numpy as np
from random import randint
from datetime import datetime
from config import CAM_MANAGER_STATES, CAMERA_STATES
import os, json
from support.camera_data import ParseData
from support.configure import TricapConfig
import subprocess

api_bp = Blueprint('api', __name__)
_logger = logging.getLogger(__name__)

@api_bp.route('/api')
def api():
  return "API working"

@api_bp.route('/api/status')
def status():
  cams = tricap_manager.get_cameras_as_list()

  ret = {}
  ret['mode'] = tricap_manager.state.name
  ret['cams'] = [cam.state.name for cam in cams]
  if CAMERA_STATES.ERROR_CONFIG.name in ret['cams'] or CAMERA_STATES.ERROR_CAPTURE.name in ret['cams']:
    ret['camError'] = True
  else: 
    ret['camError'] = False
  progress = tricap_manager.copy_eta()
  if progress != "":
    ret['progress'] = progress

  return ret

@api_bp.route('/api/images_captured')
def images_captured():
  ret = {}
  cams = tricap_manager.get_cameras_as_list()
  ret['imageCount'] = [cam.get_cam_image_count() for cam in cams]

  return ret

@api_bp.route('/api/statistics')
def statistics():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400
  try:
    camera_data = ParseData()
    stats = {}
    cameras = []
    sum_battery = 0.0
    battery_count = 0
    for index, cam in enumerate(tricap_manager._cameras):
      cam_info = cam.get_disk_info()
      cam_info['id'] = str(cam.serial_num)
      cameras.append(cam_info)
      try:
        _, _, battery_parse = camera_data.parse_camera(index)
        sum_battery += float(battery_parse)
        battery_count += 1
      except Exception as ex:
        pass
    stats['external'] = tricap_manager.external_disk_info()
    stats['cameras'] = cameras
    if battery_count == 0:
      stats['battery'] = 0
    else:
      stats['battery'] = sum_battery / battery_count
    config = TricapConfig()
    stats['captureInterval'] = float(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER)[0])
    # _logger.debug(stats['captureInterval'])
    return stats
  except Exception as ex:
    return "", 420

@api_bp.route('/api/image/<cam_idx>/<im_idx>')
def get_image(cam_idx, im_idx):
  # if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
  #   return jsonify({'msg': 'Not allowed in started state'}), 400
  camIdx = int(cam_idx)
  imIdx = int(im_idx)
  if camIdx >= len(tricap_manager._cameras):
    return jsonify({'msg': 'Invalid camera index'}), 400

  im = {}
  cam = tricap_manager._cameras[camIdx]
  im['serialNumber'] = str(cam.serial_num)
  im['image'] = cam.get_preview_image(imIdx)
  im['aspectRatio'] = cam.get_aspect_ratio()

  _logger.debug(len(im['image']))
  return im

@api_bp.route('/api/lensNumber')
def lens_number():
  ret = {}
  ret['lens'] = ''

  return ret

@api_bp.route('/api/restart')
def restart():
  _logger.debug('restart called')
  subprocess.run(['systemctl', 'restart', 'tricap.service'], check=True)
  _logger.debug('restart')
  return {'success': True}

@api_bp.route('/api/copy_eta')
def copy_eta():
  info = tricap_manager.copy_eta()
  if info == "":
    return jsonify({'msg': 'No copy information'}), 400

  return info  

@api_bp.route('/api/exif_sessions')
def exif_sessions():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  ids = []
  if tricap_manager.mount_disk():
    for root, dirs, files in os.walk(tricap_manager.mount_point):
      for name in files:
        if name == 'alk_to_fix.json':
          cam_info = {}
          filename = os.path.join(root, name)
          with open(filename, 'r') as f:
            cam_info = json.load(f)
          if 'sessionId' in cam_info:
            if cam_info['sessionId'] not in ids:
              ids.append(cam_info['sessionId'])

    tricap_manager.unmount_disk()
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

  return {
    'sessionIds': ids
  }

@api_bp.route('/api/exif_info', methods = ['POST'])
def exif_info():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  data = request.get_json()
  if not 'sessionIds' in data:
    return jsonify({'msg': 'Invalid session information'}), 400
  
  sessions = [] # array of session
  if tricap_manager.mount_disk():
    for root, dirs, files in os.walk(tricap_manager.mount_point):
      for name in files:
        if name == 'alk_to_fix.json':
          cam_info = {}
          filename = os.path.join(root, name)
          with open(filename, 'r') as f:
            cam_info = json.load(f)
          if 'sessionId' in cam_info:
            if cam_info['sessionId'] in data['sessionIds']:
              # missing session detected
              if any(cam_info['sessionId'] == s['sessionId'] for s in sessions):
                # add camera info
                session_idx = next((index for (index, d) in enumerate(sessions) if d['sessionId'] == cam_info['sessionId']), None)
                if session_idx >= 0 and session_idx < len(sessions):
                  sessions[session_idx]['sessionInfo'].append(cam_info)
              else:
                # first cam of session
                new_session = {
                  'sessionId': cam_info['sessionId'],
                  'sessionInfo': [cam_info]
                }
                sessions.append(new_session)
    tricap_manager.unmount_disk()
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

  return {
    'sessions': sessions
  }