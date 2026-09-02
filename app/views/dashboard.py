from __future__ import annotations

import bisect
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from config import FALLBACK_TELEMETRY_DIR, MOUNT_POINT

IW = "/usr/sbin/iw"

# --------------------------------------------------------------------------- #
#  Wi-Fi signal from the AP's connected stations                              #
# --------------------------------------------------------------------------- #
_wifi_lock = threading.Lock()
_wifi_cache = {
    "ts": 0.0,
    "ap": None,
    "stations": {},  # {mac: dBm}
    "clients": {},  # {ip: (timestamp, mac)}
}
_WIFI_TTL = 2.0


def _scan_ap_stations():
    """Return (ap_iface, {mac: signal_dBm}) for the AP interface, cached briefly.

    Best-effort: any failure (no iw, no AP, parse error) yields (None, {}).
    """
    with _wifi_lock:
        now = time.monotonic()
        if now - _wifi_cache["ts"] < _WIFI_TTL:
            return _wifi_cache["ap"], _wifi_cache["stations"]

        ap = None
        stations = {}
        try:
            dev = subprocess.check_output([IW, "dev"], text=True, timeout=4)
            cur = None
            for raw in dev.splitlines():
                line = raw.strip()
                if line.startswith("Interface "):
                    cur = line.split()[1]
                elif line.startswith("type ") and cur and line.split()[1] == "AP":
                    ap = cur
            if ap:
                dump = subprocess.check_output(
                    [IW, "dev", ap, "station", "dump"], text=True, timeout=4
                )
                mac = None
                for raw in dump.splitlines():
                    line = raw.strip()
                    if line.startswith("Station "):
                        mac = line.split()[1].lower()
                    elif line.startswith("signal:") and mac:
                        try:
                            stations[mac] = int(line.split(":", 1)[1].split()[0])
                        except (ValueError, IndexError):
                            pass
        except Exception:
            ap, stations = None, {}

        _wifi_cache.update(ts=time.monotonic(), ap=ap, stations=stations)
        return ap, stations


def _ip_to_mac(ip):
    if not ip:
        return None
    with _wifi_lock:
        now = time.monotonic()
        clients = _wifi_cache["clients"]
        expired = [
            cached_ip
            for cached_ip, (ts, _) in clients.items()
            if now - ts >= _WIFI_TTL
        ]
        for cached_ip in expired:
            del clients[cached_ip]
        if ip in clients:
            return clients[ip][1]

        mac = None
        try:
            out = subprocess.check_output(
                ["ip", "neigh", "show", ip], text=True, timeout=3
            )
            for raw in out.splitlines():
                parts = raw.split()
                if "lladdr" in parts:
                    mac = parts[parts.index("lladdr") + 1].lower()
                    break
        except Exception:
            pass
        clients[ip] = (time.monotonic(), mac)
        return mac


def ap_wifi_signal(client_ip=None):
    """dBm of the connected station, preferring the requesting client; else the
    strongest associated station. None if nothing is associated / unavailable."""
    _, stations = _scan_ap_stations()
    if not stations:
        return None
    if client_ip:
        mac = _ip_to_mac(client_ip)
        if mac and mac in stations:
            return stations[mac]
    return max(stations.values())  # closest to 0 = strongest


# --------------------------------------------------------------------------- #
#  Recovery uplink (the onboard Wi-Fi periodically joins the phone hotspot;   #
#  the USB high-gain adapter continues serving the local control AP).          #
# --------------------------------------------------------------------------- #
SUPPORT_CON = "skyseeker-rescue"    # pre-provisioned phone recovery profile
CUSTOM_CON = "skyseeker-uplink"     # profile created for an operator-entered SSID
NMCLI = "/usr/bin/nmcli"


def _nmcli(args, timeout=15):
    return subprocess.run([NMCLI] + args, capture_output=True, text=True, timeout=timeout)


