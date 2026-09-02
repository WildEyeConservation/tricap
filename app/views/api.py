from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file

from app import altimeter, clock, gps_ser, tricap_manager
from config import (
    CAM_MANAGER_STATES,
    CAMERA_STATES,
    CAPTURE_INTERVAL_MIN_SEC,
    MOUNT_POINT,
    MOUNT_POINT_SSD,
    SERVER_LOG_DIR,
    SONY_IMAGE_FORMAT_CHOICES,
    SONY_IMAGE_FORMAT_CONFIG_KEY,
)
from support.backup import RsyncManager
from support.component_health import component_health
from support.configure import TricapConfig
from support.system_clock import validate_phone_time
from .dashboard import ap_wifi_signal

api_bp = Blueprint('api', __name__)
_logger = logging.getLogger(__name__)
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
backupManager = RsyncManager(
    unmount=tricap_manager.unmount_disk,
    refresh_usage=tricap_manager.refresh_ssd_usage,
    claim_storage=tricap_manager.claim_external_storage,
    release_storage=tricap_manager.release_external_storage,
)


def _storage_busy_reason():
    """Reason a storage job blocks restart/reboot, or None."""
    if (backupManager.status() or {}).get('running'):
        return 'Not allowed while a backup is running'
    if backupManager.verify_delete_status().get('running'):
        return 'Not allowed while verification is running'
    with _force_delete_lock:
        if _force_delete_status.get('running'):
            return 'Not allowed while internal storage is being cleared'
    return None


def _altimeter_readings():
    return {
        name: getattr(altimeter, name, None)
        for name in (
            'measurement',
            'first_return',
            'last_return',
            'first_strength',
            'last_strength',
        )
    }


def _run_system_action(command):
    try:
        subprocess.run(command, check=True)
    except Exception:
        _logger.exception('System action failed: %s', command)


def _schedule_system_action(command):
    timer = threading.Timer(1.0, _run_system_action, args=(command,))
    timer.daemon = True
    timer.start()

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
    gps["fix"] = gps_ser.hasGps()
    gps['satellites'] = gps_ser.total_visible
    gps['pdop'] = gps_ser.pdop if gps_ser.pdop is not None else 0
    gps['max'] = gps_ser.snr_max if gps_ser.snr_max is not None else 0
    gps['min'] = gps_ser.snr_min if gps_ser.snr_min is not None else 0
    gps['avg'] = gps_ser.snr_avg if gps_ser.snr_avg is not None else 0
    gps['lastUpdate'] = (datetime.now() - gps_ser.pdopLastUpdate).total_seconds() if gps_ser.pdopLastUpdate is not None else -1
    ret['gps'] = gps
    readings = _altimeter_readings()
    ret['altimeter'] = {
        # Height remains the backwards-compatible dashboard field and now
        # intentionally represents the last/farthest reflection.
        'height': readings['measurement'],
        'firstReturn': readings['first_return'],
        'lastReturn': readings['last_return'],
        'firstStrength': readings['first_strength'],
        'lastStrength': readings['last_strength'],
        'state': altimeter.get_state_as_string(),
        'unit': altimeter.unit,
        'error': str(altimeter.get_error() or ''),
    }

    ret['wifiSignal'] = ap_wifi_signal(request.remote_addr) or 0
    ret['components'] = component_health(
        tricap_manager, gps_ser, altimeter, os.path.ismount(MOUNT_POINT))

    return ret


@api_bp.route('/api/sync_phone_time', methods=['POST'])
def sync_phone_time():
    """Apply the dashboard device's timezone and, until GPS syncs, its clock."""
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
        result = clock.sync_from_phone(epoch_ms, timezone_offset)
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.exception('Could not set system clock from dashboard client')
        return jsonify({'msg': 'Could not set the device clock: {}'.format(exc)}), 500

    client_ip = request.remote_addr or 'unknown'
    timezone = result['timezone']
    cameras_synced = result['camerasSynced']
    _logger.info(
        'Clock synchronized from dashboard client %s; adjustment=%sms, '
        'timezone_offset=%s, timezone=%s, rtc_synced=%s, cameras_synced=%s',
        client_ip, result['adjustmentMs'], timezone_offset, timezone,
        result['rtcSynced'], cameras_synced)
    result['success'] = True
    return jsonify(result)

@api_bp.route('/api/images_captured')
def images_captured():
    ret = {}
    cams = tricap_manager.get_cameras_as_list()
    ret['imageCount'] = [cam.get_cam_image_count() for cam in cams]
    ret['copyCount'] = [cam.get_cam_copy_count() for cam in cams]

    return ret

