import struct
import sys
import serial_comms.out.tricap_pb2 as pb
import serial, time, subprocess, pytz
import netifaces as ni
from statistics import mean
from io import BytesIO
from pyubx2 import (
    POLL_LAYER_RAM,
    SET_LAYER_RAM,
    TXN_NONE,
    UBX_CLASSES,
    UBX_MSGIDS,
    NMEA_PROTOCOL,
    UBX_PROTOCOL,
    UBXMessage,
    UBXReader,
    POLL,
    SET,
    UBXStreamError,
    UBXParseError,
)
import serial, os
from datetime import datetime, timedelta
import math
from threading import Lock

from config import FALLBACK_TELEMETRY_DIR, MOUNT_POINT

class SerialProcess():
    def __init__(self, cam_manager = None):
        super().__init__()
        # append valid reponses
        self._requests = []
        self._hasGps = False
        self._firstGps = False
        self._gpsTimestamp = 0
        self._cam_manager = cam_manager

        self._lock = Lock()
        # Public "latest" values you can read at any time
        self.total_visible = 0
        self.visible_by_talker = {}    # {'GP': 17, 'GL': 9, ...}
        self.snr_min = None            # dB-Hz
        self.snr_avg = None
        self.snr_max = None
        self.pdop = None               # from GSA (best/latest valid)
        self.pdopLastUpdate = None

        # Internal state to assemble multipart GSVs per talker (constellation)
        # gsv_state[talker] = {
        #   'expected': int,             # total messages in this cycle
        #   'received_parts': set[int],  # which parts we have (1-based)
        #   'snrs': [ints],              # SNRs accumulated this cycle
        #   'num_in_view': int           # satellites in view reported by this talker
        # }
        self._gsv_state = {}

        # Last completed snapshot per talker so we can build a combined latest view
        # _gsv_complete[talker] = {'snrs':[...], 'num_in_view': int}
        self._gsv_complete = {}

    """
    Rx and Tx functions
    """
    def processGpsResponse(self, packet):
        try:
            bio = BytesIO(packet)
            # Parse UBX and NMEA messages from the blob
            ubr = UBXReader(bio, protfilter=UBX_PROTOCOL | NMEA_PROTOCOL)
            raw, parsed = ubr.read()
            if parsed:
                self._requests.append(parsed)
        except serial.SerialException as e:
            print('Device error: {}'.format(e))
            return False
        except Exception as e:
            print('Parse error: {}'.format(e))
            return False
        return True

    def processProtobufResponse(self, packet):
        try:
            msg = pb.Message()
            msg.ParseFromString(packet)
            self._requests.append(msg)
            return True
        except:
            print("Parse failed")
            return False

        return True

    def buildIpAddress(self):
        msg = pb.Message()
        msg.msgType = pb.Message.MessageType.IP_ADDRESS
        _ip = pb.IpAddress()
        try:
            _dev = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], text=True)
            _iface = "wlan0"
            for _line in _dev.split("\n"):
                _p = _line.split(":")
                if len(_p) >= 3 and _p[1] == "wifi" and _p[2] == "connected":
                    _iface = _p[0]
                    break
            ip = ni.ifaddresses(_iface)[ni.AF_INET][0]['addr']
            print(ip)
            _ip.ip = ip
        except:
            _ip.ip = ""

        msg.ip.CopyFrom(_ip)
        return msg.SerializeToString()

    def buildWifiReply(self):
        msg = pb.Message()
        msg.msgType = pb.Message.MessageType.WIFI_SETUP
        return msg.SerializeToString()

    def setupWifi(self, ssid, password):
        try:
            currentSsidReq = subprocess.run(['iwgetid', '-r'], check=True, capture_output=True)
            print('currentSsidReq {}'.format(currentSsidReq))
            currentSsid = ''
            if currentSsidReq.returncode == 0:
                # already connected
                currentSsid = currentSsidReq.stdout.rstrip().decode("utf-8")
            print('ssid {} currentSsid {}'.format(ssid, currentSsid))
            if ssid != currentSsid:
                subprocess.check_call(['/home/radxa/tricap/wifi_setup.sh', ssid, password])
            # ret = subprocess.run(["wpa_cli", "add_network"], check=True)
            # print(subprocess.run(["wpa_cli", "set_network", "ssid", ssid], check=True))
            # print(subprocess.run(["wpa_cli", "set_network", "psk", password], check=True))
            # print(subprocess.run(["wpa_cli", "enable_network"], check=True))
            # print(subprocess.run(["wpa_cli", "save_config"], check=True))
            # print(subprocess.run(["wpa_cli", "reconfigure"], check=True))
        except:
            subprocess.check_call(['/home/radxa/tricap/wifi_setup.sh', ssid, password])
        finally:
            print('failed')

    def saveGga(self, msg):
        gps_datetime = datetime.now()
        pi_time = datetime.now()
        if msg.time != None and msg.lat != '' and msg.lon != '' and self._firstGps:
            # calculate gps time with time zone
            self._hasGps = True
            tz = pytz.timezone('Africa/Johannesburg')
            tzOffset = tz.utcoffset(datetime.now()).total_seconds()
            gpsTimeString = msg.time.strftime('%H:%M:%S.%f')
            gps_time = datetime.strptime(gpsTimeString, '%H:%M:%S.%f')
            gps_time += timedelta(seconds=tzOffset)
            gps_datetime = pi_time.replace(hour=gps_time.hour, minute=gps_time.minute, second=gps_time.second, microsecond=gps_time.microsecond)
            if os.path.ismount(MOUNT_POINT):
                complete_dir = os.path.join(MOUNT_POINT, datetime.now().strftime('%Y_%m_%d'))
                dest = os.path.join(complete_dir, 'gpsData.csv')
                if not os.path.isdir(complete_dir):
                    os.makedirs(complete_dir)
                try:
                    if msg.time != None and msg.lat != '' and msg.lon != '':
                        alt = 0.0
                        if msg.alt != None:
                            alt = msg.alt
                        line=(f"{str(msg.quality)},{str(gps_datetime.timestamp())},{str(pi_time.timestamp())},{str(msg.lat)},{msg.NS},{str(msg.lon)},{msg.EW},{str(alt)},{str(msg.HDOP)},{str(msg.sep)}\n")
                        with open(dest, 'ta') as f:
                            f.write(line)
                    else:
                        print('No GPS timestamp')
                except Exception as e:
                    print("GPS line not saved")
            else:
                complete_dir = os.path.join(FALLBACK_TELEMETRY_DIR, datetime.now().strftime('%Y_%m_%d'))
                dest = os.path.join(complete_dir, 'gpsData.csv')
                if not os.path.isdir(complete_dir):
                    print("SSD not mounted, saving GPS data to built-in storage")
                    os.makedirs(complete_dir)
                try:
                    if msg.time != None and msg.lat != '' and msg.lon != '':
                        alt = 0.0
                        if msg.alt != None:
                            alt = msg.alt
                        line=(f"{str(msg.quality)},{str(gps_datetime.timestamp())},{str(pi_time.timestamp())},{str(msg.lat)},{msg.NS},{str(msg.lon)},{msg.EW},{str(alt)},{str(msg.HDOP)},{str(msg.sep)}\n")
                        with open(dest, 'ta') as f:
                            f.write(line)
                    else:
                        print('No GPS timestamp')
                except Exception as e:
                    print("GPS line not saved")
                
        else:
            self._hasGps = False

    def saveRmc(self, msg):
        if msg.date != None and msg.time != None and msg.lat != '' and msg.lon != '' and not self._firstGps and self._cam_manager != None:
            self._firstGps = True
            # calculate gps time with time zone
            tz = pytz.timezone('Africa/Johannesburg')
            tzOffset = tz.utcoffset(datetime.now()).total_seconds()
            gps_time = datetime.combine(msg.date, msg.time, msg.time.tzinfo)
            gps_time += timedelta(seconds=tzOffset)
            self._cam_manager.sync_time(gps_time.strftime('%Y-%m-%d %H:%M:%S.%f'))

    def process_gsv(self, msg):
        """
        Handle a single GSV sentence (multi-part). When the cycle for this talker completes,
        updates the public latest values (totals and SNR stats).
        """
        talker = getattr(msg, 'talker', None)
        if not talker:
            return

        # Parts/cycle info
        try:
            total_msgs = int(getattr(msg, 'numMsg', 0))
            this_part  = int(getattr(msg, 'msgNum', 0))
        except (TypeError, ValueError):
            return

        # Satellites in view for this constellation (reported on each part)
        num_in_view = self._safe_int(getattr(msg, 'numSV', None))

        # Extract up to 4 SNR fields from this sentence
        signal_id = getattr(msg, 'signalID', None)
        snrs = []
        for i in range(1, 5):
            s = getattr(msg, f"cno_0{i}", None)
            if s in (None, ''):
                continue
            try:
                snrs.append(int(s))
            except ValueError:
                pass  # ignore non-integer SNRs

        with self._lock:
            st = self._gsv_state.setdefault(talker, {
                'expected': total_msgs or 0,
                'received_parts': set(),
                'snrs': [],
                'num_in_view': num_in_view if num_in_view is not None else 0
            })

            # If expected suddenly changes (new cycle), reset the state
            if st['expected'] and total_msgs and total_msgs != st['expected'] and this_part == 1:
                st['received_parts'].clear()
                st['snrs'].clear()

            if total_msgs:
                st['expected'] = total_msgs
            if num_in_view is not None:
                st['num_in_view'] = num_in_view

            if this_part >= 1:
                st['received_parts'].add(this_part)
            if snrs:
                st['snrs'].extend(snrs)

            # Check completion of the cycle for this talker
            if st['expected'] and len(st['received_parts']) >= st['expected']:
                # Save a completed snapshot for this constellation
                self._gsv_complete[talker] = {
                    'snrs': list(st['snrs']),
                    'num_in_view': st['num_in_view'] if st['num_in_view'] is not None else 0
                }
                # Reset for the next cycle
                st['received_parts'].clear()
                if signal_id is None or signal_id == '0':
                    # only clear here for next cycle
                    st['snrs'].clear()

                # Recompute combined "latest" view across all talkers
                self._recompute_latest_from_completed_locked()

    def process_gsa(self, msg):
        """
        Handle a single GSA sentence. Updates `pdop` when it’s valid (ignores 0 and 99.99 etc.).
        """
        pdop = getattr(msg, 'PDOP', None)
        v = self._valid_pdop(pdop)
        if v is None:
            return
        with self._lock:
            # Choose the latest valid PDOP; if you prefer best (minimum), swap the logic:
            # self.pdop = v if self.pdop is None or v < self.pdop else self.pdop
            self.pdop = v
            self.pdopLastUpdate = datetime.now()

    # ---------- internal helpers ----------

    def _recompute_latest_from_completed_locked(self):
        """Combine completed per-constellation snapshots into public latest values."""
        # Total visible = sum latest num_in_view per talker
        total_visible = 0
        visible_by_talker = {}
        all_snrs = []

        for talker, snap in self._gsv_complete.items():
            n = snap.get('num_in_view') or 0
            total_visible += n
            visible_by_talker[talker] = n
            snrs = snap.get('snrs') or []
            all_snrs.extend(s for s in snrs if isinstance(s, int))

        self.total_visible = total_visible
        # Sorted by talker code for stable reads
        self.visible_by_talker = dict(sorted(visible_by_talker.items()))

        if all_snrs:
            self.snr_min = min(all_snrs)
            self.snr_max = max(all_snrs)
            self.snr_avg = round(mean(all_snrs), 2)
            # print(f"min max avg {self.snr_min} {self.snr_max} {self.snr_avg}")
        else:
            self.snr_min = self.snr_max = self.snr_avg = None

    @staticmethod
    def _safe_int(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _valid_pdop(x):
        if x is None:
            return None
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        # 0 or ~100 are typical "invalid" placeholders
        if not math.isfinite(v) or v <= 0 or v >= 50:
            return None
        return v
