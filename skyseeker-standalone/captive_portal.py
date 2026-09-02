#!/usr/bin/env python3
"""SkySeeker standalone control + captive portal.

Serves Home and Setup on :80 and reverse-proxies /api/* (and /camera) to the
existing tricap Flask app on 127.0.0.1:5000. Captive-portal probe handling is
kept. Production data comes from tricap.

Two things this layer adds on top of a plain proxy:

  * Wi-Fi signal. In the production model the USB adapter provides the
    skyseeker AP while the onboard radio periodically searches for the phone's
    skyseeker-rescue recovery hotspot.
    (NetworkManager reports it 'unmanaged', and `iw ... link` says "Not
    connected"), so tricap's /api/status can never read a signal and returns
    wifiSignal: 0.  We intercept /api/status and fill wifiSignal from the
    connected station's signal (`iw dev <ap> station dump`) -- i.e. how strong
    the operator's own link to the rig is.  The portal runs as root so it can
    run iw directly.

  * The Home/Setup pages mirror the items operators know from the mobile app
    (status, captured/copied, device, storage, sensors, interval, logs,
    restart/reboot, backup, downloads, NetBird) so nobody loses a control they
    relied on.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORTAL_HOST = "control.skyseeker"
DEFAULT_TRICAP_HOST = "127.0.0.1"
DEFAULT_TRICAP_PORT = 5000
PROXY_TIMEOUT_SEC = 20
IW = "/usr/sbin/iw"

CAPTIVE_PROBE_PATHS = {
    "/generate_204", "/gen_204", "/hotspot-detect.html", "/library/test/success.html",
    "/connecttest.txt", "/ncsi.txt", "/redirect", "/canonical.html", "/success.txt",
    "/connectivity-check.html",
}
PROXY_PREFIXES = ("/api/", "/camera")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}

# --------------------------------------------------------------------------- #
#  Wi-Fi signal from the AP's connected stations                              #
# --------------------------------------------------------------------------- #
_wifi_lock = threading.Lock()
_wifi_cache = {"ts": 0.0, "ap": None, "stations": {}}  # stations: {mac: dBm}
_WIFI_TTL = 2.0


def _scan_ap_stations():
    """Return (ap_iface, {mac: signal_dBm}) for the AP interface, cached briefly.

    Best-effort: any failure (no iw, no AP, parse error) yields (None, {}).
    """
    now = time.monotonic()
    with _wifi_lock:
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
            dump = subprocess.check_output([IW, "dev", ap, "station", "dump"], text=True, timeout=4)
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

    with _wifi_lock:
        _wifi_cache.update(ts=now, ap=ap, stations=stations)
    return ap, stations


def _ip_to_mac(ip):
    if not ip:
        return None
    try:
        out = subprocess.check_output(["ip", "neigh", "show", ip], text=True, timeout=3)
        for raw in out.splitlines():
            parts = raw.split()
            if "lladdr" in parts:
                return parts[parts.index("lladdr") + 1].lower()
    except Exception:
        pass
    return None


def ap_wifi_signal(client_ip=None):
    """dBm of the connected station, preferring the requesting client; else the
    strongest associated station. None if nothing is associated / unavailable."""
    ap, stations = _scan_ap_stations()
    if not stations:
        return None
    if client_ip:
        mac = _ip_to_mac(client_ip)
        if mac and mac in stations:
            return stations[mac]
    return max(stations.values())  # closest to 0 = strongest


# --------------------------------------------------------------------------- #
#  Recovery uplink (the onboard Wi-Fi periodically joins the phone hotspot;   #
#  the USB high-gain adapter continues serving the rescue AP).                 #
# --------------------------------------------------------------------------- #
SUPPORT_CON = "skyseeker-rescue"    # pre-provisioned phone recovery profile
CUSTOM_CON = "skyseeker-uplink"     # profile created for an operator-entered SSID
NMCLI = "/usr/bin/nmcli"


def _nmcli(args, timeout=15):
    return subprocess.run([NMCLI] + args, capture_output=True, text=True, timeout=timeout)


def uplink_iface():
    """Return the NetworkManager-managed Wi-Fi uplink adapter.

    The USB adapter is reserved for the rescue AP, so NetworkManager's managed
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
#  Onboard-GPS + laser-altitude flight log                                    #
# --------------------------------------------------------------------------- #
DATA_MOUNT = "/mnt/ext_cam_storage"
DATA_FALLBACK = "/home/radxa/GPS_IMU_Data"
# Written live by tricap (support/flight_log.py) beside the raw sensor logs,
# so the download is byte-identical to the file on the storage drive.
FLIGHT_LOG_FILENAME = "flightData.csv"


def flight_log_for_today():
    """Return (day, csv_text) for today's flightData.csv, or (None, None)."""
    day = datetime.now().strftime("%Y_%m_%d")
    base = DATA_MOUNT if os.path.ismount(DATA_MOUNT) else DATA_FALLBACK
    path = os.path.join(base, day, FLIGHT_LOG_FILENAME)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return day, f.read()
    except OSError:
        return None, None


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


