import struct
import sys
import serial_comms.out.tricap_pb2 as pb
import serial, time, subprocess, pytz
import netifaces as ni

import pynmea2
import serial, os
from datetime import datetime, timedelta

from config import MOUNT_POINT

class SerialProcess():
    def __init__(self, cam_manager = None):
        super().__init__()
        # append valid reponses
        self._requests = []
        self._hasGps = False
        self._firstGps = False
        self._gpsTimestamp = 0
        self._cam_manager = cam_manager

    """
    Rx and Tx functions
    """
    def processGpsResponse(self, packet):
        try:
            decoded = packet.decode("utf-8")
            gpsData = pynmea2.parse(decoded)
            self._requests.append(gpsData)
        except serial.SerialException as e:
            print('Device error: {}'.format(e))
            return False
        except pynmea2.ParseError as e:
            print('Parse error: {}'.format(e))
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
            ni.ifaddresses('wlan0')
            ip = ni.ifaddresses('wlan0')[ni.AF_INET][0]['addr']
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
                subprocess.check_call(['/home/pi/tricap/wifi_setup.sh', ssid, password])
            # ret = subprocess.run(["wpa_cli", "add_network"], check=True)
            # print(subprocess.run(["wpa_cli", "set_network", "ssid", ssid], check=True))
            # print(subprocess.run(["wpa_cli", "set_network", "psk", password], check=True))
            # print(subprocess.run(["wpa_cli", "enable_network"], check=True))
            # print(subprocess.run(["wpa_cli", "save_config"], check=True))
            # print(subprocess.run(["wpa_cli", "reconfigure"], check=True))
        except:
            subprocess.check_call(['/home/pi/tricap/wifi_setup.sh', ssid, password])
        finally:
            print('failed')

    def saveGga(self, msg):
        gps_datetime = datetime.now()
        pi_time = datetime.now()
        if msg.timestamp != None and msg.latitude != 0.0 and msg.longitude != 0.0:
            # calculate gps time with time zone
            self._hasGps = True
            tz = pytz.timezone('CET')
            tzOffset = tz.utcoffset(datetime.now()).total_seconds()
            gpsTimeString = msg.timestamp.strftime('%H:%M:%S.%f')
            gps_time = datetime.strptime(gpsTimeString, '%H:%M:%S.%f')
            gps_time += timedelta(seconds=tzOffset)
            gps_datetime = pi_time.replace(hour=gps_time.hour, minute=gps_time.minute, second=gps_time.second, microsecond=gps_time.microsecond)
            gpsTimeString = gps_datetime.strftime('%H:%M:%S.%f')
            if not self._firstGps:
                # first time with gps -> set pi time
                self._firstGps = True
                if self._cam_manager != None:
                    self._cam_manager.sync_time(gpsTimeString)
                                
            if os.path.ismount(MOUNT_POINT):
                complete_dir = os.path.join(MOUNT_POINT, datetime.now().strftime('%Y_%m_%d'))
                dest = os.path.join(complete_dir, 'gpsData.csv')
                if not os.path.isdir(complete_dir):
                    os.makedirs(complete_dir)
                try:
                    if msg.timestamp != None and msg.latitude != 0.0 and msg.longitude != 0.0:
                        alt = 0.0
                        if msg.altitude != None:
                            alt = msg.altitude
                        line=(f"{str(msg.gps_qual)},{str(gps_datetime.timestamp())},{str(pi_time.timestamp())},{str(msg.latitude)},{str(msg.lat_dir)},{str(msg.longitude)},{str(msg.lon_dir)},{str(alt)},{str(msg.horizontal_dil)},{str(msg.geo_sep)}\n")
                        with open(dest, 'ta') as f:
                            f.write(line)
                    else:
                        print('No GPS timestamp')
                except Exception as e:
                    print("GPS line not saved")
        else:
            self._hasGps = False
