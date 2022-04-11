import struct
from sys import platform as _platform
import serial_comms.out.tricap_pb2 as pb
import serial, time, subprocess
import netifaces as ni

class SerialProcess():
    def __init__(self):
        super().__init__()
        # append valid reponses
        self._requests = []

    """
    Rx and Tx functions
    """
    def processResponse(self, packet):
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
                subprocess.check_call(['/home/pi/tricap/alk/wifi_setup.sh', ssid, password])
            # ret = subprocess.run(["wpa_cli", "add_network"], check=True)
            # print(subprocess.run(["wpa_cli", "set_network", "ssid", ssid], check=True))
            # print(subprocess.run(["wpa_cli", "set_network", "psk", password], check=True))
            # print(subprocess.run(["wpa_cli", "enable_network"], check=True))
            # print(subprocess.run(["wpa_cli", "save_config"], check=True))
            # print(subprocess.run(["wpa_cli", "reconfigure"], check=True))
        except:
            subprocess.check_call(['/home/pi/tricap/alk/wifi_setup.sh', ssid, password])
        finally:
            print('failed')