STYLE = r'''
:root{
  --bg:#ffffff;--card:#ffffff;--line:#e5e5e5;--line-soft:#ececec;--row-line:#f2f2f2;
  --ink:#0a0a0a;--sub:#737373;--muted:#8a8a88;--faint:#a3a3a3;
  --btn-bg:#ffffff;--btn-line:#e5e5e5;--input-bg:#ffffff;
  --primary-bg:#0a0a0a;--primary-ink:#ffffff;
  --red:#c8271c;--red-ink:#c8271c;--red-btn-bg:#ffffff;--rec:#d92d20;
  --track:#ececec;--fill:#0a0a0a;--dash:#d4d4d4;--dash-bg:#ffffff;--seg-bg:#f5f5f5;
  --nav-bg:var(--bg);--climb-near:#007f98;--climb:#00c2e0;--descend-near:#a94f00;--descend:#ff7a00;
  --sans:'Archivo',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,'Cascadia Code','Consolas',monospace;
}
html[data-theme=default]{
  --bg:#2b3e50;--card:#394d60;--line:#607080;--line-soft:#526476;--row-line:#465a6d;
  --ink:#ffffff;--sub:#d7dde3;--muted:#b8c1ca;--faint:#9da9b5;
  --btn-bg:#4d5d6d;--btn-line:#71808e;--input-bg:#33475a;
  --primary-bg:#df691a;--primary-ink:#ffffff;
  --red:#d9534f;--red-ink:#ffb8b5;--red-btn-bg:transparent;--rec:#ff655d;
  --track:#4d5d6d;--fill:#df691a;--dash:#71808e;--dash-bg:#33475a;--seg-bg:#253748;
  --nav-bg:#4d5d6d;--climb-near:#1398b1;--climb:#31c7e3;--descend-near:#d06a25;--descend:#ff9b4a;
}
html[data-theme=dark]{
  --bg:#0a0a0a;--card:#151515;--line:#2a2a2a;--line-soft:#262626;--row-line:#202020;
  --ink:#ffffff;--sub:#a3a3a3;--muted:#8a8a88;--faint:#666666;
  --btn-bg:#1e1e1e;--btn-line:#2a2a2a;--input-bg:#111111;
  --primary-bg:#ffffff;--primary-ink:#0a0a0a;
  --red:#e5342a;--red-ink:#ff5347;--red-btn-bg:transparent;--rec:#ff5347;
  --track:#262626;--fill:#ffffff;--dash:#333333;--dash-bg:#0a0a0a;--seg-bg:#1e1e1e;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);-webkit-text-size-adjust:100%;font-size:14px}
button,input{font-family:inherit}
.mono{font-family:var(--mono)}
.app{max-width:480px;margin:0 auto;min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;background:var(--bg)}
.appbar{position:sticky;top:0;z-index:20;flex:0 0 auto;background:var(--nav-bg);border-bottom:1px solid var(--line);padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:9px;min-width:0;text-decoration:none}
.brand-logo{height:22px;width:auto;display:block}
html[data-theme=dark] .logo-light,html[data-theme=default] .logo-light{display:none}
html:not([data-theme=dark]):not([data-theme=default]) .logo-dark{display:none}
.wordmark{font-weight:700;font-size:16px;letter-spacing:.01em;color:var(--ink)}
.host{font-size:11px;font-weight:500;color:var(--muted);white-space:nowrap}
.content{flex:1 1 auto;overflow-y:auto;padding:18px 16px 20px;display:flex;flex-direction:column;gap:16px}
.section-label{font-weight:600;font-size:11px;letter-spacing:.11em;color:var(--muted);text-transform:uppercase;margin:2px 2px -6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px}
.card.pad{padding:18px}
.status-card{border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:16px}
.status-top{display:flex;align-items:center;justify-content:space-between}
.kicker{font-weight:600;font-size:11px;letter-spacing:.09em;color:var(--muted);text-transform:uppercase}
.rec{display:flex;align-items:center;gap:7px}
.rec-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:var(--faint)}
.rec-dot.live{background:var(--rec);animation:pulseR 2s infinite}
.rec-dot.bad{background:var(--rec)}
@keyframes pulseR{0%{box-shadow:0 0 0 0 rgba(217,45,32,.4)}70%{box-shadow:0 0 0 8px rgba(217,45,32,0)}100%{box-shadow:0 0 0 0 rgba(217,45,32,0)}}
.rec-text{font-weight:600;font-size:11px;letter-spacing:.08em;color:var(--ink);text-transform:uppercase}
.mode-text{font-weight:600;font-size:33px;line-height:1;color:var(--ink)}
.statgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:459px){
  .statgrid{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:16px}
  .statgrid .stat:nth-child(odd){border-left:0;padding-left:0}
}
.stat{min-width:0;padding:0 8px;border-left:1px solid var(--line-soft)}
.stat:first-child{padding-left:0;border-left:0}
.stat:last-child{padding-right:0}
.stat-val{font-weight:500;font-size:16px;line-height:1;color:var(--ink);white-space:nowrap}
.stat-label{font-weight:600;font-size:10px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin-top:6px}
.big-btn{border:0;border-radius:11px;min-height:60px;font-weight:600;font-size:18px;letter-spacing:.01em;cursor:pointer}
.big-btn.go{background:var(--primary-bg);color:var(--primary-ink)}
.big-btn.stop{background:var(--red);color:#fff}
.big-btn:disabled{opacity:.6;cursor:wait}
.conn-note{margin:0;font-size:12px;color:var(--red-ink)}
.conn-note:empty{display:none}
.acc-head{display:flex;align-items:center;justify-content:space-between;padding:16px;cursor:pointer;gap:10px}
.acc-title{font-weight:600;font-size:15px;color:var(--ink)}
.acc-right{display:flex;align-items:center;gap:12px}
.acc-sum{font-size:13px;font-weight:500;color:var(--sub);display:flex;align-items:center;gap:7px}
.acc-sum.strong{color:var(--ink)}
.chev{display:inline-flex;transition:transform .15s ease}
.acc.open .chev{transform:rotate(90deg)}
.chev-svg{width:13px;height:13px;display:block}
.chev-svg path{fill:none;stroke:var(--faint);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
.acc-body{display:none;padding:0 16px 16px;border-top:1px solid var(--line-soft);padding-top:14px}
.acc.open .acc-body{display:block}
.cam-list{display:flex;flex-direction:column}
.cam-row{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-top:1px solid var(--row-line)}
.cam-row:first-child{border-top:0;padding-top:0}
.cam-left{display:flex;align-items:center;gap:8px}
.cam-name{font-weight:500;font-size:14px;color:var(--ink)}
.cam-meta{font-size:13px;font-weight:500;color:var(--sub)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--faint);display:inline-block;flex:0 0 auto}
.dot.good{background:#17a558}
.dot.bad{background:var(--rec)}
.dot.warn{background:#d97706}
.dot.off{background:var(--faint)}
.empty{margin:0;color:var(--sub);font-size:13px}
.stor-item{margin-bottom:16px}
.stor-item:last-child{margin-bottom:0}
.stor-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.stor-name{font-weight:500;font-size:14px;color:var(--ink)}
.stor-name.off,.stor-val.off{color:var(--faint)}
.stor-val{font-size:12px;font-weight:500;color:var(--sub)}
.stor-estimate{margin:9px 0 0;font-size:13px;font-weight:700;color:var(--ink)}
.stor-estimate.muted{font-weight:500;color:var(--sub)}
.track{height:8px;background:var(--track);border-radius:6px;overflow:hidden}
.track .fill{height:100%;background:var(--fill)}
.track.dashed{background:var(--dash-bg);border:1px dashed var(--dash)}
.subhead{font-weight:600;font-size:10.5px;letter-spacing:.08em;color:var(--muted);text-transform:uppercase;margin:0 0 10px}
.acc-body>.subhead:not(:first-child){margin-top:16px}
.advanced{margin-top:16px;padding-top:4px;border-top:1px solid var(--line-soft)}
.advanced summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--muted);font-size:12px;font-weight:600;list-style-position:inside}
.advanced[open] summary{margin-bottom:10px}
.mgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px}
.m-label{font-weight:600;font-size:10px;letter-spacing:.07em;color:var(--muted);text-transform:uppercase;margin-bottom:5px}
.m-value{font-weight:500;font-size:14px;color:var(--ink)}
.badge{font-weight:600;font-size:10px;letter-spacing:.04em;padding:4px 8px;border-radius:6px;border:1px solid var(--dash);color:var(--ink);white-space:nowrap}
.badge.idle{color:var(--sub);border-color:var(--line)}
.row-between{display:flex;align-items:center;justify-content:space-between;gap:10px}
.mb{margin-bottom:14px}
.mt{margin-top:10px}
.card-h{font-weight:600;font-size:15px;color:var(--ink)}
.interval-val{font-weight:500;font-size:20px;color:var(--ink)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.benchmark-line{margin:8px 0 0;color:var(--sub);font-size:12px;line-height:1.45}
.step-btn{min-height:54px;border-radius:9px;border:1px solid var(--btn-line);background:var(--btn-bg);color:var(--ink);font-weight:500;font-size:16px;cursor:pointer}
.go-btn{min-height:54px;border-radius:9px;border:0;background:var(--primary-bg);color:var(--primary-ink);font-weight:600;font-size:15px;cursor:pointer}
.danger-btn{min-height:52px;border-radius:9px;border:1px solid var(--red);background:var(--red-btn-bg);color:var(--red-ink);font-weight:600;font-size:14px;cursor:pointer}
.pill-btn{min-height:50px;border-radius:9px;border:1px solid var(--btn-line);background:var(--btn-bg);color:var(--ink);font-weight:600;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;text-align:center;text-decoration:none;padding:0 10px}
button:disabled,.pill-btn[disabled]{opacity:.5;cursor:not-allowed}
.progress-track{height:10px;background:var(--track);border-radius:6px;overflow:hidden}
.progress-fill{height:100%;width:0;background:var(--fill);transition:width .3s ease}
.muted{color:var(--sub)}
.small{font-size:12.5px;line-height:1.5}
.lock-note{margin:0 0 2px;font-size:12.5px;color:var(--red-ink)}
.lock-note:empty{display:none}
.nb-field{display:flex;gap:10px}
.text-input{flex:1;min-width:0;min-height:50px;border-radius:9px;border:1px solid var(--btn-line);background:var(--input-bg);color:var(--ink);padding:0 14px;font-size:14px;font-weight:500}
.input-suffix{position:relative;flex:1;min-width:0;display:flex}
.input-suffix .text-input{width:100%;padding-right:38px}
.input-suffix-mark{position:absolute;right:14px;top:50%;transform:translateY(-50%);font-size:14px;font-weight:700;color:var(--sub);pointer-events:none}
.nb-field .pill-btn{min-width:96px;white-space:nowrap}
.notice{display:none;padding:12px 14px;border-radius:10px;background:var(--red);color:#fff;font-size:13px;font-weight:600}
.notice.show{display:block}
.component-panel{padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
.component-panel[hidden]{display:none}
.component-title{font-weight:600;font-size:14px;color:var(--ink);margin-bottom:7px}
.component-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.component-item{display:flex;align-items:flex-start;gap:8px;color:var(--sub);font-size:12.5px;line-height:1.45}
.component-item .dot{margin-top:5px;background:#d97706}
.toast{position:fixed;left:50%;bottom:88px;transform:translateX(-50%);max-width:calc(100% - 28px);padding:11px 15px;background:var(--primary-bg);color:var(--primary-ink);border-radius:9px;font-size:13px;box-shadow:0 12px 30px rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .16s ease;z-index:50;display:flex;align-items:center;gap:9px}
.toast.show{opacity:1}
.toast-spinner{width:14px;height:14px;flex:0 0 auto;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:toast-spin .7s linear infinite}
.action-busy{pointer-events:none}
@keyframes toast-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.toast{transition:none}.toast-spinner{animation-duration:1.4s}}
.connection-warning{position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;text-align:center;padding:24px;background:#b00000;color:#fff}
.connection-warning.show{display:flex}
.connection-warning-inner{max-width:680px}
.connection-warning-title{font-weight:900;font-size:clamp(42px,12vw,92px);line-height:.92;letter-spacing:-.035em;text-transform:uppercase}
.connection-warning-text{margin:22px 0 0;font-weight:800;font-size:clamp(20px,5vw,36px);line-height:1.15}
.bottomnav{position:sticky;bottom:0;z-index:20;flex:0 0 auto;background:var(--nav-bg);border-top:1px solid var(--line);padding:10px 12px calc(14px + env(safe-area-inset-bottom));display:flex;gap:8px}
.navitem{flex:1;display:flex;flex-direction:column;align-items:center;gap:5px;padding:9px 0;border-radius:10px;color:var(--sub);text-decoration:none}
.navitem.active{background:var(--primary-bg);color:var(--primary-ink)}
.nav-ico{width:19px;height:19px;display:block}
.nav-ico path{fill:none;stroke:currentColor;stroke-width:2.3;stroke-linecap:round;stroke-linejoin:round}
.nav-label{font-weight:600;font-size:11px;letter-spacing:.04em}
.seg{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;background:var(--seg-bg);border:1px solid var(--btn-line);border-radius:11px;padding:5px}
.seg-btn{min-height:48px;border-radius:8px;border:0;background:transparent;color:var(--sub);font-weight:600;font-size:14px;cursor:pointer}
.seg-btn.active{background:var(--primary-bg);color:var(--primary-ink)}
.theme-val{font-size:12px;font-weight:500;color:var(--sub)}
.home-stack{display:flex;flex-direction:column;gap:16px}
.flight-view{display:none;flex:1 1 auto;flex-direction:column;min-height:0;gap:0}
body.flight #normalHome{display:none}
body.flight .flight-view{display:flex}
body.flight .app{height:100vh;height:100dvh}
.flight-top{display:flex;align-items:center;justify-content:space-between;padding:2px 2px 0}
.flight-main{flex:1 1 auto;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:8px 0}
.chev-stack{display:flex;flex-direction:column;align-items:center;min-height:48px;justify-content:flex-end}
.chev-stack.down{justify-content:flex-start}
.fchev{width:126px;height:42px;display:none;margin:2px 0}
.fchev.on{display:block}
.chev-stack.up .fchev path{fill:var(--chev-color,var(--climb))}
.chev-stack.down .fchev path{fill:var(--chev-color,var(--descend))}
.flight-alt{font-weight:700;font-size:66px;line-height:1;color:var(--ink);letter-spacing:-.01em;white-space:nowrap}
.flight-alt .unit{font-size:26px;font-weight:600;color:var(--sub);margin-left:7px}
.flight-target{font-size:13px;font-weight:500;color:var(--muted);min-height:18px;text-align:center;padding:0 12px}
.flight-stats{flex:0 0 auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));padding:14px 2px;border-top:1px solid var(--line)}
.flight-actions{flex:0 0 auto;margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:10px}
.flight-stop-btn{border:0;border-radius:12px;background:var(--red);color:#fff;min-height:64px;cursor:pointer;font-weight:700;font-size:15px;letter-spacing:.01em}
.flight-stop-btn:disabled{opacity:.6;cursor:wait}
.glance-bar{border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);min-height:64px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;letter-spacing:.01em}
.glance-modal{position:fixed;inset:0;z-index:60;background:var(--bg);display:none;flex-direction:column}
.glance-modal.open{display:flex}
.glance-modal-head{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line);background:var(--bg)}
.glance-modal-title{font-weight:600;font-size:11px;letter-spacing:.11em;color:var(--muted);text-transform:uppercase}
.glance-close{min-height:48px;padding:0 20px;border-radius:10px;border:1px solid var(--ink);background:var(--btn-bg);color:var(--ink);font-weight:700;font-size:14px;cursor:pointer;display:flex;align-items:center;gap:8px}
.glance-modal-body{flex:1 1 auto;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:16px;max-width:480px;width:100%;margin:0 auto;padding-bottom:calc(20px + env(safe-area-inset-bottom))}
.consent-modal{position:fixed;inset:0;z-index:70;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;padding:20px}
.consent-modal.open{display:flex}
.consent-card{background:var(--card);border:1px solid var(--line);border-radius:14px;max-width:420px;width:100%;padding:20px;display:flex;flex-direction:column;gap:14px}
.consent-title{font-weight:700;font-size:17px;color:var(--ink)}
.consent-text{margin:0;color:var(--sub);font-size:13px;line-height:1.5}
.consent-cancel{border:0;background:none;color:var(--muted);font-weight:600;font-size:13px;cursor:pointer;min-height:44px}
button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--faint);outline-offset:2px}
'''

