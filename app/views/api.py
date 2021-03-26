from flask import Blueprint, request
from app import tricap_manager, use_dummy_cams
import base64, logging, cv2
import numpy as np
from random import randint
from datetime import datetime

api_bp = Blueprint('api', __name__)
_logger = logging.getLogger(__name__)

@api_bp.route('/api')
def api():
  return "API working"

@api_bp.route('/api/status')
def status():
  ret = {}
  ret['mode'] = tricap_manager.state.name
  return ret

@api_bp.route('/api/statistics')
def statistics():
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
  idx = int(cam_idx)
  if idx >= len(tricap_manager._cameras):
    return {}

  im = {}
  cam = tricap_manager._cameras[idx]
  im['serialNumber'] = str(cam.serial_num)
  im['images'] = cam.get_preview_images()
  im['aspectRatio'] = cam.get_aspect_ratio()

  for img in im['images']:
    _logger.debug(len(img))
  return im