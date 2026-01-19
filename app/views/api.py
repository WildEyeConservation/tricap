from __future__ import annotations

from flask import Blueprint, Response, request, jsonify, abort, send_file
from app import tricap_manager, gps_ser
import base64, logging, cv2
import numpy as np
from random import randint
from datetime import datetime
from config import CAM_MANAGER_STATES, CAMERA_STATES, SERVER_LOG_DIR, MOUNT_POINT, MOUNT_POINT_SSD
import os, json
from support.camera_data import ParseData
from support.configure import TricapConfig
import subprocess, csv
from pathlib import Path
from support.backup import manager as backupManager
import time, shutil, threading, re, io

api_bp = Blueprint('api', __name__)
_logger = logging.getLogger(__name__)

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

  wifiSignal = 0
  try:
    result = subprocess.check_output(
      ["iw", "dev", "wlx5c628bcde76d", "link"], text=True
    )
    for line in result.split("\n"):
      if "signal" in line:
        wifiSignal = int(line.split()[1])  # dBm value
  except Exception as e:
      print("Error:", e)

  ret['wifiSignal'] = wifiSignal
  # _logger.debug(f"Status {ret}")

  return ret

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

  camIdx = int(cam_idx)

  if camIdx >= len(tricap_manager._cameras):
    return jsonify({'msg': 'Invalid camera index'}), 400

  cam_session_dir = os.path.join(MOUNT_POINT, tricap_manager._copy_start_time.strftime('%Y_%m_%d'), tricap_manager._copy_start_time.strftime('%H_%M_%S'))
  # cam_session_dir = os.path.join(MOUNT_POINT, "2025_09_19", "00_26_29")
  image_dir = os.path.join(cam_session_dir, str(tricap_manager._cameras[camIdx].serial_num))

  if not Path(image_dir).is_dir():
    abort(404)

  # Top-level only for speed; swap to base.rglob("**/*") if you need recursion
  candidates = [p for p in Path(image_dir).iterdir() if p.is_file() and p.suffix.lower() == ".arw"]

  if not candidates:
    abort(404)

  # Sort by parsed timestamp→frame; fallback entries (if any) by mtime
  candidates.sort(key=sort_key_from_name)

  idx = len(candidates) // 2
  path = candidates[idx]

  _logger.debug(f"get_images called {image_dir} {cam_idx} {path}")

  return send_file(path, conditional=True)

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


@api_bp.route('/api/capture_interval', methods = ['POST'])
def set_capture_interval():
  _logger.debug("set capture interval {}".format(tricap_manager.state))

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

@api_bp.route('/api/verify_and_delete')
def verify_and_delete():
  _logger.debug("verify_and_delete {}".format(tricap_manager.state))
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return jsonify({'msg': 'Cannot delete while started'}), 400

  ret = {}
  if tricap_manager.mount_ssd():
    src = MOUNT_POINT
    dst = MOUNT_POINT_SSD
    res= backupManager.verify_and_delete_matched_sampled(src,dst)
    # res = backupManager.verify_now(src, dst, mode="fast", excludes=["*.csv", "*.bin", "*.json"])
    _logger.debug(res)
    if res["success"] and (res["delete"]["deleted"] > 0):
        _logger.debug("Backup verified. Deleted matched sources.")
        # delete_dir_async(src)
        ret['success'] = True
    else:
        _logger.debug("Verify and delete failed.")
        ret['success'] = False
    tricap_manager.unmount_disk()
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

  return ret

@api_bp.route('/api/force_delete')
def force_delete():
  _logger.debug("force_delete {}".format(tricap_manager.state))
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return jsonify({'msg': 'Cannot delete while started'}), 400

  ret = {}
  src = MOUNT_POINT
  delete_dir_async(src)
  ret['success'] = True

  return ret

@api_bp.route('/api/backup_start', methods = ['GET'])
def backup_start():
  _logger.debug("backup_start req")
  if tricap_manager.state == CAM_MANAGER_STATES.STARTED:
    return jsonify({'msg': 'Cannot backup while started'}), 400
  
  if tricap_manager.mount_ssd():
    src = MOUNT_POINT
    dst = MOUNT_POINT_SSD
    res = backupManager.start(src, dst)

    plan = {}
    if (not res.get("success")) and res.get("msg") and res.get("msg") == "Insufficient space" :
        _logger.debug("Not enough free space. Starting partial backup")
        plan = backupManager.generate_partial_files_from(
            src_root=src,
            dst_root=dst,
            margin_bytes=256 * 1024 * 1024
        )

        res2 = backupManager.start(src, dst, files_from=plan["files_from"])
        return jsonify(res2)
    else:
      return jsonify(res)
  else:
    return jsonify({'msg': 'Failed to mount external disk'}), 400

@api_bp.route('/api/backup_stop', methods = ['GET'])
def backup_stop():
  _logger.debug("backup_stop req")
  return jsonify(backupManager.stop())

@api_bp.route('/api/backup_status', methods = ['GET'])
def backup_status():
  _logger.debug("backup_status req")
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
      # current file name isn't parsed from rsync; snapshot doesn't need it
  }

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

def delete_dir_async(path: str) -> dict:
    cmd = ['rm', '-rf', '--', path]

    # Spawn and return immediately
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,   # detach from your API handler's process group
        close_fds=True,
        text=False,
    )

    # Reap the child in background to avoid a zombie
    threading.Thread(target=proc.wait, daemon=True).start()