CHEV = '<svg class="chev-svg" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"></path></svg>'
FCHEV_UP = '<svg class="fchev" viewBox="0 0 132 44" aria-hidden="true"><path d="M66 0 132 27v17L66 17 0 44V27Z"></path></svg>'
FCHEV_DOWN = '<svg class="fchev" viewBox="0 0 132 44" aria-hidden="true"><path d="M66 44 0 17V0l66 27L132 0v17Z"></path></svg>'

COMMON_JS = r'''
const el=id=>document.getElementById(id);
const fmt=(v,f="--")=>(v===null||v===undefined||v==="")?f:v;
const nf=v=>Number(v||0).toLocaleString();
function toast(m){const t=el("toast");t.textContent=m;t.classList.remove("loading");t.classList.add("show");clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove("show"),2800)}
function loadingToast(m){const t=el("toast"),s=document.createElement("span"),label=document.createElement("span");s.className="toast-spinner";s.setAttribute("aria-hidden","true");label.textContent=m;t.textContent="";t.append(s,label);t.classList.add("show","loading");clearTimeout(t._t)}
function hideLoadingToast(){const t=el("toast");if(t.classList.contains("loading")){t.classList.remove("show","loading")}}
function beginAction(control,message){
  if(!control||control.disabled||control.dataset.actionBusy==="true")return null;
  control.dataset.actionBusy="true";control.classList.add("action-busy");control.setAttribute("aria-busy","true");
  if("disabled" in control)control.disabled=true;else control.setAttribute("aria-disabled","true");
  loadingToast(message);
  let finished=false;
  return keepLoading=>{
    if(finished)return;finished=true;
    delete control.dataset.actionBusy;control.classList.remove("action-busy");control.removeAttribute("aria-busy");control.removeAttribute("aria-disabled");
    if("disabled" in control)control.disabled=false;
    if(!keepLoading)hideLoadingToast();
  };
}
async function fetchJson(path,opt){const r=await fetch(path,Object.assign({cache:"no-store"},opt||{}));const text=await r.text();let data={};if(text){try{data=JSON.parse(text)}catch(_){data={msg:text}}}if(!r.ok){const e=new Error(data.msg||`${r.status} ${r.statusText}`);e.data=data;e.status=r.status;throw e}return data}
async function postJson(path,body){return fetchJson(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body||{})})}
// Single-flight: a poll tick that finds the previous request for the same key
// still in flight is skipped, never queued, so at most one request per poller
// is outstanding and no catch-up burst fires when a stall clears.
const inflightRequests=new Set();
async function singleFlight(key,work){
  if(inflightRequests.has(key))return;
  inflightRequests.add(key);
  try{return await work()}finally{inflightRequests.delete(key)}
}
// Reschedules after the work completes (not on a fixed clock), so ticks stay
// spaced by the full delay even when a request runs long. Fires immediately.
function runPeriodic(work,delay){
  const run=async()=>{try{await work()}finally{setTimeout(run,typeof delay==="function"?delay():delay)}};
  run();
}
async function syncPhoneClock(){
  const now=new Date();
  return postJson("/api/sync_phone_time",{
    epochMs:now.getTime(),
    timezoneOffsetMinutes:now.getTimezoneOffset()
  });
}
function downloadBlob(blob,name){const u=URL.createObjectURL(blob),a=document.createElement("a");a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),4000)}
let heartbeatBusy=false,heartbeatFailures=0;
function showConnectionWarning(show){el("connectionWarning").classList.toggle("show",show)}
async function connectionHeartbeat(){
  if(heartbeatBusy)return;
  heartbeatBusy=true;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),2500);
  try{
    const r=await fetch(`/healthz?_=${Date.now()}`,{cache:"no-store",signal:controller.signal});
    if(!r.ok)throw new Error("health check failed");
    heartbeatFailures=0;showConnectionWarning(false);
  }catch(_){
    heartbeatFailures+=1;
    if(heartbeatFailures>=2)showConnectionWarning(true);
  }finally{clearTimeout(timer);heartbeatBusy=false}
}
window.addEventListener("offline",()=>showConnectionWarning(true));
window.addEventListener("online",connectionHeartbeat);
runPeriodic(connectionHeartbeat,5000);
el("host").textContent=location.host||"control.skyseeker";
syncPhoneClock().catch(()=>{});
document.querySelectorAll(".acc-head").forEach(h=>h.addEventListener("click",()=>h.closest(".acc").classList.toggle("open")));
'''