def uplink_iface():
    """Return the NetworkManager-managed Wi-Fi uplink adapter.

    The USB adapter is reserved for the local AP, so NetworkManager's managed
    Wi-Fi device is the onboard recovery uplink. Detect it rather than relying
    on an interface name.
    """
    try:
        r = _nmcli(["-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if (len(parts) >= 3 and parts[1] == "wifi"
                    and parts[2] != "unmanaged"
                    and not parts[0].startswith("p2p-")):
                return parts[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "wlan0"


def uplink_status():
    iface = uplink_iface()
    try:
        r = _nmcli(["-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "msg": str(exc)}
    if r.returncode != 0:
        return {"available": False, "msg": r.stderr.strip()}
    state, con = "unknown", ""
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if parts[0] == iface and len(parts) >= 3:
            state, con = parts[1], parts[2]
    info = {"available": True, "iface": iface, "state": state,
            "connection": con, "connected": state.startswith("connected")}
    if info["connected"]:
        try:
            show = _nmcli(["-t", "-f", "IP4.ADDRESS", "device", "show", iface])
            for line in show.stdout.splitlines():
                if line.startswith("IP4.ADDRESS"):
                    info["ip"] = line.split(":", 1)[1].split("/")[0]
                    break
            link = subprocess.run([IW, "dev", iface, "link"], capture_output=True, text=True, timeout=5)
            for raw in link.stdout.splitlines():
                line = raw.strip()
                if line.startswith("SSID:"):
                    info["ssid"] = line.split(":", 1)[1].strip()
                elif line.startswith("signal:"):
                    info["signal"] = int(line.split(":", 1)[1].split()[0])
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass
    try:
        conn = _nmcli(["-t", "-f", "CONNECTIVITY", "general", "status"])
        info["connectivity"] = conn.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        info["connectivity"] = "unknown"
    return info


def uplink_connect(ssid=None, psk=None):
    """Join the well-known support hotspot, or an operator-supplied one."""
    try:
        _nmcli(["radio", "wifi", "on"])
        if ssid:
            name = CUSTOM_CON
            _nmcli(["connection", "delete", name])  # replace any previous custom profile
            args = ["connection", "add", "type", "wifi", "ifname", uplink_iface(),
                    "con-name", name, "ssid", ssid,
                    "connection.autoconnect", "no", "ipv6.method", "ignore",
                    "ipv4.route-metric", "100"]
            if psk:
                args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk]
            r = _nmcli(args)
            if r.returncode != 0:
                return False, r.stderr.strip() or "could not create the connection profile"
        else:
            name = SUPPORT_CON
        r = _nmcli(["--wait", "40", "connection", "up", name], timeout=50)
        if r.returncode != 0:
            return False, r.stderr.strip() or r.stdout.strip() or "connect failed"
        return True, f"Joined {ssid or SUPPORT_CON}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def uplink_disconnect():
    try:
        r = _nmcli(["device", "disconnect", uplink_iface()], timeout=20)
        if r.returncode != 0:
            return False, r.stderr.strip() or "disconnect failed"
        return True, "Uplink disconnected"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


# --------------------------------------------------------------------------- #
#  Merged onboard-GPS + laser-altitude flight log                             #
# --------------------------------------------------------------------------- #
DATA_MOUNT = MOUNT_POINT
DATA_FALLBACK = FALLBACK_TELEMETRY_DIR
FLIGHT_LOG_HEADER = ("quality,gps_timestamp,pi_timestamp,latitude,ns,longitude,ew,"
                     "gps_altitude_m,hdop,geoid_sep,"
                     "laser_altitude_agl_m,laser_strength_db,"
                     "laser_first_return_m,laser_last_return_m,"
                     "laser_first_strength_db,laser_last_strength_db\n")
ALT_MATCH_TOLERANCE_SEC = 2.0


def _load_altitude_samples(path):
    """Load new dual-return rows while retaining legacy log compatibility."""
    rows = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split(",")
                try:
                    ts = float(parts[0])
                except (IndexError, ValueError):
                    continue
                if len(parts) >= 7:
                    # altitude_m and strength_db are last-return compatibility
                    # aliases, followed by explicit first/last fields.
                    values = tuple(parts[i] for i in (1, 2, 3, 4, 5, 6))
                elif len(parts) >= 3:
                    # Historical logs contain only the then-live first return.
                    values = (parts[1], parts[2], parts[1], "", parts[2], "")
                else:
                    continue
                rows.append((ts, values))
    except OSError:
        pass
    rows.sort(key=lambda r: r[0])
    return [r[0] for r in rows], rows


def _nearest(keys, rows, ts, blanks):
    if rows:
        i = bisect.bisect_left(keys, ts)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(keys) and (best is None or abs(keys[j] - ts) < abs(keys[best] - ts)):
                best = j
        if best is not None and abs(keys[best] - ts) <= ALT_MATCH_TOLERANCE_SEC:
            return rows[best][1]
    return blanks


def merged_flight_log():
    """Today's gpsData.csv with the nearest laser-altimeter sample joined on.

    Each GPS row gains the altitudeData.csv sample nearest in pi_timestamp
    within two seconds. The fields are empty when the laser was not measuring.
    Returns (day, csv_text), or (None, None) when there is no GPS log for today.
    """
    day = datetime.now().strftime("%Y_%m_%d")
    base = DATA_MOUNT if os.path.ismount(DATA_MOUNT) else DATA_FALLBACK
    gps_path = os.path.join(base, day, "gpsData.csv")
    if not os.path.exists(gps_path):
        return None, None

    # altitudeData.csv contains legacy last-return aliases plus explicit
    # first/last distances and strengths.
    alt_keys, alt_rows = _load_altitude_samples(
        os.path.join(base, day, "altitudeData.csv"))

    out = [FLIGHT_LOG_HEADER]
    with open(gps_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            row = line.strip()
            if not row:
                continue
            laser = ("", "", "", "", "", "")
            parts = row.split(",")
            if len(parts) >= 3:
                try:
                    ts = float(parts[2])
                    laser = _nearest(alt_keys, alt_rows, ts, laser)
                except ValueError:
                    pass
            out.append(row + "," + ",".join(laser) + "\n")
    return day, "".join(out)


# --------------------------------------------------------------------------- #
#  Measured image-size sample used by the UI's remaining-flight-time estimate #
# --------------------------------------------------------------------------- #
IMAGE_SUFFIXES = {".arw", ".jpg", ".jpeg"}
IMAGE_SAMPLE_LIMIT = 200
IMAGE_DIRECTORY_LIMIT = 12
_storage_sample_lock = threading.Lock()
_storage_sample_cache = {"ts": 0.0, "payload": None}
_STORAGE_SAMPLE_TTL = 30.0


def storage_image_sample():
    """Return a bounded recent image-size sample and current free bytes."""
    now = time.monotonic()
    with _storage_sample_lock:
        cached = _storage_sample_cache["payload"]
        if cached is not None and now - _storage_sample_cache["ts"] < _STORAGE_SAMPLE_TTL:
            return cached

    payload = {
        "available": False,
        "sampleCount": 0,
        "averageImageBytes": None,
        "freeBytes": None,
    }
    if not os.path.ismount(DATA_MOUNT):
        payload["message"] = "Internal storage is not mounted."
        with _storage_sample_lock:
            _storage_sample_cache.update(ts=now, payload=payload)
        return payload

    try:
        usage = shutil.disk_usage(DATA_MOUNT)
        payload["freeBytes"] = usage.free
        candidates = []
        with os.scandir(DATA_MOUNT) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    try:
                        candidates.append(
                            (entry.stat(follow_symlinks=False).st_mtime, entry.path)
                        )
                    except OSError:
                        continue
        candidates.sort(reverse=True)

        sizes = []
        for _, directory in candidates[:IMAGE_DIRECTORY_LIMIT]:
            for root, dirs, files in os.walk(directory):
                dirs[:] = [name for name in dirs if not name.startswith(".")]
                for name in files:
                    if os.path.splitext(name)[1].lower() not in IMAGE_SUFFIXES:
                        continue
                    try:
                        size = os.path.getsize(os.path.join(root, name))
                    except OSError:
                        continue
                    if size > 0:
                        sizes.append(size)
                    if len(sizes) >= IMAGE_SAMPLE_LIMIT:
                        break
                if len(sizes) >= IMAGE_SAMPLE_LIMIT:
                    break
            if len(sizes) >= IMAGE_SAMPLE_LIMIT:
                break

        payload["sampleCount"] = len(sizes)
        if sizes:
            payload["averageImageBytes"] = round(sum(sizes) / len(sizes))
            payload["available"] = True
    except OSError as exc:
        payload["message"] = str(exc)

    with _storage_sample_lock:
        _storage_sample_cache.update(ts=now, payload=payload)
    return payload

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@dashboard_bp.get("/index")
@dashboard_bp.get("/index.html")
def home():
    return render_template("dashboard/home.html", ui_config=_ui_config())


@dashboard_bp.get("/setup")
def setup():
    return render_template("dashboard/setup.html", ui_config=_ui_config())


def _ui_config():
    """[Ui] poll rates from initial.cfg; the pages fall back to built-in values if empty."""
    return current_app.config.get("UI_SETTINGS") or {}


@dashboard_bp.get("/healthz")
def health():
    return jsonify({"ok": True})


@dashboard_bp.get("/api/uplink_status")
def get_uplink_status():
    return jsonify(uplink_status())


@dashboard_bp.get("/api/storage_estimate")
def get_storage_estimate():
    return jsonify(storage_image_sample())


@dashboard_bp.post("/api/uplink_connect")
def connect_uplink():
    payload = request.get_json(silent=True) or {}
    ok, message = uplink_connect(payload.get("ssid") or None,
                                 payload.get("psk") or None)
    return jsonify({"success": ok, "msg": message}), 200 if ok else 500


@dashboard_bp.post("/api/uplink_disconnect")
def disconnect_uplink():
    ok, message = uplink_disconnect()
    return jsonify({"success": ok, "msg": message}), 200 if ok else 500


@dashboard_bp.get("/api/flight_log")
def download_flight_log():
    day, payload = merged_flight_log()
    if payload is None:
        return jsonify({"msg": "No GPS log recorded today."}), 404
    return Response(
        payload,
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="flightData_{day}.csv"'
        },
    )
