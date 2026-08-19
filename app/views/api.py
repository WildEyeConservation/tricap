from __future__ import annotations

from flask import Blueprint, Response, request, jsonify, abort, send_file
from app import tricap_manager, gps_ser, altimeter, accel_ser
import base64, logging, cv2
import numpy as np
from random import randint
from datetime import datetime
from config import (
  CAM_MANAGER_STATES,
  CAMERA_STATES,
  SERVER_LOG_DIR,
  MOUNT_POINT,
  MOUNT_POINT_SSD,
  SONY_IMAGE_FORMAT_CHOICES,
  SONY_IMAGE_FORMAT_CONFIG_KEY,
)
import os, json
from support.camera_data import ParseData
from support.configure import TricapConfig
import subprocess, csv
from pathlib import Path
from support.backup import manager as backupManager
from support.component_health import component_health
from support.phone_time import set_system_time_from_phone, validate_phone_time
import time, shutil, threading, re, io

api_bp = Blueprint('api', __name__)
_logger = logging.getLogger(__name__)
_phone_time_lock = threading.Lock()
_FORCE_DELETE_CONFIRMATION = 'delete-unbacked-internal-data'
_force_delete_lock = threading.Lock()
_force_delete_status = {
  'running': False,
  'phase': 'idle',
  'success': False,
  'completed': 0,
  'total': 0,
  'message': 'Idle',
  'errors': [],
}

@api_bp.route('/api')
def api():
  return "API working"

@api_bp.route('/api/status')
def status():
  cams = tricap_manager.get_cameras_as_list()

  ret = {}
  gps = {}
  ret['mode'] = tricap_manager.state.name
  ret['cams'] = [cam.state.name for cam in cams]
  if CAMERA_STATES.ERROR_CONFIG.name in ret['cams'] or CAMERA_STATES.ERROR_CAPTURE.name in ret['cams']:
    ret['camError'] = True
  else: 
    ret['camError'] = False
  progress = tricap_manager.copy_eta()
  if progress != "":
    ret['progress'] = progress
  gps["fix"] = gps_ser.hasGps()
  gps['satellites'] = gps_ser.total_visible
  gps['pdop'] = gps_ser.pdop if gps_ser.pdop is not None else 0
  gps['max'] = gps_ser.snr_max if gps_ser.snr_max is not None else 0
  gps['min'] = gps_ser.snr_min if gps_ser.snr_min is not None else 0
  gps['avg'] = gps_ser.snr_avg if gps_ser.snr_avg is not None else 0
  gps['lastUpdate'] = (datetime.now() - gps_ser.pdopLastUpdate).total_seconds() if gps_ser.pdopLastUpdate is not None else -1
  ret['gps'] = gps
  live_height = altimeter.measurement
  ret['altimeter'] = {
      # Height remains the backwards-compatible dashboard field and now
      # intentionally represents the last/farthest reflection.
      'height': live_height,
      'firstReturn': getattr(altimeter, 'first_return', live_height),
      'lastReturn': getattr(altimeter, 'last_return', live_height),
      'firstStrength': getattr(altimeter, 'first_strength',
                               getattr(altimeter, 'strength', 0)),
      'lastStrength': getattr(altimeter, 'last_strength',
                              getattr(altimeter, 'strength', 0)),
      'state': altimeter.get_state_as_string(),
      'unit': getattr(altimeter, 'unit', 'm'),
      'error': str(altimeter.get_error() or ''),
  }

  wifiSignal = 0
  try:
    # Detect an upstream Wi-Fi station link. The USB radio serves the rescue AP
    # outside NetworkManager, while the onboard Broadcom radio may join the
    # phone recovery hotspot. Query every connected station and use the one
    # which actually reports a signal.
    _dev = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], text=True)
    for _line in _dev.split("\n"):
      _p = _line.split(":")
      if len(_p) >= 3 and _p[1] == "wifi" and _p[2] == "connected":
        try:
          result = subprocess.check_output(["/usr/sbin/iw", "dev", _p[0], "link"], text=True)
        except Exception:
          continue
        if "signal:" in result:
          for line in result.split("\n"):
            if "signal:" in line:
              wifiSignal = int(line.split()[1])  # dBm value
          break
  except Exception as e:
      print("Error:", e)

  ret['wifiSignal'] = wifiSignal
  ret['components'] = component_health(
      tricap_manager, gps_ser, altimeter, accel_ser,
      os.path.ismount(MOUNT_POINT))
  # _logger.debug(f"Status {ret}")

  return ret