HOME_JS = COMMON_JS + r'''
const good=new Set(["INITIALISED","CAPTURING","READY","STARTED"]);
const bad=new Set(["ERROR_CONFIG","ERROR_CAPTURE","ERROR"]);
let latest=null,busy=false,lastStats=null,lastStorageEstimate=null;
function sum(a){return Array.isArray(a)?a.reduce((x,y)=>x+Number(y||0),0):0}
function altSettings(){
  let target=NaN,devPct=NaN,unit="ft";
  try{
    target=parseFloat(localStorage.getItem("ss-alt-target"));
    devPct=parseFloat(localStorage.getItem("ss-alt-dev"));
    unit=localStorage.getItem("ss-alt-unit")||"ft";
  }catch(_){}
  if(!Number.isFinite(devPct)||devPct<0)devPct=5;
  return{target,devPct,unit:unit==="m"?"m":"ft"};
}
function toUnit(value,from,to){return from===to?value:(from==="m"?value*3.28084:value/3.28084)}
function chevronCount(err,band){
  const r=Math.abs(err)/band;
  // The configured deviation is the maximum permitted error: one chevron at
  // one-third, two at two-thirds, and all three at or beyond the limit.
  if(r<1/3)return 0;
  if(r<2/3)return 1;
  if(r<1)return 2;
  return 3;
}
function chevronTone(nearVar,farVar,severity){
  const styles=getComputedStyle(document.documentElement);
  const parse=name=>{
    const hex=styles.getPropertyValue(name).trim().replace("#","");
    return hex.length===6?[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16)):null;
  };
  const near=parse(nearVar),far=parse(farVar);
  if(!near||!far)return "var("+farVar+")";
  const t=Math.max(0,Math.min(1,severity)),smooth=t*t*(3-2*t);
  return "#"+near.map((v,i)=>Math.round(v+(far[i]-v)*smooth).toString(16).padStart(2,"0")).join("");
}
function openGlance(){el("glanceModal").classList.add("open");el("glanceBody").appendChild(el("glanceSections"))}
function closeGlance(){el("glanceModal").classList.remove("open");el("normalHome").appendChild(el("glanceSections"))}
function renderFlight(status,capturing){
  document.body.classList.toggle("flight",capturing);
  if(!capturing){closeGlance();el("stopConfirmModal").classList.remove("open");return}
  const s=altSettings();
  const alti=status.altimeter||{},raw=alti.height!==undefined?alti.height:alti.measurement;
  const num=Number(raw);
  const sensorUnit=String(alti.unit||"m").toLowerCase().startsWith("f")?"ft":"m";
  const alt=(raw!==null&&raw!==""&&Number.isFinite(num))?toUnit(num,sensorUnit,s.unit):NaN;
  el("flightAlt").textContent=Number.isFinite(alt)?Math.round(alt).toLocaleString():"--";
  el("flightUnit").textContent=Number.isFinite(alt)?s.unit:"";
  let up=0,down=0,intensity=0,note="";
  if(!Number.isFinite(alt))note="Waiting for altimeter";
  else if(!Number.isFinite(s.target)||s.target<=0)note="Set a target altitude in Setup";
  else{
    const band=s.target*s.devPct/100;
    const err=alt-s.target;
    if(band>0){
      const ratio=Math.abs(err)/band,n=chevronCount(err,band);
      intensity=Math.max(0,Math.min(1,ratio));
      if(err<0)up=n;else down=n;
    }
    note=`Target ${Math.round(s.target).toLocaleString()} ${s.unit} · ±${Math.round(band).toLocaleString()} ${s.unit}`;
  }
  el("flightTarget").textContent=note;
  el("chevUp").style.setProperty("--chev-color",chevronTone("--climb-near","--climb",intensity));
  el("chevDown").style.setProperty("--chev-color",chevronTone("--descend-near","--descend",intensity));
  document.querySelectorAll("#chevUp .fchev").forEach((c,i)=>c.classList.toggle("on",i>=3-up));
  document.querySelectorAll("#chevDown .fchev").forEach((c,i)=>c.classList.toggle("on",i<down));
}
function renderCams(status,images){
  const grid=el("cameraGrid"),states=status.cams||[],counts=Array.isArray(images.imageCount)?images.imageCount:[],copies=Array.isArray(images.copyCount)?images.copyCount:[];
  el("camSummary").textContent=`${states.length} connected`;
  grid.innerHTML="";
  if(!states.length){grid.innerHTML='<p class="empty">No cameras detected.</p>';return}
  states.forEach((state,i)=>{
    const g=good.has(state)?"good":bad.has(state)?"bad":"warn";
    const row=document.createElement("div");row.className="cam-row";
    row.innerHTML=`<div class="cam-left"><span class="dot ${g}"></span><span class="cam-name">Camera ${i+1}</span></div><div class="cam-meta mono">${state} · ${fmt(counts[i],"0")}/${fmt(copies[i],"0")}</div>`;
    grid.appendChild(row);
  });
}
function renderComponents(status){
  const panel=el("componentPanel"),list=el("componentList"),components=status.components||{};
  const order=["cameras","gps","altimeter","storage"];
  const missing=order.map(k=>components[k]).filter(c=>c&&c.connected===false);
  panel.hidden=missing.length===0;
  list.innerHTML="";
  missing.forEach(component=>{
    const item=document.createElement("li");item.className="component-item";
    const dot=document.createElement("span");dot.className="dot warn";dot.setAttribute("aria-hidden","true");
    const message=document.createElement("span");message.textContent=component.message||"Component not connected.";
    item.append(dot,message);list.appendChild(item);
  });
}
function bar(pct){pct=Math.max(0,Math.min(100,pct));return `<div class="track"><div class="fill" style="width:${pct}%"></div></div>`}
function formatFlightTime(seconds){
  const total=Math.max(0,Math.floor(Number(seconds)||0));
  if(total<60)return "< 1 minute";
  const days=Math.floor(total/86400),hours=Math.floor((total%86400)/3600),minutes=Math.floor((total%3600)/60);
  if(days)return `${days}d ${hours}h`;
  if(hours)return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
function flightTimeEstimate(stats,estimate){
  const avg=Number(estimate&&estimate.averageImageBytes),free=Number(estimate&&estimate.freeBytes);
  const interval=Number(stats&&stats.captureInterval),cameras=latest&&Array.isArray(latest.cams)?latest.cams.length:0;
  if(!(avg>0))return {text:"Record images to estimate flight time",ready:false};
  if(!(cameras>0))return {text:"Connect cameras to estimate flight time",ready:false};
  if(!(interval>0)||!(free>0))return {text:"Flight-time estimate unavailable",ready:false};
  return {text:`${formatFlightTime(free*interval/(avg*cameras))} estimated flight time`,ready:true};
}
function renderStorage(stats,estimate){
  const int=stats&&stats.internalStorage,ext=stats&&stats.externalStorage;
  const hasInt=int&&int.freeGB!==undefined,hasExt=ext&&ext.freeGB!==undefined;
  const flight=flightTimeEstimate(stats,estimate);
  el("storageSummary").textContent=flight.ready?flight.text:(hasInt?`${nf(int.usedGB)} / ${nf(int.capacityGB)} GB`:"--");
  let html="";
  html+=`<div class="stor-item"><div class="stor-head"><span class="stor-name">Internal SSD</span><span class="mono stor-val">${hasInt?nf(int.usedGB)+" / "+nf(int.capacityGB)+" GB":"--"}</span></div>${hasInt?bar(int.capacityGB?int.usedGB/int.capacityGB*100:0):'<div class="track dashed"></div>'}<p class="stor-estimate${flight.ready?"":" muted"}">${flight.text}</p></div>`;
  html+=`<div class="stor-item"><div class="stor-head"><span class="stor-name off">External</span><span class="mono stor-val off">${hasExt?nf(ext.usedGB)+" / "+nf(ext.capacityGB)+" GB":"not connected"}</span></div>${hasExt?bar(ext.capacityGB?ext.usedGB/ext.capacityGB*100:0):'<div class="track dashed"></div>'}</div>`;
  el("storageBody").innerHTML=html;
}
function render(status,images){
  latest=status;
  const mode=status.mode||"UNKNOWN",capturing=mode==="STARTED",copying=mode==="COPYING";
  const dot=el("recDot"),txt=el("recText");
  if(capturing){dot.className="rec-dot live";txt.textContent="Recording"}
  else if(bad.has(mode)){dot.className="rec-dot bad";txt.textContent="Error"}
  else if(copying){dot.className="rec-dot";txt.textContent="Copying"}
  else{dot.className="rec-dot";txt.textContent="Standby"}
  el("modeText").textContent=capturing?"Capturing":copying?"Copying":(mode==="READY"||mode==="INITIALISED"?"Ready":"Stopped");
  const captured=sum(images.imageCount),copied=sum(images.copyCount);
  el("statCaptured").textContent=nf(captured);
  el("statSignal").textContent=`${fmt(status.wifiSignal)} dBm`;
  const gpsFix=!!(status.gps&&status.gps.fix),sats=status.gps&&status.gps.satellites;
  const pdop=status.gps&&status.gps.pdop;
  el("statPdop").textContent=gpsFix?`${fmt(pdop)} · Fix`:"No fix";
  const alti=status.altimeter||{},height=alti.height!==undefined?alti.height:alti.measurement;
  const heightNumber=Number(height);
  el("statAltitude").textContent=height!==null&&height!==""&&Number.isFinite(heightNumber)?`${heightNumber.toFixed(1)} ${alti.unit||"m"}`:"--";
  const gpsConnected=status.components&&status.components.gps?status.components.gps.connected:Boolean(status.gps);
  el("deviceGpsSummary").textContent=!gpsConnected?"Not connected":gpsFix?`3D fix · PDOP ${fmt(pdop)}`:"Waiting for fix";
  el("devCams").textContent=(status.cams||[]).length;
  el("gpsFix").textContent=gpsFix?"3D fix":"No fix";
  el("gpsFix").className="badge "+(gpsFix?"live":"idle");
  el("sats").textContent=fmt(sats);
  el("pdop").textContent=fmt(pdop);
  el("snrAvg").textContent=fmt(status.gps&&status.gps.avg);
  const pct=captured>0?copied/captured*100:0;
  el("copySummary").textContent=captured>0?`${pct.toFixed(0)}%`:"idle";
  el("copyFill").style.width=Math.max(0,Math.min(100,pct))+"%";
  el("copyText").textContent=captured>0?`${nf(copied)} of ${nf(captured)} files copied`:(status.progress||"No active copy reported.");
  el("camError").classList.toggle("show",Boolean(status.camError));
  renderComponents(status);
  renderCams(status,images);
  const b=el("captureButton");
  const camerasConnected=status.components&&status.components.cameras?status.components.cameras.connected:(status.cams||[]).length>0;
  b.textContent=capturing?"Stop capture":"Start capture";
  b.className=capturing?"big-btn stop":"big-btn go";
  b.disabled=busy||copying||(!capturing&&!camerasConnected);
  el("conn").textContent=!capturing&&!camerasConnected?"Connect at least one camera to start capture.":"";
  el("flCaptured").textContent=nf(captured);
  el("flSignal").textContent=`${fmt(status.wifiSignal)} dBm`;
  el("flPdop").textContent=gpsFix?`${fmt(pdop)} · Fix`:"No fix";
  el("flightStop").disabled=busy;
  renderFlight(status,capturing);
}
async function poll(){return singleFlight("home-status",async()=>{
  try{
    const [s,i]=await Promise.all([fetchJson("/api/status"),fetchJson("/api/images_captured").catch(()=>({}))]);
    render(s,i);
  }catch(e){
    el("recDot").className="rec-dot bad";el("recText").textContent="Offline";
    el("modeText").textContent="Offline";
    el("conn").textContent="tricap is not reachable on the rig.";el("captureButton").disabled=true;
  }
})}
async function pollStorage(){return singleFlight("home-storage",async()=>{
  const [statsResult,estimateResult]=await Promise.allSettled([
    fetchJson("/api/statistics"),fetchJson("/portal/storage_estimate")
  ]);
  if(statsResult.status==="fulfilled")lastStats=statsResult.value;
  if(estimateResult.status==="fulfilled")lastStorageEstimate=estimateResult.value;
  renderStorage(lastStats||{},lastStorageEstimate||{});
  el("storageNote").textContent=statsResult.status==="fulfilled"?"":"Storage usage refreshes while capture is stopped.";
})}
async function doToggle(control){
  if(!latest||busy)return;
  const capturing=latest.mode==="STARTED";
  const finish=beginAction(control,capturing?"Stopping capture...":"Starting capture...");
  if(!finish)return;
  busy=true;el("captureButton").disabled=true;el("flightStop").disabled=true;
  try{
    if(!capturing)await syncPhoneClock();
    await fetchJson(capturing?"/api/stop_capture":"/api/start_capture");
    toast(capturing?"Capture stopped":"Capture started");
  }
  catch(e){toast(e.message)}finally{busy=false;finish();poll();pollStorage()}
}
function toggle(event){
  if(!latest||busy)return;
  const control=event.currentTarget;
  const starting=latest.mode!=="STARTED";
  if(!starting){
    const finish=beginAction(control,"Opening confirmation...");
    if(!finish)return;
    el("stopConfirmModal").classList.add("open");
    // Wrap finish: rAF passes a timestamp, which finish(keepLoading) would
    // read as "keep the loading toast up", leaving the spinner stuck if the
    // user cancels the stop confirmation.
    requestAnimationFrame(()=>finish());
    return;
  }
  doToggle(control);
}
el("stopConfirmYes").addEventListener("click",event=>{el("stopConfirmModal").classList.remove("open");doToggle(event.currentTarget)});
el("stopConfirmNo").addEventListener("click",()=>el("stopConfirmModal").classList.remove("open"));
el("captureButton").addEventListener("click",toggle);
el("flightStop").addEventListener("click",toggle);
el("glanceOpen").addEventListener("click",openGlance);
el("glanceClose").addEventListener("click",closeGlance);
// Storage (incl. the estimate's NVMe directory walk) pauses while recording so
// it never competes with the cameras for disk I/O; the post-stop manual
// pollStorage() in doToggle refreshes it as soon as capture ends.
runPeriodic(poll,1000);
runPeriodic(()=>latest&&latest.mode==="STARTED"?null:pollStorage(),15000);
'''

