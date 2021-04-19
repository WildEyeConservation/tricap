from flask import Blueprint, request, Response
from app import tricap_manager, use_dummy_cams
import base64, logging, cv2
import numpy as np
from random import randint
from datetime import datetime
from config import CAM_MANAGER_STATES, CAMERA_STATES
import os, json

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

  return ret

@api_bp.route('/api/images_captured')
def images_captured():
  if tricap_manager.state != CAM_MANAGER_STATES.STARTED:
    return Response("{}", status=400, mimetype='application/json')

  ret = {}
  cams = tricap_manager.get_cameras_as_list()
  ret['imageCount'] = [cam.get_cam_image_count() for cam in cams]

  return ret

@api_bp.route('/api/statistics')
def statistics():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return Response("{}", status=400, mimetype='application/json')
  stats = {}
  cameras = []
  for cam in tricap_manager._cameras:
    cam_info = cam.get_disk_info()
    cam_info['id'] = str(cam.serial_num)
    cameras.append(cam_info)
  stats['external'] = tricap_manager.external_disk_info()
  stats['cameras'] = cameras
  _logger.debug(stats)
  return stats

@api_bp.route('/api/image/<cam_idx>')
def get_image(cam_idx):
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return Response("{}", status=400, mimetype='application/json')
  idx = int(cam_idx)
  if idx >= len(tricap_manager._cameras):
    return Response("{}", status=400, mimetype='application/json')

  im = {}
  cam = tricap_manager._cameras[idx]
  im['serialNumber'] = str(cam.serial_num)
  im['images'] = cam.get_preview_images()
  im['aspectRatio'] = cam.get_aspect_ratio()

  for img in im['images']:
    _logger.debug(len(img))
  return im

@api_bp.route('/api/copy_eta')
def copy_eta():
  info = tricap_manager.copy_eta()
  if info == "":
    return Response("{}", status=400, mimetype='application/json')

  return info

@api_bp.route('/api/exif_sessions')
def exif_sessions():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return Response("{}", status=400, mimetype='application/json')

  ids = []
  if tricap_manager.mount_disk():
    for root, dirs, files in os.walk(tricap_manager.mount_point):
      for name in files:
        if name == 'exif_cam.json':
          cam_info = {}
          filename = os.path.join(root, name)
          with open(filename, 'r') as f:
            cam_info = json.load(f)
          if 'sessionId' in cam_info:
            if cam_info['sessionId'] not in ids:
              ids.append(cam_info['sessionId'])

    tricap_manager.unmount_disk()
  else:
    return Response("{}", status=400, mimetype='application/json')

  return {
    'sessionIds': ids
  }

@api_bp.route('/api/exif_info', methods = ['POST'])
def exif_info():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return Response("{}", status=400, mimetype='application/json')

  data = request.get_json()
  if not 'sessionIds' in data:
    return Response("{}", status=400, mimetype='application/json')
  
  sessions = [] # array of session
  if tricap_manager.mount_disk():
    for root, dirs, files in os.walk(tricap_manager.mount_point):
      for name in files:
        if name == 'exif_cam.json':
          cam_info = {}
          filename = os.path.join(root, name)
          with open(filename, 'r') as f:
            cam_info = json.load(f)
          if 'sessionId' in cam_info:
            if not any(cam_info['sessionId'] == s['sessionId'] for s in sessions):
              new_session = {
                'sessionId': cam_info['sessionId'],
                'sessionInfo': [cam_info]
              }
              sessions.append(new_session)
            else:
              session_idx = next((index for (index, d) in enumerate(sessions) if d['sessionId'] == cam_info['sessionId']), None)
              if session_idx >= 0 and session_idx < len(sessions):
                sessions[session_idx]['sessionInfo'].append(cam_info)
    tricap_manager.unmount_disk()
  else:
    return Response("{}", status=400, mimetype='application/json')

  return {
    'sessions': sessions
  }