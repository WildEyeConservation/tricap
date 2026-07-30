#!/usr/bin/env python3
"""skyseeker-diag - out-of-band field status page for the tricap Rock Pi rig.

Served over the always-on 'SkySeeker' rescue access point so you can see *why* a
unit will not join the ESS-ops hotspot, even when its hotspot link is completely
down. Connect a phone/laptop to the SkySeeker AP and open http://192.168.50.1:8080/

This is READ-ONLY: it only reports state, it never changes the network. It runs
as its own systemd service (skyseeker-diag), independent of tricap, so the page
still answers even if tricap itself has crashed. Uses only the Python standard
library so it cannot break from a missing pip package after a re-flash.
"""
import html
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080  # apache2 already owns :80 on these units, so use a dedicated port
# iw / iwgetid / nmcli live in /usr/sbin, which is off the rock user's PATH; the
# service runs as root but we set an explicit PATH so it never matters.
ENV = {"PATH": "/usr/sbin:/sbin:/usr/bin:/bin", "LC_ALL": "C"}


def run(cmd, timeout=6):
    """Run a read-only shell command; return its combined output as a string."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                            timeout=timeout, env=ENV)
        return (r.stdout + r.stderr).strip()
    except Exception as exc:  # noqa: BLE001 - report anything rather than crash
        return f"(error running command: {exc})"


# Each check: (section title, shell command). All strictly read-only.
CHECKS = [
    ("Host / time / uptime",
     'echo "$(hostname)   $(date)   up $(uptime -p)"'),
    ("Active connections",
     "nmcli -t -f NAME,DEVICE,TYPE,STATE connection show --active"),
    ("All Wi-Fi/eth devices",
     "nmcli -f DEVICE,TYPE,STATE,CONNECTION device status | grep -Ev '^(lo|p2p)'"),
    ("Hotspot link state (per radio)",
     "for i in $(ls /sys/class/net | grep -E '^wl'); do echo \"== $i ==\"; "
     "iw dev \"$i\" link 2>/dev/null | grep -E 'Connected|SSID|signal|bitrate' "
     "|| echo '  (not connected)'; done"),
    ("ESS-ops visible in a scan?",
     # --rescan no: use cached scan results so the page renders fast and does
     # not kick off a fresh scan (which can disturb the radios) on every load.
     "nmcli --rescan no -f SSID,SIGNAL,CHAN device wifi list 2>/dev/null | "
     "grep -E 'SSID|ESS-ops' | head"),
    ("High-gain USB adapter present?",
     "lsusb | grep -i '2357:0108' || echo 'NOT DETECTED (TP-Link TL-WN822N missing!)'"),
    ("Wi-Fi drivers loaded",
     "lsmod | grep -E '8192|brcmfmac' || echo 'none loaded'"),
    ("tricap service",
     "echo active=$(systemctl is-active tricap.service) "
     "enabled=$(systemctl is-enabled tricap.service 2>/dev/null)"),
    ("tricap recent log (last 20 lines)",
     "journalctl -u tricap.service -n 20 --no-pager 2>/dev/null | tail -20 "
     "|| echo '(no journal)'"),
    ("Imagery storage (NVMe)",
     "df -h /mnt/ext_cam_storage 2>/dev/null || echo '(not mounted)'"),
]


def headline():
    """A few one-glance booleans for the coloured banner at the top."""
    ssid = run("iwgetid -r")
    on_essops = ssid == "ESS-ops"
    # which driver is carrying the client link?
    client_dev = run("iwgetid | awk '{print $1}'")
    client_drv = run(f"basename $(readlink /sys/class/net/{client_dev}/device/driver "
                     "2>/dev/null) 2>/dev/null") if client_dev else ""
    on_highgain = client_drv == "rtl8192eu"
    ap_up = "skyseeker" in run(
        "nmcli -t -f NAME connection show --active").lower()
    tricap_up = run("systemctl is-active tricap.service") == "active"
    return ssid, on_essops, client_drv, on_highgain, ap_up, tricap_up


def render():
    ssid, on_essops, client_drv, on_highgain, ap_up, tricap_up = headline()

    def chip(ok, good, bad):
        cls = "ok" if ok else "bad"
        return f'<span class="chip {cls}">{html.escape(good if ok else bad)}</span>'

    banner = (
        chip(on_essops, f"Hotspot: {ssid or '-'}", "Hotspot: NOT CONNECTED")
        + chip(on_highgain, "Link radio: high-gain USB",
               f"Link radio: {client_drv or 'none'} (weak/onboard!)")
        + chip(ap_up, "Rescue AP: up", "Rescue AP: down")
        + chip(tricap_up, "tricap: running", "tricap: stopped")
    )

    rows = []
    for title, cmd in CHECKS:
        out = html.escape(run(cmd)) or "(no output)"
        rows.append(f"<h2>{html.escape(title)}</h2><pre>{out}</pre>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>SkySeeker diag - {html.escape(run('hostname'))}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}}
 header{{padding:14px 16px;background:#161a22;position:sticky;top:0}}
 .chip{{display:inline-block;margin:4px 6px 0 0;padding:4px 10px;border-radius:14px;
        font-size:13px;font-weight:600}}
 .chip.ok{{background:#13371f;color:#7ee29a}} .chip.bad{{background:#3a1620;color:#ff8a9a}}
 main{{padding:8px 16px 40px}} h2{{font-size:14px;margin:18px 0 4px;color:#9fb3c8}}
 pre{{background:#161a22;padding:10px 12px;border-radius:8px;overflow-x:auto;
      font-size:12px;line-height:1.45;white-space:pre-wrap;word-break:break-word}}
 small{{color:#6b7785}}
</style></head><body>
<header><b>SkySeeker field diagnostics</b> &nbsp;<small>auto-refresh 5s &middot;
 {time.strftime('%H:%M:%S')}</small><div>{banner}</div></header>
<main>{''.join(rows)}</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):  # quiet; journald already timestamps starts
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