SETUP_JS = COMMON_JS + r'''
let currentInterval=null,currentImageFormat=null,capturing=false,backupRunning=false,backupTimer=null,camCount=-1,externalConnected=false;
let verifyRunning=false,verifyTimer=null,verifyAnnounce=false;
let deleteMode="verify",statusFailures=0,jobTick=0;
// Controls stay locked until every poller has answered at least once.
const known={status:false,backup:false,verify:false};
function setControlsEnabled(){
  const unknown=!(known.status&&known.backup&&known.verify);
  const lock=unknown||capturing||backupRunning||verifyRunning;
  document.querySelectorAll("[data-locks]").forEach(b=>{b.disabled=lock||b.dataset.actionBusy==="true"});
  el("lockNote").textContent=unknown?"Checking device status...":lock?"Some controls are disabled while capture or copy is running.":"";
}
function renderImageButtons(n){
  if(n===camCount)return;camCount=n;
  const c=el("imageButtons");c.innerHTML="";
  if(!n){el("imageNote").textContent="No cameras detected. Connect cameras and run a copy, then sample images appear here.";return}
  el("imageNote").textContent="Downloads a representative image from the most recent copy session.";
  for(let i=0;i<n;i++){const b=document.createElement("button");b.className="pill-btn";b.type="button";b.textContent=`Camera ${i+1}`;b.addEventListener("click",()=>downloadImage(i,b));c.appendChild(b)}
}
async function loadSensors(){return singleFlight("setup-status",async()=>{
  try{
    const status=await fetchJson("/api/status"),gps=status.gps||{};
    capturing=(status.mode==="STARTED"||status.mode==="COPYING");
    el("setupMode").textContent=status.mode||"--";
    el("wifi").textContent=`${fmt(status.wifiSignal)} dBm`;
    el("sats").textContent=fmt(gps.satellites);el("pdop").textContent=fmt(gps.pdop);
    const age=Number(gps.lastUpdate);el("age").textContent=Number.isFinite(age)&&age>=0?`${age.toFixed(0)}s`:"--";
    el("snrMin").textContent=fmt(gps.min);el("snrAvg").textContent=fmt(gps.avg);el("snrMax").textContent=fmt(gps.max);
    renderImageButtons((status.cams||[]).length);
    known.status=true;statusFailures=0;
  }catch(e){el("setupMode").textContent="Offline";if(++statusFailures>=3)known.status=false}
  if(!known.backup)pollBackup();
  if(!known.verify)pollVerify();
  // A copy or delete can be started from another phone or tab while this
  // page sits idle, so the job endpoints are re-checked every third tick.
  else if(known.backup&&!capturing&&!backupRunning&&!verifyRunning&&++jobTick%3===0)checkRemoteJobs();
  setControlsEnabled();
})}
// Only a running job is rendered: an idle answer must not overwrite the
// completion message the other poller left on the backup line.
async function checkRemoteJobs(){return singleFlight("job-check",async()=>{
  try{
    const [backup,verify,force]=await Promise.all([fetchJson("/api/backup_status"),fetchJson("/api/verify_and_delete_status"),fetchJson("/api/force_delete_status")]);
    if(force.running||verify.running){deleteMode=force.running?"force":"verify";renderVerify(force.running?force:verify)}
    else if(backup.running)renderBackup(backup);
  }catch(e){}
})}
async function loadStats(){return singleFlight("setup-stats",async()=>{
  try{
    const [stats,lens]=await Promise.all([fetchJson("/api/statistics"),fetchJson("/api/lensNumber").catch(()=>({}))]);
    el("lens").textContent=fmt(lens.lens);
    externalConnected=!!(stats.externalStorage&&Number(stats.externalStorage.capacityGB)>0);
    if(stats.captureInterval!==undefined){currentInterval=Number(stats.captureInterval);el("interval").textContent=currentInterval.toFixed(1)+" s"}
  }catch(e){/* blocked while capturing */}
})}
function renderImageFormat(value){
  currentImageFormat=value;
  [["imageFormatDefault","Default"],["imageFormatRaw","RAW"],["imageFormatJpeg","JPEG"]].forEach(([id,choice])=>{
    const button=el(id),active=value===choice;
    button.className="seg-btn"+(active?" active":"");
    button.setAttribute("aria-pressed",active?"true":"false");
  });
  el("imageFormatValue").textContent=value||"--";
}
async function loadImageFormat(){return singleFlight("setup-image-format",async()=>{
  try{const result=await fetchJson("/api/sony_image_format");renderImageFormat(result.value)}
  catch(e){el("imageFormatValue").textContent="--"}
})}
async function setImageFormat(value,control){
  if(value===currentImageFormat)return;
  const finish=beginAction(control,"Saving image format...");
  if(!finish)return;
  try{
    const result=await postJson("/api/sony_image_format",{value});
    renderImageFormat(result.value);
    toast(`Image format set to ${result.value}`);
  }catch(e){toast(e.message)}
  finally{finish();setControlsEnabled()}
}
async function setIntervalValue(delta,control){
  if(currentInterval===null||Number.isNaN(currentInterval)){toast("Current interval is not available");return}
  const next=Math.max(.1,Math.round((currentInterval+delta)*10)/10);
  const finish=beginAction(control,"Saving capture interval...");
  if(!finish)return;
  try{await postJson("/api/capture_interval",{interval:next});currentInterval=next;el("interval").textContent=currentInterval.toFixed(1)+" s";toast("Capture interval set to "+next.toFixed(1)+"s")}
  catch(e){toast(e.message)}
  finally{finish();setControlsEnabled()}
}
function renderBackup(st){
  const wasRunning=backupRunning,running=!!st.running,pct=Number(st.percent||0);
  backupRunning=running;setControlsEnabled();
  if(verifyRunning)return;
  el("backupFill").style.width=Math.max(0,Math.min(100,pct))+"%";
  let line=st.phase||"Idle";
  if(running){line=`${st.phase||"copying"} - ${pct.toFixed(1)}%`;
    if(st.files_total)line+=` (${st.files_done}/${st.files_total} files)`;
    if(st.eta_seconds>0)line+=` - ETA ${formatDuration(st.eta_seconds)}`;
    loadingToast(`Copying to SSD... ${pct.toFixed(0)}%`);}
  else if(st.message)line=st.message;
  el("backupState").textContent=line;
  if(!running&&st.elapsed_seconds>0){
    const rate=Number(st.throughput_mib_s||0);
    let result=`Plain copy · ${Number(st.elapsed_seconds).toFixed(1)}s`;
    if(rate>0)result+=` · ${rate.toFixed(1)} MiB/s`;
    el("backupBenchmark").textContent=result;
  }
  if(running&&!backupTimer)backupTimer=setInterval(pollBackup,2000);
  if(!running&&backupTimer){clearInterval(backupTimer);backupTimer=null}
  if(wasRunning&&!running)toast(st.message||"Backup complete");
}
async function pollBackup(){return singleFlight("backup-status",async()=>{
  try{const st=await fetchJson("/api/backup_status");known.backup=true;renderBackup(st)}
  catch(e){
    if(backupTimer){clearInterval(backupTimer);backupTimer=null}
    // 400 means the backend refused because capture is running, so no backup can be.
    known.backup=e.status===400;
    if(known.backup)backupRunning=false;
    setControlsEnabled();
  }
})}
function formatDuration(seconds){
  const total=Math.max(0,Math.round(Number(seconds)||0));
  if(total<60)return `${total}s`;
  if(total<3600){const minutes=Math.floor(total/60),secs=total%60;return secs?`${minutes}m ${secs}s`:`${minutes}m`}
  const hours=Math.floor(total/3600),minutes=Math.floor((total%3600)/60);
  return minutes?`${hours}h ${minutes}m`:`${hours}h`;
}
function renderVerify(st){
  const running=!!st.running,total=Number(st.total||0),done=Number(st.completed||0);
  verifyRunning=running;setControlsEnabled();
  const pct=total>0?(done/total)*100:(running?0:100);
  el("backupFill").style.width=Math.max(0,Math.min(100,pct))+"%";
  if(running){
    verifyAnnounce=true;
    const action=st.phase==="deleting"?"Deleting":"Verifying";
    el("backupState").textContent=total?`${action} ${done}/${total} files...`:(st.message||`${action}...`);
    loadingToast(total?`${action} files... ${done}/${total}`:`${action} files...`);
    if(!verifyTimer)verifyTimer=setInterval(pollVerify,1000);
  }else{
    if(st.phase!=="idle"&&st.message)el("backupState").textContent=st.message;
    if(verifyTimer){clearInterval(verifyTimer);verifyTimer=null}
    if(verifyAnnounce&&st.phase!=="idle"){
      toast(st.success?st.message:(st.message||"Verification failed; files were retained"));
      verifyAnnounce=false;
    }
  }
}
async function pollVerify(){return singleFlight("verify-status",async()=>{
  try{
    if(known.verify){
      const path=deleteMode==="force"?"/api/force_delete_status":"/api/verify_and_delete_status";
      renderVerify(await fetchJson(path));
    }else{
      // Either job may already be running from an earlier session.
      const [verify,force]=await Promise.all([fetchJson("/api/verify_and_delete_status"),fetchJson("/api/force_delete_status")]);
      deleteMode=force.running?"force":"verify";
      known.verify=true;
      renderVerify(force.running?force:verify);
    }
  }
  catch(e){if(verifyTimer){clearInterval(verifyTimer);verifyTimer=null}known.verify=false;setControlsEnabled()}
})}
async function startBackup(control){
  const finish=beginAction(control,"Starting backup...");
  if(!finish)return;
  try{
    const r=await fetchJson("/api/backup_start");
    if(r&&r.success===false)toast(r.msg||"Backup failed to start");
    else{backupRunning=true;loadingToast("Copying to SSD...")}
    pollBackup();
  }
  catch(e){toast(e.message)}
  finally{finish(backupRunning);setControlsEnabled()}
}
async function moveBackup(control){
  const finish=beginAction(control,"Starting copy & delete...");
  if(!finish)return;
  el("moveConfirmModal").classList.remove("open");
  try{
    const r=await fetchJson("/api/backup_move");
    if(r&&r.success===false)toast(r.msg||"Copy & delete failed to start");
    else{backupRunning=true;loadingToast("Moving to SSD...")}
    pollBackup();
  }
  catch(e){toast(e.message)}
  finally{finish(backupRunning);setControlsEnabled()}
}
function openDeleteDialog(){
  el("deleteDecisionTitle").textContent=externalConnected?"Clear internal storage?":"External SSD not connected";
  el("deleteDecisionText").textContent=externalConnected
    ?"Verify the SSD copy and delete only matched files. If you continue without verification, all images and logs on internal storage will be permanently deleted and may not be backed up."
    :"The internal files cannot be verified and may not be backed up. Continuing permanently deletes all images and logs from internal storage. This cannot be undone.";
  el("deleteDecisionVerify").hidden=!externalConnected;
  el("deleteDecisionModal").classList.add("open");
}
async function deleteBackup(control){
  const finish=beginAction(control,"Checking storage...");
  if(!finish)return;
  try{
    const stats=await fetchJson("/api/statistics");
    externalConnected=!!(stats.externalStorage&&Number(stats.externalStorage.capacityGB)>0);
  }catch(e){/* use the most recent storage state */}
  openDeleteDialog();
  finish();setControlsEnabled();
}
async function verifyDeleteMatched(control){
  const finish=beginAction(control,"Starting verification...");
  if(!finish)return;
  el("deleteDecisionModal").classList.remove("open");
  try{
    deleteMode="verify";
    const r=await fetchJson("/api/verify_and_delete");
    if(r&&r.success){verifyRunning=true;verifyAnnounce=true;setControlsEnabled();el("backupState").textContent="Preparing verification...";pollVerify()}
    else toast((r&&r.msg)||"Verification could not be started");
  }
  catch(e){
    if(e.data&&e.data.code==="external_not_connected"){externalConnected=false;openDeleteDialog()}
    else toast(e.message);
  }
  finally{finish(verifyRunning);setControlsEnabled()}
}
async function forceDeleteAll(control){
  const finish=beginAction(control,"Clearing internal storage...");
  if(!finish)return;
  el("deleteDecisionModal").classList.remove("open");
  try{
    deleteMode="force";
    const r=await postJson("/api/force_delete",{confirmation:"delete-unbacked-internal-data"});
    if(r&&r.success){verifyRunning=true;verifyAnnounce=true;setControlsEnabled();el("backupState").textContent="Preparing to clear internal storage...";pollVerify()}
    else toast((r&&r.msg)||"Internal storage could not be cleared");
  }catch(e){toast(e.message)}
  finally{finish(verifyRunning);setControlsEnabled()}
}
async function netbirdStatus(announce){
  try{const r=await fetchJson("/api/netbird_status");const ok=!!r.connected;
    el("nbDot").className="dot "+(ok?"good":"off");el("nbState").textContent=ok?"Available":"Off";
    if(announce)toast(ok?"Remote support is available":"Remote support is off");}
  catch(e){el("nbDot").className="dot bad";el("nbState").textContent="Unavailable";if(announce)toast(e.message)}
}
async function downloadImage(idx,control){
  const name=`Camera ${idx+1}`;
  const finish=beginAction(control,`Preparing ${name} sample...`);
  if(!finish)return;
  try{const r=await fetch(`/api/get_images/${idx}`,{cache:"no-store"});
    if(r.status===404){toast(`No sample image for ${name} yet (run a copy first).`);return}
    if(!r.ok)throw new Error(`${r.status} ${r.statusText}`);
    const blob=await r.blob(),serverName=r.headers.get("X-SkySeeker-Filename");
    downloadBlob(blob,serverName||`camera${idx+1}_sample`);toast(`Downloading ${name} sample`);}
  catch(e){toast(e.message)}
  finally{finish()}
}
document.querySelectorAll("[data-delta]").forEach(b=>b.addEventListener("click",()=>setIntervalValue(Number(b.dataset.delta),b)));
el("imageFormatDefault").addEventListener("click",event=>setImageFormat("Default",event.currentTarget));
el("imageFormatRaw").addEventListener("click",event=>setImageFormat("RAW",event.currentTarget));
el("imageFormatJpeg").addEventListener("click",event=>setImageFormat("JPEG",event.currentTarget));
el("restartService").addEventListener("click",async event=>{if(!confirm("Restart the tricap capture service? Capture pauses briefly."))return;const finish=beginAction(event.currentTarget,"Restarting tricap...");if(!finish)return;try{await fetchJson("/api/restart");toast("tricap restart requested")}catch(e){toast(e.message)}finally{finish();setControlsEnabled()}});
el("rebootDevice").addEventListener("click",async event=>{if(!confirm("Reboot the SkySeeker device? It will be offline for ~30-60s and you may need to rejoin Wi-Fi."))return;const finish=beginAction(event.currentTarget,"Requesting reboot...");if(!finish)return;try{await fetchJson("/api/reboot");toast("Reboot requested - rejoin skyseeker when it returns")}catch(e){toast(e.message)}finally{finish();setControlsEnabled()}});
el("backupStart").addEventListener("click",event=>startBackup(event.currentTarget));
el("backupMove").addEventListener("click",()=>el("moveConfirmModal").classList.add("open"));
el("moveConfirmContinue").addEventListener("click",event=>moveBackup(event.currentTarget));
el("moveConfirmCancel").addEventListener("click",()=>el("moveConfirmModal").classList.remove("open"));
el("backupDelete").addEventListener("click",event=>deleteBackup(event.currentTarget));
el("deleteDecisionCancel").addEventListener("click",()=>el("deleteDecisionModal").classList.remove("open"));
el("deleteDecisionVerify").addEventListener("click",event=>verifyDeleteMatched(event.currentTarget));
el("deleteDecisionContinue").addEventListener("click",event=>forceDeleteAll(event.currentTarget));
el("nbConnect").addEventListener("click",async event=>{const finish=beginAction(event.currentTarget,"Connecting remote support...");if(!finish)return;try{await postJson("/api/netbird_connect",{});await netbirdStatus(true)}catch(e){toast(e.message)}finally{finish()}});
el("nbDisconnect").addEventListener("click",async event=>{if(!confirm("Turn off remote support? Support will not be able to reach this rig until it is reconnected."))return;const finish=beginAction(event.currentTarget,"Turning off remote support...");if(!finish)return;try{await postJson("/api/netbird_disconnect",{});await netbirdStatus(true)}catch(e){toast(e.message)}finally{finish()}});
async function uplinkStatus(){
  try{
    const r=await fetchJson("/portal/uplink_status");
    if(!r.available){el("ulDot").className="dot off";el("ulState").textContent="--";el("ulDetail").textContent=r.msg||"Uplink control is not available on this build.";return}
    const on=!!r.connected;
    el("ulDot").className="dot "+(on?"good":"off");
    el("ulState").textContent=on?"Online":"Offline";
    el("ulDetail").textContent=on
      ?`${r.ssid||r.connection} · ${r.ip||"no IP"} · ${r.signal!==undefined?r.signal+" dBm":"--"} · internet: ${r.connectivity||"unknown"}`
      :"Phone recovery hotspot not found. The USB skyseeker network remains available for local control.";
  }catch(e){el("ulDot").className="dot bad";el("ulState").textContent="--"}
}
async function connectUplink(custom){
  const b=el(custom?"ulConnectCustom":"ulConnect"),finish=beginAction(b,"Connecting internet...");
  if(!finish)return;
  try{
    const body={};
    if(custom){
      const s=el("ulSsid").value.trim(),p=el("ulPsk").value;
      if(!s)throw new Error("Enter a hotspot name");
      body.ssid=s;if(p)body.psk=p;
    }
    const r=await postJson("/portal/uplink_connect",body);
    toast(r.msg||"Internet connected");uplinkStatus();
  }catch(e){toast(e.message)}
  finally{finish()}
}
el("ulConnect").addEventListener("click",()=>connectUplink(false));
el("ulConnectCustom").addEventListener("click",()=>connectUplink(true));
el("ulDisconnect").addEventListener("click",async event=>{
  if(!confirm("Disconnect SkySeeker from the phone hotspot? The dashboard remains available through the USB skyseeker Wi-Fi network."))return;
  const finish=beginAction(event.currentTarget,"Disconnecting internet...");
  if(!finish)return;
  try{const r=await postJson("/portal/uplink_disconnect");toast(r.msg||"Internet disconnected");uplinkStatus()}
  catch(e){toast(e.message)}
  finally{finish()}
});
function altUnit(){let u="ft";try{u=localStorage.getItem("ss-alt-unit")||"ft"}catch(_){}return u==="m"?"m":"ft"}
function renderAltBand(){
  const t=parseFloat(el("altTarget").value),d=parseFloat(el("altDev").value),u=altUnit();
  el("unitFt").className="seg-btn"+(u==="ft"?" active":"");
  el("unitM").className="seg-btn"+(u==="m"?" active":"");
  el("altBand").textContent=(Number.isFinite(t)&&t>0&&Number.isFinite(d)&&d>0)?`±${Math.round(t*d/100).toLocaleString()} ${u}`:"--";
}
function saveAltCfg(){
  try{
    localStorage.setItem("ss-alt-target",el("altTarget").value);
    localStorage.setItem("ss-alt-dev",el("altDev").value);
  }catch(_){}
  renderAltBand();
}
function setAltUnit(u){try{localStorage.setItem("ss-alt-unit",u)}catch(_){}renderAltBand()}
(function(){
  let t="",d="";
  try{t=localStorage.getItem("ss-alt-target")||"";d=localStorage.getItem("ss-alt-dev")||""}catch(_){}
  el("altTarget").value=t;
  el("altDev").value=d!==""?d:"5";
  if(d==="")saveAltCfg();else renderAltBand();
})();
el("altTarget").addEventListener("input",saveAltCfg);
el("altDev").addEventListener("input",saveAltCfg);
el("unitFt").addEventListener("click",()=>setAltUnit("ft"));
el("unitM").addEventListener("click",()=>setAltUnit("m"));
function applyTheme(t,persist){
  document.documentElement.setAttribute("data-theme",t);
  if(persist){try{localStorage.setItem("ss-theme",t)}catch(e){}}
  el("themeVal").textContent=t==="default"?"Default":t==="dark"?"Dark":"Light";
  el("themeDefault").className="seg-btn"+(t==="default"?" active":"");
  el("themeLight").className="seg-btn"+(t==="light"?" active":"");
  el("themeDark").className="seg-btn"+(t==="dark"?" active":"");
}
el("themeDefault").addEventListener("click",()=>applyTheme("default",true));
el("themeLight").addEventListener("click",()=>applyTheme("light",true));
el("themeDark").addEventListener("click",()=>applyTheme("dark",true));
applyTheme(["default","light","dark"].includes(document.documentElement.getAttribute("data-theme"))?document.documentElement.getAttribute("data-theme"):"default",false);
// While capture (or copy) is running the page is locked out, so everything
// except the status poll pauses; the status poll slows to 5 s and keeps
// running only so the page notices capture ended and re-enables. The
// netbird/uplink manual refreshes after connect/disconnect stay unwrapped so
// a user action always gets a fresh result.
runPeriodic(loadSensors,()=>capturing?5000:2000);
runPeriodic(()=>capturing?null:loadStats(),15000);
runPeriodic(()=>capturing?null:loadImageFormat(),15000);
runPeriodic(()=>capturing?null:singleFlight("setup-netbird",()=>netbirdStatus(false)),20000);
runPeriodic(()=>capturing?null:singleFlight("setup-uplink",uplinkStatus),10000);
'''