@api_bp.route('/api/sync_phone_time', methods=['POST'])
def sync_phone_time():
  """Set the rig and connected cameras from the dashboard device's clock."""
  if tricap_manager.state in (
      CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({
      'msg': 'Clock cannot be changed during capture or copying'
    }), 409

  try:
    epoch_ms, timezone_offset = validate_phone_time(
      request.get_json(silent=True))
  except ValueError as exc:
    return jsonify({'msg': str(exc)}), 400

  try:
    with _phone_time_lock:
      result = set_system_time_from_phone(epoch_ms)
      cameras_synced = 0
      camera_errors = []
      for cam in tricap_manager.get_cameras_as_list():
        try:
          cam.sync_time()
          cameras_synced += 1
        except Exception as exc:
          camera_errors.append(str(exc) or type(exc).__name__)
          _logger.warning('Could not sync camera %s time: %s',
                          getattr(cam, 'serial_num', '?'), exc)
  except (OSError, subprocess.SubprocessError) as exc:
    _logger.exception('Could not set system clock from dashboard client')
    return jsonify({'msg': 'Could not set the device clock: {}'.format(exc)}), 500

  client_ip = (
    request.headers.get('X-SkySeeker-Client-IP') or request.remote_addr or
    'unknown')
  _logger.info(
    'Clock synchronized from dashboard client %s; adjustment=%sms, '
    'timezone_offset=%s, rtc_synced=%s, cameras_synced=%s',
    client_ip, result['adjustmentMs'], timezone_offset, result['rtcSynced'],
    cameras_synced)
  result.update({
    'success': True,
    'camerasSynced': cameras_synced,
    'cameraErrors': camera_errors,
  })
  return jsonify(result)

@api_bp.route('/api/images_captured')
def images_captured():
  ret = {}
  cams = tricap_manager.get_cameras_as_list()
  ret['imageCount'] = [cam.get_cam_image_count() for cam in cams]
  ret['copyCount'] = [cam.get_cam_copy_count() for cam in cams]

  return ret

@api_bp.route('/api/do_preview')
def do_preview():
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  ret = {}
  ret['success'] = tricap_manager.start_preview()

  return ret  

@api_bp.route('/api/statistics')
def statistics():
  _logger.debug('statistics called')
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400
  try:
    # camera_data = ParseData()
    stats = {}
    # cameras = []
    # sum_battery = 0.0
    # battery_count = 0
    # for index, cam in enumerate(tricap_manager._cameras):
    #   cam_info = cam.get_disk_info()
    #   cam_info['id'] = str(cam.serial_num)
    #   cameras.append(cam_info)
    #   try:
    #     _, _, battery_parse = camera_data.parse_camera(index)
    #     sum_battery += float(battery_parse)
    #     battery_count += 1
    #   except Exception as ex:
    #     pass
    stats['internalStorage'] = _internal_disk_info()
    stats['externalStorage'] = _external_disk_info()
    # stats['cameras'] = cameras
    # if battery_count == 0:
    #   stats['battery'] = 0
    # else:
    #   stats['battery'] = sum_battery / battery_count
    config = TricapConfig()
    stats['captureInterval'] = float(config.get('image_capture_interval', TricapConfig.MISC_SECTION_HEADER))
    _logger.debug(stats)
    return stats
  except Exception as ex:
    return "", 420

def _mjpeg_placeholder_frame():
  """Single grey JPEG frame for 'no signal' when no preview is available."""
  img = np.zeros((80, 80, 3), dtype=np.uint8)
  img[:] = (48, 48, 48)
  _, jpeg = cv2.imencode('.jpg', img)
  return jpeg.tobytes()


STREAM_PREVIEW_TIMEOUT_SEC = 300  # Stop live stream after 5 minutes


def _stream_preview_frames(cam_idx: int):
  """Generate MJPEG frames for a camera.

  For Sony cameras uses SDK live view; otherwise uses preview images.
  Stops after 5 minutes or when the manager enters STARTED/COPYING.
  """
  boundary = b'frame'
  if cam_idx >= len(tricap_manager._cameras):
    return

  cam = tricap_manager._cameras[cam_idx]
  placeholder = _mjpeg_placeholder_frame()
  use_sony_live_view = getattr(tricap_manager, 'use_sony_cam', False) and hasattr(cam, 'get_live_view_frame')
  stream_start = time.monotonic()

  _logger.debug(f'stream_preview_frames called {use_sony_live_view}')
  while True:
    # Stop after 2 minutes
    if time.monotonic() - stream_start >= STREAM_PREVIEW_TIMEOUT_SEC:
      _logger.debug('stream_preview_frames ended (5 min timeout)')
      break
    # Stop streaming while system is capturing or copying
    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
      break

    try:
      if use_sony_live_view:
        frame_bytes = cam.get_live_view_frame()
        frame = frame_bytes if frame_bytes else placeholder
      else:
        # Fall back to latest preview image
        frame_b64 = ''
        for idx in (2, 1, 0):
          try:
            frame_b64 = cam.get_preview_image(idx)
            if frame_b64:
              break
          except Exception:
            continue
        frame = base64.b64decode(frame_b64) if frame_b64 else placeholder
    except Exception as e:
      _logger.debug('stream frame error: %s', e)
      frame = placeholder

    part = (
      b'--' + boundary +
      b'\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n' % len(frame) +
      frame + b'\r\n'
    )
    yield part
    time.sleep(0.1)
  _logger.debug('stream_preview_frames ended')


@api_bp.route('/api/stream/<int:cam_idx>')
def stream_preview(cam_idx):
  """Stream live preview as MJPEG for the given camera index.

  Not available while capturing or copying.
  """
  if cam_idx < 0 or cam_idx >= len(tricap_manager._cameras):
    return jsonify({'msg': 'Invalid camera index'}), 400
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Stream not available while capturing or copying'}), 503

  return Response(
    _stream_preview_frames(cam_idx),
    mimetype='multipart/x-mixed-replace; boundary=frame',
    headers={
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
    },
  )


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

NAME_RE = re.compile(
    r"^(?P<cam>\d+)_(?P<dd>\d{2})_(?P<mm>\d{2})_(?P<yyyy>\d{4})_(?P<hh>\d{2})_(?P<mi>\d{2})_(?P<ss>\d{2})_(?P<frame>\d+)\.[A-Za-z0-9]+$",
    re.IGNORECASE
)

def sort_key_from_name(p: Path):
  m = NAME_RE.match(p.name)
  if not m:
    # Fallback: mtime if name doesn't match pattern
    return ("mtime", p.stat().st_mtime, p.name.lower())
  return ("pat",
          int(m["yyyy"]), int(m["mm"]), int(m["dd"]),
          int(m["hh"]), int(m["mi"]), int(m["ss"]),
          int(m["frame"]))

@api_bp.get("/api/get_images/<cam_idx>")
def get_images(cam_idx):
  if tricap_manager._copy_start_time is None:
    abort(404)

  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  camIdx = int(cam_idx)

  if camIdx >= len(tricap_manager._cameras):
    return jsonify({'msg': 'Invalid camera index'}), 400

  cam_session_dir = os.path.join(MOUNT_POINT, tricap_manager._copy_start_time.strftime('%Y_%m_%d'), tricap_manager._copy_start_time.strftime('%H_%M_%S'))
  # cam_session_dir = os.path.join(MOUNT_POINT, "2025_09_19", "00_26_29")
  image_dir = os.path.join(cam_session_dir, str(tricap_manager._cameras[camIdx].serial_num))

  if not Path(image_dir).is_dir():
    abort(404)

  # Top-level only for speed; swap to base.rglob("**/*") if you need recursion
  image_extensions = {".arw", ".jpg", ".jpeg"}
  candidates = [
    p for p in Path(image_dir).iterdir()
    if p.is_file() and p.suffix.lower() in image_extensions
  ]

  if not candidates:
    abort(404)

  # Sort by parsed timestamp→frame; fallback entries (if any) by mtime
  candidates.sort(key=sort_key_from_name)

  idx = len(candidates) // 2
  path = candidates[idx]

  _logger.debug(f"get_images called {image_dir} {cam_idx} {path}")

  response = send_file(path, conditional=True)
  response.headers['X-SkySeeker-Filename'] = path.name
  return response

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

@api_bp.route('/api/reboot')
def reboot():
  _logger.debug('reboot called')
  subprocess.run(['systemctl', 'reboot'], check=True)
  _logger.debug('reboot')
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
        if name == 'exif_cam.json':          
          cam_info = {}
          filename = os.path.join(root, name)
          try:
            with open(filename, 'r') as f:
              cam_info = json.load(f)
            if 'sessionId' in cam_info:
              if cam_info['sessionId'] not in ids:
                ids.append(cam_info['sessionId'])
          except Exception as e:
            _logger.warning(f"Cannot open json file {e}")

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

  _logger.debug(f"Missing ids: {data['sessionIds']}")    
  
  sessions = [] # array of session
  if tricap_manager.mount_disk():
    for root, dirs, files in os.walk(tricap_manager.mount_point):
      for name in files:
        if name == 'exif_cam.json':
          cam_info = {}
          filename = os.path.join(root, name)
          try:
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
          except Exception as e:
            _logger.warning(f"Cannot open json file {e}")
    ssd_exif = os.path.join(tricap_manager.mount_point, 'exif_ssd.json')
    with open(ssd_exif, 'w') as f:
      json.dump(sessions, f, sort_keys=True)
    if tricap_manager.state != CAM_MANAGER_STATES.STARTED:
      tricap_manager.unmount_disk()
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

  return {
    'sessions': sessions
  }

@api_bp.route('/api/start_capture')
def start():
  _logger.debug("Start req {}".format(tricap_manager.state))
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return jsonify({'msg': 'Already started'}), 400
  if not tricap_manager.get_cameras_as_list():
    return jsonify({
        'msg': 'No cameras connected. Connect at least one camera to start capture.'
    }), 409
  
  tricap_manager.start_capturing()
  ret = {}
  ret['success'] = True
  return ret  

@api_bp.route('/api/stop_capture')
def stop():
  _logger.debug("Stop req {}".format(tricap_manager.state))
  if tricap_manager.state == CAM_MANAGER_STATES.STOPPED:
    return jsonify({'msg': 'Already stopped'}), 400
  
  tricap_manager.stop_capturing()
  ret = {}
  ret['success'] = True
  return ret  


@api_bp.route('/api/test_capture', methods=['POST'])
def test_capture():
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  data = request.get_json()
  if data is None or 'cam' not in data:
    return jsonify({'msg': 'Missing cam index'}), 400

  cam_idx = int(data['cam'])
  if cam_idx >= len(tricap_manager._cameras):
    return jsonify({'msg': 'Invalid camera index'}), 400

  try:
    img_bytes, filename = tricap_manager._cameras[cam_idx].test_capture()
  except Exception as e:
    _logger.error(f"test_capture failed for cam {cam_idx}: {e}")
    return jsonify({'msg': f'Capture failed: {e}'}), 500

  return send_file(io.BytesIO(img_bytes), mimetype='application/octet-stream',
                   download_name=filename, as_attachment=True)


@api_bp.route('/api/capture_interval', methods = ['POST'])
def set_capture_interval():
  _logger.debug("set capture interval {}".format(tricap_manager.state))

  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  data = request.get_json()
  if not 'interval' in data:
    return jsonify({'msg': 'Invalid request'}), 400

  tricap_manager.set_image_capture_interval(data['interval'])
  config = TricapConfig()
  miscSection = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
  miscSection["image_capture_interval"] = data['interval']
  config.set_section(miscSection, TricapConfig.MISC_SECTION_HEADER)
  config.save_to_file()

  ret = {}
  ret['success'] = True
  return ret  

@api_bp.route('/api/sony_image_format', methods=['GET', 'POST'])
def sony_image_format():
  """Read or update the Sony capture format used by the rig."""
  if request.method == 'GET':
    return jsonify({
      'value': tricap_manager.get_sony_image_format(),
      'choices': list(SONY_IMAGE_FORMAT_CHOICES),
    })

  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Stop capture or backup before changing image format'}), 400

  data = request.get_json(silent=True) or {}
  image_format = data.get('value')
  if image_format not in SONY_IMAGE_FORMAT_CHOICES:
    return jsonify({
      'msg': 'Invalid image format',
      'choices': list(SONY_IMAGE_FORMAT_CHOICES),
    }), 400

  try:
    tricap_manager.set_sony_image_format(image_format)
    config = TricapConfig()
    camera_section = config.get_section_dict(TricapConfig.CAMERA_SECTION_HEADER)
    camera_section[SONY_IMAGE_FORMAT_CONFIG_KEY] = image_format
    config.set_section(camera_section, TricapConfig.CAMERA_SECTION_HEADER)
    config.save_to_file()
  except Exception as exc:
    _logger.exception('Failed to set Sony image format to %s', image_format)
    return jsonify({'msg': str(exc) or 'Could not set image format'}), 500

  return jsonify({
    'success': True,
    'value': image_format,
    'choices': list(SONY_IMAGE_FORMAT_CHOICES),
  })

@api_bp.route('/api/verify_and_delete')
def verify_and_delete():
  _logger.debug("verify_and_delete {}".format(tricap_manager.state))
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  current = backupManager.verify_delete_status()
  if current.get("running"):
    return jsonify({'success': True, 'started': False, 'msg': 'Verification is already running'})

  if tricap_manager.mount_ssd():
    src = MOUNT_POINT
    dst = MOUNT_POINT_SSD
    res = backupManager.start_verify_and_delete(src, dst)
    if not res.get("success"):
      tricap_manager.unmount_disk()
      return jsonify(res), 409
    return jsonify(res), 202
  elif (tricap_manager.external_ssd_device() is None and
        not os.path.ismount(MOUNT_POINT_SSD)):
    return jsonify({
      'code': 'external_not_connected',
      'msg': 'No external SSD is connected',
    }), 409
  else:
    return jsonify({
      'code': 'external_mount_failed',
      'msg': 'The external SSD could not be mounted',
    }), 409

@api_bp.route('/api/verify_and_delete_status')
def verify_and_delete_status():
  return jsonify(backupManager.verify_delete_status())

@api_bp.route('/api/force_delete', methods=['POST'])
def force_delete():
  _logger.debug("force_delete {}".format(tricap_manager.state))
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  if (backupManager.status() or {}).get('running'):
    return jsonify({'msg': 'Not allowed while a backup is running'}), 409
  if backupManager.verify_delete_status().get('running'):
    return jsonify({'msg': 'Not allowed while verification is running'}), 409

  payload = request.get_json(silent=True) or {}
  if payload.get('confirmation') != _FORCE_DELETE_CONFIRMATION:
    return jsonify({
      'code': 'confirmation_required',
      'msg': 'Explicit confirmation is required to delete unbacked-up data',
    }), 400

  if not os.path.ismount(MOUNT_POINT):
    return jsonify({
      'code': 'internal_not_mounted',
      'msg': 'Internal storage is not mounted; nothing was deleted',
    }), 409

  res = delete_dir_async(MOUNT_POINT)
  return jsonify(res), (202 if res.get('success') else 409)


@api_bp.route('/api/force_delete_status')
def force_delete_status():
  with _force_delete_lock:
    return jsonify(dict(_force_delete_status))

@api_bp.route('/api/backup_start', methods = ['GET'])
def backup_start():
  _logger.debug("backup_start req")
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400
  
  if tricap_manager.mount_ssd():
    src = MOUNT_POINT
    dst = MOUNT_POINT_SSD
    res = backupManager.start(src, dst, tag_gps=False)

    plan = {}
    if (not res.get("success")) and res.get("msg") and res.get("msg") == "Insufficient space" :
        _logger.debug("Not enough free space. Starting partial backup")
        plan = backupManager.generate_partial_files_from(
            src_root=src,
            dst_root=dst,
            margin_bytes=256 * 1024 * 1024
        )

        res = backupManager.start(src, dst, files_from=plan["files_from"], tag_gps=False)
        return jsonify(res)
    else:
      return jsonify(res)
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

@api_bp.route('/api/backup_move', methods = ['GET'])
def backup_move():
  _logger.debug("backup_move req")
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  if tricap_manager.mount_ssd():
    src = MOUNT_POINT
    dst = MOUNT_POINT_SSD
    res = backupManager.start(src, dst, tag_gps=False, remove_source=True)

    if (not res.get("success")) and res.get("msg") == "Insufficient space":
        _logger.debug("Not enough free space. Starting partial copy & delete")
        plan = backupManager.generate_partial_files_from(
            src_root=src,
            dst_root=dst,
            margin_bytes=256 * 1024 * 1024
        )
        if not plan.get("success"):
          return jsonify(res)
        res = backupManager.start(src, dst, files_from=plan["files_from"], tag_gps=False, remove_source=True)
    return jsonify(res)
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

@api_bp.route('/api/backup_stop', methods = ['GET'])
def backup_stop():
  _logger.debug("backup_stop req")
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  return jsonify(backupManager.stop())

@api_bp.route('/api/backup_status', methods = ['GET'])
def backup_status():
  _logger.debug("backup_status req")
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  st = backupManager.status() or {}
  total = int(st.get("total_bytes") or 0)
  done = int(st.get("bytes_copied") or 0)
  percent = round((done / total) * 100, 2) if total > 0 else 0.0
  eta = _eta_simple(st.get("started_at"), done, total)

  return {
      "running": bool(st.get("running")),
      "phase": st.get("phase") or "idle",
      "message": st.get("message") or "",
      "percent": percent,                 # 0..100 with 2 decimals
      "bytes_done": done,
      "bytes_total": total,
      "files_done": int(st.get("files_done") or 0),
      "files_total": int(st.get("total_files") or 0),
      "eta_seconds": 0 if eta is None else float(eta),
      "current_file": st.get("current_file") or "",
      "gps_tagged": int(st.get("gps_tagged") or 0),
      "gps_interpolated": int(st.get("gps_interpolated") or 0),
      "gps_nearest": int(st.get("gps_nearest") or 0),
      "gps_unresolved": int(st.get("gps_unresolved") or 0),
      "gps_failed": int(st.get("gps_failed") or 0),
      "tag_gps": bool(st.get("tag_gps")),
      "planned_bytes": int(st.get("planned_bytes") or 0),
      "planned_files": int(st.get("planned_files") or 0),
      "elapsed_seconds": float(st.get("elapsed_seconds") or 0),
      "copy_seconds": float(st.get("copy_seconds") or 0),
      "tag_seconds": float(st.get("tag_seconds") or 0),
      "throughput_mib_s": float(st.get("throughput_mib_s") or 0),
  }

@api_bp.route('/api/netbird_key', methods=['POST'])
def set_netbird_key():
    _logger.debug("set_netbird_key {}".format(tricap_manager.state))
    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
      return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    data = request.get_json()
    if not data or 'key' not in data:
        return jsonify({'msg': 'Invalid request', 'success': False}), 400
    
    key = data.get('key', '').strip()
    if not key:
        return jsonify({'msg': 'Key cannot be empty', 'success': False}), 400
    
    try:
        # Execute: sudo netbird up --setup-key <key>
        cmd = ['sudo', 'netbird', 'up', '--setup-key', key, '--disable-auto-connect=false']
        _logger.info("Executing: {}".format(' '.join(cmd)))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            _logger.error("netbird up --setup-key failed: {}".format(error_msg))
            return jsonify({
                'msg': 'Failed to set netbird key: {}'.format(error_msg),
                'success': False
            }), 500
        
        _logger.info(f"netbird up --setup-key succeeded, return code {result.returncode}")
        ret = {
            'success': True,
            'msg': 'Netbird key set successfully'
        }
        return jsonify(ret), 200
        
    except subprocess.TimeoutExpired:
        _logger.error("netbird command timed out")
        return jsonify({
            'msg': 'Command timed out',
            'success': False
        }), 500
    except Exception as e:
        _logger.error("Error setting netbird key: {}".format(str(e)))
        return jsonify({
            'msg': 'Error: {}'.format(str(e)),
            'success': False
        }), 500


@api_bp.route('/api/netbird_connect', methods=['POST'])
def netbird_connect():
    """Connect to netbird (without setup key)"""
    _logger.debug("netbird_connect {}".format(tricap_manager.state))

    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
      return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    try:
        # Execute: sudo netbird up
        cmd = ['sudo', 'netbird', 'up']
        _logger.info("Executing: {}".format(' '.join(cmd)))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            _logger.error("netbird up failed: {}".format(error_msg))
            return jsonify({
                'msg': 'Failed to connect: {}'.format(error_msg),
                'success': False
            }), 500
        
        _logger.info("netbird up succeeded")
        ret = {
            'success': True,
            'msg': 'Netbird connected successfully'
        }
        return jsonify(ret), 200
        
    except subprocess.TimeoutExpired:
        _logger.error("netbird connect command timed out")
        return jsonify({
            'msg': 'Command timed out',
            'success': False
        }), 500
    except Exception as e:
        _logger.error("Error connecting netbird: {}".format(str(e)))
        return jsonify({
            'msg': 'Error: {}'.format(str(e)),
            'success': False
        }), 500


@api_bp.route('/api/netbird_disconnect', methods=['POST'])
def netbird_disconnect():
    """Disconnect from netbird"""
    _logger.debug("netbird_disconnect {}".format(tricap_manager.state))

    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
      return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    try:
        # Execute: sudo netbird down
        cmd = ['sudo', 'netbird', 'down']
        _logger.info("Executing: {}".format(' '.join(cmd)))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            _logger.error("netbird down failed: {}".format(error_msg))
            return jsonify({
                'msg': 'Failed to disconnect: {}'.format(error_msg),
                'success': False
            }), 500
        
        _logger.info("netbird down succeeded")
        ret = {
            'success': True,
            'msg': 'Netbird disconnected successfully'
        }
        return jsonify(ret), 200
        
    except subprocess.TimeoutExpired:
        _logger.error("netbird disconnect command timed out")
        return jsonify({
            'msg': 'Command timed out',
            'success': False
        }), 500
    except Exception as e:
        _logger.error("Error disconnecting netbird: {}".format(str(e)))
        return jsonify({
            'msg': 'Error: {}'.format(str(e)),
            'success': False
        }), 500

@api_bp.route('/api/netbird_status', methods=['GET'])
def netbird_status():
    """Get netbird connection status"""
    _logger.debug("netbird_status {}".format(tricap_manager.state))

    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
      return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    try:
        # Execute: sudo netbird status
        cmd = ['sudo', 'netbird', 'status']
        _logger.info("Executing: {}".format(' '.join(cmd)))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Parse the output to determine if connected
        # Check for "Management: Connected" and "Signal: Connected"
        output = result.stdout
        is_connected = False
        
        if output:
            # Check if both Management and Signal are Connected
            lines = output.split('\n')
            management_connected = False
            signal_connected = False
            
            for line in lines:
                line_lower = line.lower().strip()
                if line_lower.startswith('management:'):
                    if 'connected' in line_lower and 'disconnected' not in line_lower:
                        management_connected = True
                elif line_lower.startswith('signal:'):
                    if 'connected' in line_lower and 'disconnected' not in line_lower:
                        signal_connected = True
            
            # Consider connected if both Management and Signal are Connected
            is_connected = management_connected and signal_connected
        
        ret = {
            'success': True,
            'connected': is_connected,
        }
        return jsonify(ret), 200
        
    except subprocess.TimeoutExpired:
        _logger.error("netbird status command timed out")
        return jsonify({
            'success': False,
            'connected': False,
        }), 500
    except Exception as e:
        _logger.error("Error getting netbird status: {}".format(str(e)))
        return jsonify({
            'success': False,
            'connected': False,
        }), 500

CHUNK_SIZE = 1024 * 1024 # 1 MiB

def file_iterator(path, start=0, end=None):
  with path.open("rb") as f:
    f.seek(start)
    bytes_left = None if end is None else end - start + 1
    while True:
      size = CHUNK_SIZE if bytes_left is None else min(CHUNK_SIZE, bytes_left)
      if size <= 0:
        break
      data = f.read(size)
      if not data:
        break
      if bytes_left is not None:
        bytes_left -= len(data)
      yield data


@api_bp.route('/api/download_logs', methods = ['GET'])
def download_log():
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  log_path_file = Path(os.path.join(SERVER_LOG_DIR, 'tricap_master.log'))
  
  if not log_path_file.exists():
    abort(404)

  file_size = log_path_file.stat().st_size
  range_header = request.headers.get("Range", None)

  headers = {
    "Accept-Ranges": "bytes",
    "Content-Disposition": f'attachment; filename="{log_path_file.name}"',
    "Content-Type": "text/plain",
    "Cache-Control": "no-store",
  }

  if range_header:
    try:
      _, rng = range_header.split("=")
      start_s, end_s = rng.split("-")
      start = int(start_s) if start_s else 0
      end = int(end_s) if end_s else file_size - 1
      if start < 0 or end >= file_size or start > end:
        raise ValueError
    except Exception:
      abort(416) # invalid Range

    length = end - start + 1
    headers.update({
      "Content-Range": f"bytes {start}-{end}/{file_size}",
      "Content-Length": str(length),
    })
    return Response(
      file_iterator(log_path_file, start, end),
      status=206,
      headers=headers,
    )

  # Full download
  headers["Content-Length"] = str(file_size)
  return Response(file_iterator(log_path_file), headers=headers)

@api_bp.route('/api/download_imu_logs', methods = ['GET'])
def download_imu_log():
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  log_path = ''
  if os.path.ismount(MOUNT_POINT):
      log_path = os.path.join(MOUNT_POINT, datetime.now().strftime('%Y_%m_%d'))
  else:
      print("SSD not mounted, falling back to builtin storage GPS_IMU_Data for Accel data")
      log_path = os.path.join("/home/radxa/GPS_IMU_Data", datetime.now().strftime('%Y_%m_%d'))
  log_path_file = Path(os.path.join(log_path, 'accelData.bin'))

  if not log_path_file.exists():
    abort(404)

  file_size = log_path_file.stat().st_size
  range_header = request.headers.get("Range", None)

  headers = {
    "Accept-Ranges": "bytes",
    "Content-Disposition": f'attachment; filename="{log_path_file.name}"',
    "Content-Type": "text/plain",
    "Cache-Control": "no-store",
  }

  if range_header:
    try:
      _, rng = range_header.split("=")
      start_s, end_s = rng.split("-")
      start = int(start_s) if start_s else 0
      end = int(end_s) if end_s else file_size - 1
      if start < 0 or end >= file_size or start > end:
        raise ValueError
    except Exception:
      abort(416) # invalid Range

    length = end - start + 1
    headers.update({
      "Content-Range": f"bytes {start}-{end}/{file_size}",
      "Content-Length": str(length),
    })
    return Response(
      file_iterator(log_path_file, start, end),
      status=206,
      headers=headers,
    )

  # Full download
  headers["Content-Length"] = str(file_size)
  return Response(file_iterator(log_path_file), headers=headers)

@api_bp.route('/api/download_gps_logs', methods = ['GET'])
def download_gps_log():
  if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
    return jsonify({'msg': 'Not allowed in started or copying state'}), 400

  log_path = ''
  if os.path.ismount(MOUNT_POINT):
      log_path = os.path.join(MOUNT_POINT, datetime.now().strftime('%Y_%m_%d'))
  else:
      print("SSD not mounted, falling back to builtin storage GPS_IMU_Data for GPS data")
      log_path = os.path.join("/home/radxa/GPS_IMU_Data", datetime.now().strftime('%Y_%m_%d'))
  log_path_file = Path(os.path.join(log_path, 'gpsData.csv'))

  if not log_path_file.exists():
    abort(404)

  file_size = log_path_file.stat().st_size
  range_header = request.headers.get("Range", None)

  headers = {
    "Accept-Ranges": "bytes",
    "Content-Disposition": f'attachment; filename="{log_path_file.name}"',
    "Content-Type": "text/plain",
    "Cache-Control": "no-store",
  }

  if range_header:
    try:
      _, rng = range_header.split("=")
      start_s, end_s = rng.split("-")
      start = int(start_s) if start_s else 0
      end = int(end_s) if end_s else file_size - 1
      if start < 0 or end >= file_size or start > end:
        raise ValueError
    except Exception:
      abort(416) # invalid Range

    length = end - start + 1
    headers.update({
      "Content-Range": f"bytes {start}-{end}/{file_size}",
      "Content-Length": str(length),
    })
    return Response(
      file_iterator(log_path_file, start, end),
      status=206,
      headers=headers,
    )

  # Full download
  headers["Content-Length"] = str(file_size)
  return Response(file_iterator(log_path_file), headers=headers)

def _eta_simple(started_at: float | None, bytes_done: int, bytes_total: int) -> float | None:
    """ETA using only start time + completion fraction."""
    if not started_at or bytes_total <= 0 or bytes_done <= 0:
        return None
    now = time.time()
    elapsed = max(0.0, now - started_at)
    completion = bytes_done / bytes_total
    if completion <= 0.0:
        return None
    total_estimated = elapsed / completion
    return max(0.0, total_estimated - elapsed)

def _internal_disk_info():
    if tricap_manager.use_gpio_cams:
        return

    _logger.debug(f"_internal_disk_info")
    info = {}
    total, used, free = shutil.disk_usage(MOUNT_POINT)

    info['capacityGB'] = round(total / 1073741824, 2)
    info['usedGB'] = round(used / 1073741824, 2)
    info['freeGB'] = round(free / 1073741824, 2)

    return info

def _external_disk_info():
    if tricap_manager.use_gpio_cams:
        return

    _logger.debug(f"_external_disk_info")
    info = {}
    is_mounted = os.path.ismount(MOUNT_POINT_SSD)
    if tricap_manager.mount_ssd():
        total, used, free = shutil.disk_usage(MOUNT_POINT_SSD)
        if not is_mounted:
            # only unmount if unmounted at the start of this function
            tricap_manager.unmount_disk()

        info['capacityGB'] = round(total / 1073741824, 2)
        info['usedGB'] = round(used / 1073741824, 2)
        info['freeGB'] = round(free / 1073741824, 2)
    
    return info

def _run_delete_dir_contents(root: Path) -> None:
    errors = []
    try:
        # lost+found belongs to the ext4 filesystem rather than to a flight.
        entries = [p for p in root.iterdir() if p.name != 'lost+found']
        with _force_delete_lock:
            _force_delete_status.update(
                total=len(entries),
                completed=0,
                message='Deleting all data from internal storage...',
            )

        for completed, entry in enumerate(entries, start=1):
            try:
                if entry.is_symlink() or entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            except Exception as exc:
                errors.append(f'{entry.name}: {exc}')
                _logger.exception('Failed to delete %s from internal storage', entry)
            finally:
                with _force_delete_lock:
                    _force_delete_status['completed'] = completed

        with _force_delete_lock:
            _force_delete_status.update(
                running=False,
                phase='finished' if not errors else 'error',
                success=not errors,
                message=(
                    'Internal storage cleared.'
                    if not errors
                    else 'Internal storage could not be completely cleared.'
                ),
                errors=errors[:50],
            )
    except Exception as exc:
        _logger.exception('Failed to clear internal storage')
        with _force_delete_lock:
            _force_delete_status.update(
                running=False,
                phase='error',
                success=False,
                message=f'Internal storage could not be cleared: {exc}',
                errors=[str(exc)],
            )


def delete_dir_async(path: str) -> dict:
    root = Path(path).resolve()
    expected_root = Path(MOUNT_POINT).resolve()
    if root != expected_root or not os.path.ismount(root):
        return {
            'success': False,
            'msg': 'Internal storage is not safely mounted; nothing was deleted',
        }

    with _force_delete_lock:
        if _force_delete_status.get('running'):
            return {
                'success': False,
                'msg': 'Internal storage deletion is already running',
            }
        _force_delete_status.update(
            running=True,
            phase='deleting',
            success=False,
            completed=0,
            total=0,
            message='Preparing to clear internal storage...',
            errors=[],
        )

    threading.Thread(
        target=_run_delete_dir_contents,
        args=(root,),
        daemon=True,
    ).start()
    return {
        'success': True,
        'started': True,
        'msg': 'Internal storage deletion started',
    }