@api_bp.route('/api/statistics')
def statistics():
    _logger.debug('statistics called')
    if tricap_manager.state == CAM_MANAGER_STATES.STARTED or tricap_manager.state == CAM_MANAGER_STATES.COPYING:
        return jsonify({'msg': 'Not allowed in started or copying state'}), 400
    try:
        stats = {}
        stats['internalStorage'] = _internal_disk_info()
        stats['externalStorage'] = _external_disk_info()
        stats['captureInterval'] = float(
            tricap_manager.get_image_capture_interval())
        _logger.debug(stats)
        return stats
    except Exception:
        _logger.exception('Storage statistics unavailable')
        return jsonify({'msg': 'Storage statistics unavailable'}), 503

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

@api_bp.route('/api/restart', methods=['POST'])
def restart():
    _logger.debug('restart called')
    if tricap_manager.state in (
        CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed during capture or copying'}), 409
    busy = _storage_busy_reason()
    if busy:
        return jsonify({'msg': busy}), 409
    _schedule_system_action(
        ['systemctl', '--no-block', 'restart', 'tricap.service'])
    _logger.debug('restart')
    return {'success': True}

@api_bp.route('/api/reboot', methods=['POST'])
def reboot():
    _logger.debug('reboot called')
    if tricap_manager.state in (
        CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed during capture or copying'}), 409
    busy = _storage_busy_reason()
    if busy:
        return jsonify({'msg': busy}), 409
    _schedule_system_action(['systemctl', 'reboot'])
    _logger.debug('reboot')
    return {'success': True}

@api_bp.route('/api/start_capture', methods=['POST'])
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

@api_bp.route('/api/stop_capture', methods=['POST'])
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

    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    data = request.get_json(silent=True) or {}
    interval = data.get('interval')
    if isinstance(interval, bool) or not isinstance(interval, (int, float)):
        return jsonify({'msg': 'Invalid request'}), 400
    if interval < CAPTURE_INTERVAL_MIN_SEC:
        return jsonify({'msg': f'Capture interval must be at least {CAPTURE_INTERVAL_MIN_SEC} s'}), 400

    tricap_manager.set_image_capture_interval(interval)
    config = TricapConfig()
    miscSection = config.get_section_dict(TricapConfig.MISC_SECTION_HEADER)
    miscSection["image_capture_interval"] = interval
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

@api_bp.route('/api/verify_and_delete', methods=['POST'])
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
    elif (
        tricap_manager.external_ssd_device() is None
        and not os.path.ismount(MOUNT_POINT_SSD)
    ):
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

@api_bp.route('/api/backup_start', methods=['POST'])
def backup_start():
    _logger.debug("backup_start req")
    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    if tricap_manager.mount_ssd():
        src = MOUNT_POINT
        dst = MOUNT_POINT_SSD
        res = backupManager.start(src, dst)
        if not res.get("success"):
            tricap_manager.unmount_disk()
            return jsonify(res), 400
        return jsonify(res), 202
    else:
        return jsonify({'msg': 'Failed to mount external disk'}), 400

@api_bp.route('/api/backup_move', methods=['POST'])
def backup_move():
    _logger.debug("backup_move req")
    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    if tricap_manager.mount_ssd():
        src = MOUNT_POINT
        dst = MOUNT_POINT_SSD
        res = backupManager.start(src, dst, remove_source=True)
        if not res.get("success"):
            tricap_manager.unmount_disk()
            return jsonify(res), 400
        return jsonify(res), 202
    else:
        return jsonify({'msg': 'Failed to mount external disk'}), 400

@api_bp.route('/api/backup_stop', methods=['POST'])
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
        "planned_bytes": int(st.get("planned_bytes") or 0),
        "planned_files": int(st.get("planned_files") or 0),
        "elapsed_seconds": float(st.get("elapsed_seconds") or 0),
        "copy_seconds": float(st.get("copy_seconds") or 0),
        "throughput_mib_s": float(st.get("throughput_mib_s") or 0),
    }

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

@api_bp.route('/api/download_logs', methods=['GET'])
def download_log():
    if tricap_manager.state in (CAM_MANAGER_STATES.STARTED, CAM_MANAGER_STATES.COPYING):
        return jsonify({'msg': 'Not allowed in started or copying state'}), 400

    path = Path(os.path.join(SERVER_LOG_DIR, 'tricap_master.log'))

    if not path.exists():
        abort(404)

    return send_file(
        path,
        mimetype='text/plain',
        as_attachment=True,
        download_name=path.name,
        conditional=True,
    )

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
    # Without the check an unmounted NVMe would report the root filesystem.
    if not os.path.ismount(MOUNT_POINT):
        return {}
    total, used, free = shutil.disk_usage(MOUNT_POINT)
    gb = 1073741824
    return {
        'capacityGB': round(total / gb, 2),
        'usedGB': round(used / gb, 2),
        'freeGB': round(free / gb, 2),
    }

def _external_disk_info():
    return tricap_manager.ssd_usage()

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