# No external font <link>: the rig is an offline field AP with no internet, so a
# Google Fonts request would only stall page load. The font stack in STYLE names
# 'Archivo'/'IBM Plex Mono' first (used if the operator's device has them) and
# falls back to system sans/mono otherwise.
_HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
         # Set the theme before first paint so the branded default does not flash white.
         '<script>(function(){var t=null;try{t=localStorage.getItem("ss-theme")}catch(e){}'
         'document.documentElement.setAttribute("data-theme",["default","light","dark"].indexOf(t)>-1?t:"default");})()</script>')

LOGO_WHITE_DATA_URI = "data:image/png;base64,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"
LOGO_BLACK_DATA_URI = "data:image/png;base64,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"


def _appbar():
    return (
        '<header class="appbar">'
        '<a class="brand" href="/" aria-label="SkySeeker home">'
        f'<img class="brand-logo logo-light" src="{LOGO_BLACK_DATA_URI}" alt="SkySeeker">'
        f'<img class="brand-logo logo-dark" src="{LOGO_WHITE_DATA_URI}" alt="" aria-hidden="true">'
        '<span class="wordmark">SkySeeker</span></a>'
        '<span class="host mono" id="host">control.skyseeker</span>'
        '</header>'
    )


def _bottomnav(active):
    home_cls = "navitem active" if active == "home" else "navitem"
    setup_cls = "navitem active" if active == "setup" else "navitem"
    home_ico = '<svg class="nav-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11.5 12 4l9 7.5"></path><path d="M5.5 10.5V20h13v-9.5"></path><path d="M9.5 20v-5h5v5"></path></svg>'
    setup_ico = '<svg class="nav-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M14.7 6.3a4 4 0 0 0-5 5L3.8 17.2a1.8 1.8 0 0 0 2.5 2.5l5.9-5.9a4 4 0 0 0 5-5l-2.7 2.7-2-2 2.2-3.2Z"></path></svg>'
    return (
        '<nav class="bottomnav" aria-label="Main">'
        f'<a class="{home_cls}" href="/" aria-label="Home">{home_ico}<span class="nav-label">Home</span></a>'
        f'<a class="{setup_cls}" href="/setup" aria-label="Setup">{setup_ico}<span class="nav-label">Setup</span></a>'
        '</nav>'
    )


HOME_HTML = f'''{_HEAD}<title>SkySeeker Control</title><style>{STYLE}</style></head><body><div class="app">{_appbar()}<main class="content">
<div class="notice" id="camError">Camera error detected. Check camera states before flying.</div>
<section class="component-panel" id="componentPanel" hidden aria-live="polite" aria-atomic="true">
  <div class="component-title">Limited configuration</div>
  <ul class="component-list" id="componentList"></ul>
</section>
<div id="normalHome" class="home-stack">
<section class="card status-card">
  <div class="status-top"><div class="kicker">Capture status</div><div class="rec"><span class="rec-dot" id="recDot"></span><span class="rec-text" id="recText">--</span></div></div>
  <div class="mode-text" id="modeText">--</div>
  <div class="statgrid">
    <div class="stat"><div class="stat-val mono" id="statCaptured">--</div><div class="stat-label">Captured</div></div>
    <div class="stat"><div class="stat-val mono" id="statSignal">-- dBm</div><div class="stat-label">Signal</div></div>
    <div class="stat"><div class="stat-val mono" id="statPdop">--</div><div class="stat-label">PDOP</div></div>
    <div class="stat"><div class="stat-val mono" id="statAltitude">--</div><div class="stat-label">Altitude</div></div>
  </div>
  <button class="big-btn go" id="captureButton" type="button">Start capture</button>
  <p class="conn-note" id="conn"></p>
</section>
<div class="section-label">Rig status</div>
<div id="glanceSections" class="home-stack">
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Cameras</div><div class="acc-right"><span class="acc-sum mono" id="camSummary">-- active</span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div class="cam-list" id="cameraGrid"></div></div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Storage</div><div class="acc-right"><span class="acc-sum mono" id="storageSummary">--</span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div id="storageBody"></div><p class="muted small" id="storageNote"></p></div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Device &amp; GPS</div><div class="acc-right"><span class="acc-sum mono strong" id="deviceGpsSummary">--</span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body">
    <div class="subhead">Device</div>
    <div class="mgrid">
      <div class="m-item"><div class="m-label">Address</div><div class="m-value mono" id="host2">control.skyseeker</div></div>
      <div class="m-item"><div class="m-label">Cameras</div><div class="m-value mono" id="devCams">0</div></div>
    </div>
    <div class="subhead row-between"><span>GPS signal</span><span class="badge idle" id="gpsFix">--</span></div>
    <div class="mgrid">
      <div class="m-item"><div class="m-label">Satellites</div><div class="m-value mono" id="sats">--</div></div>
      <div class="m-item"><div class="m-label">PDOP</div><div class="m-value mono" id="pdop">--</div></div>
      <div class="m-item"><div class="m-label">SNR avg</div><div class="m-value mono" id="snrAvg">--</div></div>
    </div>
  </div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Copy progress</div><div class="acc-right"><span class="acc-sum mono strong" id="copySummary">idle</span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div class="progress-track"><div class="progress-fill" id="copyFill"></div></div><p class="muted small" id="copyText" style="margin-top:8px">No active copy reported.</p></div>
</section>
</div>
</div>
<section class="flight-view" id="flightView">
  <div class="flight-top"><div class="kicker">Capture status</div><div class="rec"><span class="rec-dot live"></span><span class="rec-text">Recording</span></div></div>
  <div class="flight-main">
    <div class="chev-stack up" id="chevUp">{FCHEV_UP}{FCHEV_UP}{FCHEV_UP}</div>
    <div class="flight-alt"><span id="flightAlt">--</span><span class="unit" id="flightUnit"></span></div>
    <div class="flight-target" id="flightTarget"></div>
    <div class="chev-stack down" id="chevDown">{FCHEV_DOWN}{FCHEV_DOWN}{FCHEV_DOWN}</div>
  </div>
  <div class="flight-stats">
    <div class="stat"><div class="stat-val mono" id="flCaptured">--</div><div class="stat-label">Captured</div></div>
    <div class="stat"><div class="stat-val mono" id="flSignal">-- dBm</div><div class="stat-label">Signal</div></div>
    <div class="stat"><div class="stat-val mono" id="flPdop">--</div><div class="stat-label">PDOP</div></div>
  </div>
  <div class="flight-actions">
    <button class="flight-stop-btn" id="flightStop" type="button">Stop capture</button>
    <button class="glance-bar" id="glanceOpen" type="button">Rig status</button>
  </div>
</section>
</main>{_bottomnav("home")}</div>
<div class="consent-modal" id="stopConfirmModal" role="dialog" aria-modal="true" aria-label="Stop capture confirmation">
  <div class="consent-card">
    <div class="consent-title">Stop capture?</div>
    <p class="consent-text">This ends the current capture session.</p>
    <button class="big-btn stop" id="stopConfirmYes" type="button">Stop capture</button>
    <button class="consent-cancel" id="stopConfirmNo" type="button">Keep capturing</button>
  </div>
</div>
<div class="glance-modal" id="glanceModal" role="dialog" aria-modal="true" aria-label="Rig status">
  <div class="glance-modal-head"><div class="glance-modal-title">Rig status</div><button class="glance-close" id="glanceClose" type="button">&#10005;&ensp;Close</button></div>
  <div class="glance-modal-body" id="glanceBody"></div>
</div>
<div class="connection-warning" id="connectionWarning" role="alert" aria-live="assertive">
  <div class="connection-warning-inner"><div class="connection-warning-title">Connection lost</div><p class="connection-warning-text">Reconnect this screen to the skyseeker Wi-Fi network immediately.</p></div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<script>document.getElementById("host2").textContent=location.host||"control.skyseeker";</script>
<script>{HOME_JS}</script>
</body></html>'''

SETUP_HTML = f'''{_HEAD}<title>SkySeeker Setup</title><style>{STYLE}</style></head><body><div class="app">{_appbar()}<main class="content">
<p class="lock-note" id="lockNote">Checking device status...</p>
<div class="section-label">Setup · most used</div>
<section class="card pad">
  <div class="row-between mb"><div class="card-h">Capture interval</div><div class="interval-val mono" id="interval">--</div></div>
  <div class="grid2">
    <button class="step-btn mono" type="button" data-delta="-0.5" data-locks disabled>−0.5</button>
    <button class="step-btn mono" type="button" data-delta="-0.1" data-locks disabled>−0.1</button>
    <button class="step-btn mono" type="button" data-delta="0.1" data-locks disabled>+0.1</button>
    <button class="step-btn mono" type="button" data-delta="0.5" data-locks disabled>+0.5</button>
  </div>
</section>
<section class="card pad">
  <div class="row-between mb"><div class="card-h">Camera image format</div><div class="theme-val mono" id="imageFormatValue">--</div></div>
  <div class="seg" role="group" aria-label="Camera image format">
    <button class="seg-btn" id="imageFormatDefault" type="button" data-locks disabled>Default</button>
    <button class="seg-btn" id="imageFormatRaw" type="button" data-locks disabled>RAW</button>
    <button class="seg-btn" id="imageFormatJpeg" type="button" data-locks disabled>JPEG</button>
  </div>
  <p class="muted small mt">Default leaves each camera at the image format selected on the camera.</p>
</section>
<section class="card pad">
  <div class="row-between mb"><div class="card-h">Flight altitude</div><div class="interval-val mono" id="altBand">--</div></div>
  <div class="nb-field"><input class="text-input mono" id="altTarget" name="flight-target-altitude" type="number" inputmode="decimal" min="0" placeholder="Target altitude" autocomplete="off"></div>
  <div class="grid2 mt">
    <div class="nb-field"><label class="input-suffix"><input class="text-input mono" id="altDev" name="flight-deviation-percent" type="number" inputmode="decimal" min="0" max="100" step="0.5" placeholder="Deviation" autocomplete="off"><span class="input-suffix-mark" aria-hidden="true">%</span></label></div>
    <div class="seg"><button class="seg-btn" id="unitFt" type="button">ft</button><button class="seg-btn" id="unitM" type="button">m</button></div>
  </div>
  <p class="muted small mt">The deviation is the maximum permitted error. One and two chevrons appear as altitude approaches that limit; all three appear at or beyond it.</p>
</section>
<section class="card pad">
  <div class="card-h mb">Backup to SSD</div>
  <p class="muted small" style="margin:0 0 12px">Copies images together with GPS and altitude CSV logs.</p>
  <div class="grid2">
    <button class="go-btn" id="backupStart" type="button" data-locks disabled>Start backup</button>
    <button class="danger-btn" id="backupDelete" type="button" data-locks disabled>Verify &amp; delete</button>
  </div>
  <button class="danger-btn mt" id="backupMove" type="button" data-locks disabled style="width:100%">Copy &amp; delete</button>
  <div class="progress-track mt"><div class="progress-fill" id="backupFill"></div></div>
  <p class="muted small" id="backupState" style="margin-top:8px">Idle</p>
  <p class="benchmark-line mono" id="backupBenchmark">No benchmark recorded this session.</p>
</section>
<div class="section-label">More</div>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Download images</div><div class="acc-right"><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div class="grid3" id="imageButtons"></div><p class="muted small" id="imageNote" style="margin-top:10px">Downloads a representative image from the most recent copy session.</p></div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Sensor check</div><div class="acc-right"><span class="acc-sum mono" id="setupMode">--</span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div class="mgrid">
    <div class="m-item"><div class="m-label">Wi-Fi</div><div class="m-value mono" id="wifi">-- dBm</div></div>
    <div class="m-item"><div class="m-label">Satellites</div><div class="m-value mono" id="sats">--</div></div>
    <div class="m-item"><div class="m-label">PDOP</div><div class="m-value mono" id="pdop">--</div></div>
    <div class="m-item"><div class="m-label">GPS age</div><div class="m-value mono" id="age">--</div></div>
    <div class="m-item"><div class="m-label">SNR min</div><div class="m-value mono" id="snrMin">--</div></div>
    <div class="m-item"><div class="m-label">SNR avg</div><div class="m-value mono" id="snrAvg">--</div></div>
    <div class="m-item"><div class="m-label">SNR max</div><div class="m-value mono" id="snrMax">--</div></div>
    <div class="m-item"><div class="m-label">Lens</div><div class="m-value mono" id="lens">--</div></div>
  </div></div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Download logs</div><div class="acc-right"><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body"><div class="grid3">
    <a class="pill-btn" href="/api/download_logs">Main</a>
    <a class="pill-btn" href="/api/download_imu_logs">IMU</a>
    <a class="pill-btn" href="/portal/flight_log">GPS + altitude</a>
  </div></div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Restart</div><div class="acc-right"><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body">
    <div class="grid2"><button class="pill-btn" id="restartService" type="button" data-locks disabled>Tricap service</button><button class="danger-btn" id="rebootDevice" type="button" data-locks disabled>Reboot device</button></div>
    <p class="muted small mt">&ldquo;Tricap service&rdquo; restarts capture only. &ldquo;Reboot device&rdquo; power-cycles the whole rig.</p>
  </div>
</section>
<section class="card acc">
  <div class="acc-head"><div class="acc-title">Connectivity</div><div class="acc-right"><span class="acc-sum"><span class="dot off" id="ulDot"></span><span class="mono" id="ulState">--</span></span><span class="chev">{CHEV}</span></div></div>
  <div class="acc-body">
    <div class="subhead">Internet connection</div>
    <p class="muted small" style="margin:0 0 10px">The USB Wi-Fi adapter serves <span class="mono">skyseeker</span> for local control. The onboard radio periodically searches for the phone's <span class="mono">skyseeker-rescue</span> recovery hotspot.</p>
    <p class="muted small" id="ulDetail"></p>
    <button class="pill-btn" id="ulConnect" type="button">Reconnect internet</button>
    <div class="subhead row-between"><span>Remote support</span><span class="acc-sum"><span class="dot off" id="nbDot"></span><span class="mono" id="nbState">--</span></span></div>
    <p class="muted small" style="margin:0 0 12px">Remote support becomes available automatically whenever the rig has internet access. No action is normally required.</p>
    <div class="grid2"><button class="pill-btn" id="nbConnect" type="button">Reconnect support</button><button class="pill-btn" id="nbDisconnect" type="button">Turn off support</button></div>
    <details class="advanced">
      <summary>Advanced connection options</summary>
      <p class="muted small" style="margin:0 0 10px">Use a different hotspot temporarily, or disconnect the internet uplink.</p>
      <div class="nb-field"><input class="text-input mono" id="ulSsid" type="text" placeholder="Different hotspot name" autocomplete="off" spellcheck="false"></div>
      <div class="nb-field mt"><input class="text-input mono" id="ulPsk" type="password" placeholder="Hotspot password" autocomplete="new-password" spellcheck="false"></div>
      <div class="grid2 mt"><button class="pill-btn" id="ulConnectCustom" type="button">Use different hotspot</button><button class="pill-btn" id="ulDisconnect" type="button">Disconnect internet</button></div>
    </details>
  </div>
</section>
<div class="section-label">Appearance</div>
<section class="card pad">
  <div class="row-between mb"><div class="card-h">Theme</div><div class="theme-val mono" id="themeVal">Default</div></div>
  <div class="seg"><button class="seg-btn" id="themeDefault" type="button">Default</button><button class="seg-btn" id="themeLight" type="button">Light</button><button class="seg-btn" id="themeDark" type="button">Dark</button></div>
</section>
</main>{_bottomnav("setup")}</div>
<div class="consent-modal" id="moveConfirmModal" role="dialog" aria-modal="true" aria-labelledby="moveConfirmTitle">
  <div class="consent-card">
    <div class="consent-title" id="moveConfirmTitle">Copy &amp; delete?</div>
    <p class="consent-text">Copies files to the SSD and deletes each one from internal storage once its transfer is verified. Files that cannot be verified are retained.</p>
    <div style="display:flex;flex-direction:column;gap:10px">
      <button class="danger-btn" id="moveConfirmContinue" type="button">Copy &amp; delete</button>
      <button class="consent-cancel" id="moveConfirmCancel" type="button">Cancel</button>
    </div>
  </div>
</div>
<div class="consent-modal" id="deleteDecisionModal" role="dialog" aria-modal="true" aria-labelledby="deleteDecisionTitle">
  <div class="consent-card">
    <div class="consent-title" id="deleteDecisionTitle">Clear internal storage?</div>
    <p class="consent-text" id="deleteDecisionText">Choose how to clear internal storage.</p>
    <div style="display:flex;flex-direction:column;gap:10px">
      <button class="go-btn" id="deleteDecisionVerify" type="button">Verify backup and delete matched files</button>
      <button class="danger-btn" id="deleteDecisionContinue" type="button">Continue, delete everything</button>
      <button class="consent-cancel" id="deleteDecisionCancel" type="button">Keep data</button>
    </div>
  </div>
</div>
<div class="connection-warning" id="connectionWarning" role="alert" aria-live="assertive">
  <div class="connection-warning-inner"><div class="connection-warning-title">Connection lost</div><p class="connection-warning-text">Reconnect this screen to the skyseeker Wi-Fi network immediately.</p></div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<script>{SETUP_JS}</script>
</body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = "SkySeekerPortal/1.9"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Permissions-Policy", "geolocation=()")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), ctype="application/json")

    def _redirect(self, path="/"):
        self._send(302, b"", headers={"Location": "http://%s%s" % (self.server.public_host, path)})

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else None

    def _client_ip(self):
        try:
            return self.client_address[0]
        except Exception:
            return None

    def _status_patched(self):
        """Proxy /api/status, then fill wifiSignal from the AP station signal."""
        body = self._body()
        headers = {}
        for key, value in self.headers.items():
            low = key.lower()
            if low in HOP_BY_HOP or low == "host":
                continue
            headers[key] = value
        headers["Host"] = f"{self.server.tricap_host}:{self.server.tricap_port}"
        headers["X-SkySeeker-Client-IP"] = self._client_ip() or ""
        conn = http.client.HTTPConnection(self.server.tricap_host, self.server.tricap_port, timeout=PROXY_TIMEOUT_SEC)
        try:
            conn.request(self.command, "/api/status", body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            ctype = resp.getheader("Content-Type", "application/json")
            if resp.status == 200 and "json" in (ctype or "").lower():
                try:
                    data = json.loads(raw.decode("utf-8"))
                    if not data.get("wifiSignal"):
                        sig = ap_wifi_signal(self._client_ip())
                        if sig is not None:
                            data["wifiSignal"] = sig
                    data.setdefault("components", {})["wifi"] = {
                        "connected": True,
                        "state": "connected",
                        "message": "Wi-Fi access point connected.",
                    }
                    self._json(200, data)
                    return
                except (ValueError, UnicodeDecodeError):
                    pass
            # Pass through whatever tricap said if we couldn't patch.
            self._send(resp.status, raw, ctype=ctype)
        except (ConnectionError, TimeoutError, socket.timeout, OSError) as exc:
            self._json(502, {"msg": "tricap is not reachable", "detail": str(exc)})
        finally:
            conn.close()

    def _proxy(self):
        body = self._body()
        headers = {}
        for key, value in self.headers.items():
            low = key.lower()
            if low in HOP_BY_HOP or low == "host":
                continue
            headers[key] = value
        headers["Host"] = f"{self.server.tricap_host}:{self.server.tricap_port}"
        headers["X-Forwarded-Host"] = self.headers.get("Host", PORTAL_HOST)
        headers["X-Forwarded-Proto"] = "http"
        headers["X-SkySeeker-Client-IP"] = self._client_ip() or ""
        conn = http.client.HTTPConnection(self.server.tricap_host, self.server.tricap_port, timeout=PROXY_TIMEOUT_SEC)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status, resp.reason)
            sent_cache = False
            for key, value in resp.getheaders():
                if key.lower() in HOP_BY_HOP:
                    continue
                if key.lower() == "cache-control":
                    sent_cache = True
                self.send_header(key, value)
            if not sent_cache:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (ConnectionError, TimeoutError, socket.timeout, OSError) as exc:
            self._json(502, {"msg": "tricap is not reachable", "detail": str(exc), "target": f"http://{self.server.tricap_host}:{self.server.tricap_port}"})
        finally:
            conn.close()

    def _route(self):
        path = urlparse(self.path).path
        if path in ("/", "/index", "/index.html"):
            self._send(200, HOME_HTML)
        elif path == "/setup":
            self._send(200, SETUP_HTML)
        elif path == "/favicon.ico":
            self._send(204, b"", ctype="image/x-icon")
        elif path == "/healthz":
            self._json(200, {"ok": True, "proxy": f"http://{self.server.tricap_host}:{self.server.tricap_port}"})
        elif path == "/portal/uplink_status":
            self._json(200, uplink_status())
        elif path == "/portal/storage_estimate":
            self._json(200, storage_image_sample())
        elif path == "/portal/uplink_connect" and self.command == "POST":
            payload = {}
            body = self._body()
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    payload = {}
            ok, msg = uplink_connect(payload.get("ssid") or None, payload.get("psk") or None)
            self._json(200 if ok else 500, {"success": ok, "msg": msg})
        elif path == "/portal/uplink_disconnect" and self.command == "POST":
            ok, msg = uplink_disconnect()
            self._json(200 if ok else 500, {"success": ok, "msg": msg})
        elif path == "/portal/flight_log":
            day, payload = flight_log_for_today()
            if payload is None:
                self._json(404, {"msg": "No flight log recorded today."})
            else:
                self._send(200, payload, ctype="text/csv; charset=utf-8",
                           headers={"Content-Disposition": f'attachment; filename="flightData_{day}.csv"'})
        elif path == "/api/status":
            self._status_patched()
        elif any(path == prefix or path.startswith(prefix) for prefix in PROXY_PREFIXES):
            self._proxy()
        elif path in CAPTIVE_PROBE_PATHS:
            self._redirect()
        else:
            self._redirect()

    def do_GET(self):
        self._route()

    def do_HEAD(self):
        self._route()

    def do_POST(self):
        self._route()


class PortalServer(ThreadingHTTPServer):
    # Sized for the worst-case simultaneous rejoin after an AP drop: ~10
    # connections per device (OS captive-portal probes + parallel browser
    # sockets) x 4 devices, plus a buffer of 10. The stdlib default of 5 can
    # be overflowed by a single reconnecting phone.
    request_queue_size = 50
    daemon_threads = True
    block_on_close = False

    def __init__(
        self, addr, handler, tricap_host, tricap_port,
        public_host=PORTAL_HOST,
    ):
        super().__init__(addr, handler)
        self.tricap_host = tricap_host
        self.tricap_port = tricap_port
        self.public_host = public_host


def main():
    parser = argparse.ArgumentParser(description="SkySeeker standalone control + captive portal")
    parser.add_argument("--port", type=int, default=8088, help="listen port (80 on the rig)")
    parser.add_argument("--host", default="0.0.0.0", help="bind address")
    parser.add_argument("--tricap-host", default=DEFAULT_TRICAP_HOST, help="tricap API host")
    parser.add_argument("--tricap-port", type=int, default=DEFAULT_TRICAP_PORT, help="tricap API port")
    parser.add_argument("--public-host", default=PORTAL_HOST, help="hostname advertised in redirects")
    args = parser.parse_args()
    server = PortalServer(
        (args.host, args.port), Handler, args.tricap_host, args.tricap_port,
        public_host=args.public_host,
    )
    print("SkySeeker portal listening on http://%s:%d/ and proxying tricap at http://%s:%d" % (args.host, args.port, args.tricap_host, args.tricap_port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
