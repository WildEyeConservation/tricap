import time
import serial
from io import BytesIO
import socket
import requests
import logging
from pyubx2 import (
    POLL_LAYER_RAM,
    SET_LAYER_RAM,
    TXN_NONE,
    UBX_CLASSES,
    UBX_MSGIDS,
    UBX_PROTOCOL,
    NMEA_PROTOCOL,
    UBXMessage,
    UBXReader,
    POLL,
    SET,
    UBXStreamError,
    UBXParseError,
)
import json
from config import SECRETS_FILE

# Helper functions that can be used to download AGPS data from UBlox assistnow using a ZTP (zero touch protocol) token obtained 
# from the u-blox Thingstream portal. This assumes that pyubx2 is used to parse the GPS NMEA messages sent from the GPS chip.

# AssistNow API endpoints
ZTP_CREDENTIALS_URL = "https://api.thingstream.io/ztp/assistnow/credentials"
ASSISTNOW_URL = "https://assistnow.services.u-blox.com/GetAssistNowData.ashx"

class UBXMessageBuffer:
    """
    Simple buffer for storing parsed UBX messages.
    Messages are stored with their identity and raw data.
    """

    def __init__(self, messageArray=[]):
        # Store parsed_data
        self._messages = messageArray

    def add_message(self, parsed_data):
        """Add a parsed message to the buffer."""
        self._messages.append(parsed_data)

    def get_message(self, identity, remove=True):
        """
        Get a message with the specified identity from the buffer.
        If remove is True, the message is removed from the buffer after retrieval.
        Returns (raw_data, parsed_data) or None if not found within timeout.
        """
        for i, parsed_data in enumerate(self._messages):
            if parsed_data.identity == identity:
                if remove:
                    self._messages.pop(i)
                return parsed_data

    def get_all_messages(self, identity=None, remove=True):
        """
        Get all messages from the buffer, optionally filtered by identity.
        If remove is True, messages are removed after retrieval.
        Returns list of (raw_data, parsed_data) tuples.
        """
        if identity is None:
            messages = list(self._messages)
            if remove:
                self._messages.clear()
            return [parsed for parsed in messages]
        else:
            result = []
            indices_to_remove = []
            for i, parsed_data in enumerate(self._messages):
                if parsed_data.identity == identity:
                    result.append(parsed_data)
                    if remove:
                        indices_to_remove.append(i)

            if remove:
                # Remove in reverse order to maintain indices
                for i in reversed(indices_to_remove):
                    self._messages.pop(i)

            return result

    def clear(self):
        """Clear all messages from the buffer."""
        self._messages.clear()

class UBXAgps:
    _logger = logging.getLogger(__name__)
    def __init__(self, serialport, messageArray=[]):
        self.ser = serialport
        self.message_buffer = UBXMessageBuffer(messageArray)

    def has_internet(self):
        """
        Check if we currently have an internet connection to determine if we should try to
        download AGPS data.
        """
        try:
            # See if we can resolve the host name - tells us if there is
            # A DNS listening
            host = socket.gethostbyname("one.one.one.one")
            # Connect to the host - tells us if the host is actually reachable
            s = socket.create_connection((host, 80), 2)
            s.close()
            return True
        except Exception:
            pass # We ignore any errors, returning False
        return False
    
    def download_and_send_agps(self, serialport):
        self._logger.debug("Starting AGPS download and send process")
        self.ser = serialport
        self._enable_uart_outprot_ubx(self.ser, self.message_buffer)

        # Step 1.5: Enable CFG-NAVSPG-ACKAIDING for flow control
        self._enable_ackaiding(self.ser, self.message_buffer)

        ztp_token = None
        # Get the ZTP token from secrets file
        try:
            with open(SECRETS_FILE, 'r') as f:
                secrets = json.load(f)
                ztp_token = secrets.get("UBLOX_GPS_ZTP_TOKEN", None)
                if ztp_token is None or ztp_token == "your-ztp-token-here":
                    self._logger.error(f"ZTP token not found in secrets file. Creating placeholder entry. "
                                      f"Please update it with your actual token in the secrets file located in {SECRETS_FILE}.")
                    secrets["UBLOX_GPS_ZTP_TOKEN"] = "your-ztp-token-here"
                    with open(SECRETS_FILE, 'w') as fw:
                        json.dump(secrets, fw, indent=4)
                    return
        except Exception as e:
            self._logger.error(f"Error reading secrets file: {e} \nCreating placeholder entry. "
                                      f"Please update it with your actual token in the secrets file located in {SECRETS_FILE}.")
            secrets = {}
            secrets["UBLOX_GPS_ZTP_TOKEN"] = "your-ztp-token-here"
            with open(SECRETS_FILE, 'w') as fw:
                json.dump(secrets, fw, indent=4)
            return

        # # Step 2: Get chipcode from device using ZTP API
        chipcode, service_url = self._get_chipcode_from_device(
            self.ser, self.message_buffer, ztp_token)
        print(f"\nUsing chipcode: {chipcode}\n")
        self._logger.debug(f"\nUsing chipcode: {chipcode}\n")

        # Step 3: Download A-GPS data
        agps_data = self._download_agps_data(chipcode, service_url)
        # agps_data = b'\xb5b\x13@\x18\x00\x10\x00\x00\x12\xe9\x07\x0c\x0b\x079\x1b\x00@\xb3\xd5\t\n\x00\x00\x00\x00\x00\x00\x00\xcao\xb5b\x13\x00$\x00\x02\x00\x19\x00$i\\\x90c\x03M\xfd\xac\r\xa1\x00R\x9fc\x00\x1a\x8d.\x00B \x82\xff\xde\x01\xff\xff\x00\x00\x00\x00\xbe\x07\xb5b\x13\x00$\x00\x02\x00\x07\x00)\xa4\\\x90 \x05I\xfd\xc5\x0c\xa1\x00A\xde9\x00D\x07\xae\xff\xb3T\xa0\xff\x82\xff\xfe\xff\x00\x00\x00\x00J\x01\xb5b\x13\x00$\x00\x02\x00\x10\x00yz\\\x90\x89\nU\xfd\x80\x0c\xa1\x00\xdc\x1ah\x00\xbc3%\x00j\xfd<\x00\xaf\x00\x02\x00\x00\x00\x00\x00\x00\xe5\xb5b\x13\x00$\x00\x02\x00\x15\x00K\x03\\\x90\xa8\x0cR\xfdf\r\xa1\x00\xdcs\xe5\xffF\xc8\xe9\xff\xd2;\x84\xfft\x01\x03\x00\x00\x00\x00\x00\xd09\xb5b\x13\x00$\x00\x02\x00\x03\x00\xa23\\\x90\x96 n\xfd\x06\r\xa1\x00\x16\x1a\xe5\xff\x05\xb21\x00\xb7\xc7\x8c\xff\x8f\x02\xfe\xff\x00\x00\x00\x00e\xdd\xb5b\x13\x00$\x00\x02\x00\x1e\x00\x87?\\\x90\x82\xfb:\xfd\x1f\x0c\xa1\x00v\x8c9\x00\x17L\xa0\xff"\xf8\x9c\xff9\x00\x03\x00\x00\x00\x00\x00\xb7\xa7\xb5b\x13\x00$\x00\x02\x00\x0c\x00\xcaI\\\x90\x10\x0bV\xfdO\x0c\xa1\x00}hg\x009/>\x00\xcd\x81\x86\xff\x85\xfd\x00\x00\x00\x00\x00\x00\xf5\xe7\xb5b\x13\x00$\x00\x02\x00\x1d\x00\x07\x1b\\\x90\x9d\r>\xfd\t\x0c\xa1\x00\xc4;\x92\xff\xf2\xc0p\x00\rl\x13\x00R\xfe\x02\x00\x00\x00\x00\x00\x8f\xed\xb5b\x13\x00$\x00\x02\x00\x01\x00\xc0\t\\\x90T\n@\xfd\xb6\x0c\xa1\x00\xad\xf9\xbc\xffd\x12\xfd\xff\x98?\xea\xffq\x01\xff\xff\x00\x00\x00\x00\xf0\x07\xb5b\x13\x00$\x00\x02\x00\n\x00\x92Y\\\x90K o\xfd\xe0\x0c\xa1\x00\xe8\xff\xe4\xff\xcd\xfb\xa2\xff\x8fJf\x00\xa7\xfd\xff\xff\x00\x00\x00\x00\x92\xd2\xb5b\x13\x00$\x00\x02\x00\x1b\x00Or\\\x90\x9b\x076\xfd\xd8\x0c\xa1\x00\x9b\x9f\x8e\xff\x10\xfd"\x00\xd6y\x18\x00\xcc\xff\xfe\xff\x00\x00\x00\x00\x80\xf6\xb5b\x13\x00$\x00\x02\x00\t\x00o\x1c\\\x90"\x0eJ\xfdS\x0c\xa1\x00X\'\x0e\x00I\xf1S\x00\xbb\x9c+\x00%\x03\x00\x00\x00\x00\x00\x00\xf4\xa0\xb5b\x13\x00$\x00\x02\x00\x12\x00\xa2.\\\x90h\x13J\xfd\xdb\x0c\xa1\x00<\xb5\xba\xff \x99\x8b\xff\xb4\x1e\xbf\xff\x0b\xfe\x03\x00\x00\x00\x00\x00\xda\x1b\xb5b\x13\x00$\x00\x02\x00\x17\x00\xea0\\\x90\t\x1dk\xfd8\r\xa1\x00,\xb5\xe3\xff\xc1K\x8f\xff\x85\x9c\x93\xfff\x02\x01\x00\x00\x00\x00\x00C\x94\xb5b\x13\x00$\x00\x02\x00\x05\x00N,\\\x90\xd8\x17a\xfd\xf1\x0c\xa1\x00\xbd\xb5\xe2\xff6j:\x00\xf4 "\x00\x14\xff\x00\x00\x00\x00\x00\x00\x05\x11\xb5b\x13\x00$\x00\x02\x00 \x00\xbfI\\\x90#\x10M\xfd&\r\xa1\x00\xbe\xd5\x0e\x00\xef\xb3\xac\xff\xfc72\x00%\xff\x04\x00\x00\x00\x00\x00\x19\x08\xb5b\x13\x00$\x00\x02\x00\x0e\x00W4\\\x90*\x00J\xfd\xbd\x0c\xa1\x00\xf3;e\x00YS\x8f\xff\xa6\xf1~\x00\xf5\x02\x01\x00\x00\x00\x00\x00s\x9f\xb5b\x13\x00$\x00\x02\x00\x1a\x00\x11Y\\\x90\xcf\xf6?\xfd\xfb\x0c\xa1\x00\xa5\xa5`\x00@\x0c\x1c\x00q\xc7_\x00\xcc\xfe\xfe\xff\x00\x00\x00\x00\xc2\x1d\xb5b\x13\x00$\x00\x02\x00\x08\x00\xd0[\\\x90\xad\x010\xfd\xcb\x0c\xa1\x00\xcaX\x8d\xff\xdc\xc2\x13\x00p\x1c\x15\x00\x1c\x02\xff\xff\x00\x00\x00\x00\xc7\xcd\xb5b\x13\x00$\x00\x02\x00\x11\x001j\\\x90\xe9\x0b>\xfd\xf7\x0b\xa1\x00\xc2\x8f\x91\xff\x12\x19\xd1\xff\xc5\x8b\x0f\x00\x01\x00\xfd\xff\x00\x00\x00\x00\xdb#\xb5b\x13\x00$\x00\x02\x00\x16\x00xe\\\x90+\nW\xfd\xb2\x0c\xa1\x00\x8e=h\x00\xf4\x15\xd7\xff]w*\x00\xb7\xff\x01\x00\x00\x00\x00\x00\xc7\xb1\xb5b\x13\x00$\x00\x02\x00\x04\x004\x1e\\\x90\xf4\x11Q\xfd\xa3\r\xa1\x00O\xbf\x10\x00h\x1d\x88\xff9\xdb\x0b\x00!\x00\x01\x00\x00\x00\x00\x00\x8a\xad\xb5b\x13\x00$\x00\x02\x00\x1f\x00sY\\\x90\x98\x07M\xfd\x92\r\xa1\x00{\xd7:\x00+\x82%\x00>.v\x00E\xff\x01\x00\x00\x00\x00\x00\xbe(\xb5b\x13\x00$\x00\x02\x00\r\x00\xd5P\\\x90\xa4\x15V\xfd\xf5\x0c\xa1\x00\xdd=\x15\x00\xb8\x03)\x00\xbbE\t\x00\xd6\x02\x00\x00\x00\x00\x00\x00\xf97\xb5b\x13\x00$\x00\x02\x00\x14\x00J\x1e\\\x90\xe1\x0bQ\xfd\xc3\x0c\xa1\x00\n\x0f\xdd\xff\x81\x01\xab\xff\xa7\x9f\xc8\xff|\x01\x00\x00\x00\x00\x00\x00\xf6A\xb5b\x13\x00$\x00\x02\x00\x02\x00\x93\x8a\\\x90\xf6\rE\xfd\x9a\x0c\xa1\x00\x83U\xb6\xff1>\xdc\xff0\x9b!\x00\xf9\xff\x02\x00\x00\x00\x00\x00\x8dU\xb5b\x13\x00$\x00\x02\x00\x0b\x00\x9c\x12\\\x90\x1f\x0eE\xfd\xb4\r\xa1\x00h\xb4\xbb\xff\xe2\xb8\xa3\xffZ[\xee\xff\xe8\xfd\x04\x00\x00\x00\x00\x00LG\xb5b\x13\x00$\x00\x02\x00\x1c\x00\x82\x03\\\x90G\x0cQ\xfd~\r\xa1\x00E\xc88\x00\xa72\x15\x00\x8b\x0b\x9b\xffr\xfd\x01\x00\x00\x00\x00\x00f\x00\xb5b\x13\x00$\x00\x02\x00\x13\x008Y\\\x90^\x0b:\xfd*\r\xa1\x00\x02Z\x93\xff]Uv\x00r\xc1\\\x00\xc9\x02\x01\x00\x00\x00\x00\x00\xb2\xe9\xb5b\x13\x00$\x00\x02\x00\x18\x00\xb3\x91\\\x90\xb1\xfa:\xfd\xc3\x0c\xa1\x00\xe8\x805\x00\x16\xc4-\x00\xffN\xc8\xff+\xff\x04\x00\x00\x00\x00\x00\xb9~\xb5b\x13\x00$\x00\x02\x00\x06\x00\xe1\x1e\\\x907\x1dX\xfd>\r\xa1\x00.\xde\xba\xff\xfe\x8a\xe4\xff~|\xc7\xff\x96\xfd\xfe\xff\x00\x00\x00\x00?\xc0\xb5b\x13\x00$\x00\x02\x00\x0f\x001\x88\\\x90\xae\xff<\xfd\xd4\x0c\xa1\x00\xb7]\x08\x00\xb1\xa8<\x00\xe6\x9c\xeb\xff\x81\x01\x01\x00\x00\x00\x00\x00\xf4s\xb5b\x13\x06$\x00\x02\x00\x07\x00\xc7\x02\x01\x01\xe2\xff\xac\x07\xd3\xdc\xfe\xff\xcb1\x00\x00X\xb1\x06\x00\n@\xeb\xff\x07\x05|\xa4\x00\x00\x00\x00\xbc^\xb5b\x13\x06$\x00\x02\x00\x10\x00\xc7\x02\x01\x01\xf5\xff\x08\x03?e\x08\x00J\'\x00\x00]$\x08\x00\'@\xeb\xff\xe0\xff\x83\x85\x00\x00\x00\x00\xf7\xd8\xb5b\x13\x06$\x00\x02\x00\x15\x00\xc7\x02\x01\x01D\x00\x89\x02\x02\x85\n\x0035\x00\x00\xe1\x80\x13\x00\xd6>\xeb\xff\x1a\x04&\x90\x00\x00\x00\x00-,\xb5b\x13\x06$\x00\x02\x00\x03\x00\xc7\x02\x01\x00\xdd\xff\xe7\x08\xe8I\xf7\xff\xa41\x00\x00\xfe\xa3\x10\x00\x98@\xeb\xff\x04\x056\xa4\x00\x00\x00\x00)g\xb5b\x13\x06$\x00\x02\x00\x0c\x00\xc7\x02\x01\x01\xf0\xff\xa9\x02\xb0\xdf\x00\x00\xd2\x1e\x00\x00\x9e\x07\x12\x00\xfd?\xeb\xff\xdf\xffS\xd1\x00\x00\x00\x00\x0e\x12\xb5b\x13\x06$\x00\x02\x00\x01\x00\xc7\x02\x01\x01\xd9\xff\xd0\x00\x8e\xf3\xfa\xff\xae+\x00\x00\x83\x9c\x0b\x00\xb8?\xeb\xff\x04\x01\xe8\xfc\x00\x00\x00\x00\xfa\xfe\xb5b\x13\x06$\x00\x02\x00\n\x00\xc7\x02\x01\x01n\x00\xbe\x07]\xb1\x04\x00\xdb\x1d\x00\x00\xcf\xef\x0c\x00\xc4@\xeb\xff\xe1\xf9c\x0c\x00\x00\x00\x00R\x7f\xb5b\x13\x06$\x00\x02\x00\t\x00\xc7\x02\x01\x01\xb3\xff\xab\x07!K\x06\x00\xb0\r\x00\x00\xd4\xa9\n\x00\r@\xeb\xff\xe1\xfe\x83\x8c\x00\x00\x00\x00R\x9f\xb5b\x13\x06$\x00\x02\x00\x12\x00\xc7\x02\x01\x01\xc2\xff<\x05A\x11\xf0\xff\xaa6\x00\x00\xe0<\x0c\x00\xe9?\xeb\xff\x1b\xfd\x1f\xe5\x00\x00\x00\x00\x95M\xb5b\x13\x06$\x00\x02\x00\x17\x00\xc7\x02\x01\x01-\x00O\x00\x1a\xf8\xf5\xffo9\x00\x00\xb4\x89\x04\x00\xd4>\xeb\xff\x19\x03\x8e\x04\x00\x00\x00\x006\xf6\xb5b\x13\x06$\x00\x02\x00\x05\x00\xc7\x02\x01\x01\xd6\xff\xba\x02\x11\xe1\x02\x00\xb48\x00\x00\xf5\x83\x01\x00W@\xeb\xff\x0c\x01<\x97\x00\x00\x00\x00Z\xe1\xb5b\x13\x06$\x00\x02\x00\x0e\x00\xc7\x02\x01\x01\xf8\xff\xca\x01>\x1e\x0c\x007\x18\x00\x00\x88+\x03\x00\x04@\xeb\xff\xde\xf9\xdb\x91\x00\x00\x00\x00\xb8\xf1\xb5b\x13\x06$\x00\x02\x00\x08\x00\xc7\x02\x01\x01\x00\x00\xaf\t\x81\x06\xfd\xff\xf41\x00\x00>\x1c\t\x00\x8f@\xeb\xff\x07\x06\x0f\xb0\x00\x00\x00\x00ZW\xb5b\x13\x06$\x00\x02\x00\x11\x00\xc7\x02\x01\x01\xbe\xff*\x04\x95\xb3\xf1\xffq0\x00\x00\x02\xfd\t\x00\x10@\xeb\xff\x1b\x04q\x95\x00\x00\x00\x00F\x1d\xb5b\x13\x06$\x00\x02\x00\x16\x00\xc7\x02\x01\x01\xe6\xff\x8c\x04Q\x82\xf7\xff\xf3\x1f\x00\x00\xd7\x8b\x02\x00+@\xeb\xff\x1b\xfd\x1e\xc8\x00\x00\x00\x00\'\x1d\xb5b\x13\x06$\x00\x02\x00\x04\x00\xc7\x02\x01\x01\xab\xff\x9e\x04\x8e\x95\xf5\xffk8\x00\x00*\xf9\x12\x00y@\xeb\xff\x05\x06\xc7\xaf\x00\x00\x00\x00m\xc7\xb5b\x13\x06$\x00\x02\x00\r\x00\xc7\x02\x01\x01\x11\x00\xff\x02\x89-\x0e\x00\xa6\x1d\x00\x00\x8cu\x00\x00S@\xeb\xff\xde\xfeA4\x00\x00\x00\x00\x7f\x8f\xb5b\x13\x06$\x00\x02\x00\x14\x00\xc7\x02\x01\x01\xc5\xff\x10\x05\xe9f\x0c\x00\x8d\'\x00\x00\x852\x11\x00\xd4@\xeb\xff \x02\x17\xe0\x00\x00\x00\x00\xe5\xfd\xb5b\x13\x06$\x00\x02\x00\x02\x00\xc7\x02\x01\x01\xfd\xff0\t\x10_\xf9\xff\x155\x00\x00\xe4\xfb\r\x00\x05@\xeb\xff\x05\xfc\xe9\xa0\x00\x00\x00\x00\x97\xcc\xb5b\x13\x06$\x00\x02\x00\x0b\x00\xc7\x02\x01\x01\x00\x00\xa9\x01\x1a\xe1\x02\x00\x10$\x00\x00\xc6^\x0f\x00\xdc@\xeb\xff\xe0\x00%\x94\x00\x00\x00\x00\xc2\xfe\xb5b\x13\x06$\x00\x02\x00\x13\x00\xc7\x02\x01\x01\xfa\xff\x83\x04\xcfB\x0e\x00R\x1f\x00\x00\xec\xb6\x0e\x00[@\xeb\xff\x1c\x03\x83\x7f\x00\x00\x00\x00\x83h\xb5b\x13\x06$\x00\x02\x00\x18\x00\xc7\x02\x01\x01#\x00\xaa\x03\xb7\x9a\xf3\xffV!\x00\x00\xa7o\x07\x00\xf0?\xeb\xff\x1b\x02\x1a\xaf\x00\x00\x00\x00\xc8\xbe\xb5b\x13\x06$\x00\x02\x00\x06\x00\xc7\x02\x01\x01@\x00a\x02\xa3V\x00\x00Y+\x00\x00\xf8\x82\x04\x00\xaf@\xeb\xff\n\xfcA]\x00\x00\x00\x00+\xd4\xb5b\x13\x06$\x00\x02\x00\x0f\x00\xc7\x02\x01\x01\xf0\xff\xcf\x01\x02O\n\x00$\x1d\x00\x00:\xa0\x05\x00\r@\xeb\xff\xdf\x00\xb8\xb2\x00\x00\x00\x00\xd3\xc2\xb5b\x13\x05$\x00\x02\x00\x03\x01\xe9yU\x15\x07\xca.\xff\xb4\xeb\xca\x00\xb7\xcd\xe2\xff\xdb\xf9\xbf\xff\xe4\xc8\xbf\xff\xfe\xff\x00\x00\x00\x00\x00\x00\xd3\x9e\xb5b\x13\x05$\x00\x02\x00\x04\x10\x94xQ+z\xa3\xbf\xfeJ\xe8\xca\x00\xeda;\x00f\x0c\xc0\xff\xb9>p\x00\xff\xff\x00\x00\x00\x00\x00\x00\xcfD\xb5b\x13\x05$\x00\x02\x00\x02\x01\xe8vT\x7f\x0e\xc5\xf1\xfe\x1c\xee\xca\x003\xa3\xa0\xff\xbb\xb9\xc0\xff\x175\x0b\x00\xfa\xff\x00\x00\x00\x00\x00\x00\x00\n\xb5b\x13\x03(\x00\x02\x00\x19\x00\x10\x1b\xca\x01\xe1\x14\xa5\x00\xe1\x05\x00\x00\x97/$\x00*\x8d\x97\xffwFO\x00\xa7\xfd\xff\xff\xd5\x03\x03\x00\x00\x00\x00\x00\x8fV\xb5b\x13\x03(\x00\x02\x00\x07\x00\x10\x1b\xe5\xbaL\xe8\xca\x00]\'\x00\x00\xd8\xbd\x98\xff\xb7Ho\x00\x06\xed\x8c\xff-\xff\xff\xff\x8d\x01\x07\x00\x00\x00\x00\x00j\xae\xb5b\x13\x03(\x00\x02\x00\x10\x00\x10\x1b\xcc\x0c\x9f\xed\xca\x00\xbfJ\x00\x00B\xe5\xa6\xff\t\xab\xb1\xff\xf7\x12?\x00o\xff\xff\xffX\xfc\x02\x00\x00\x00\x00\x00\xec\xf9\xb5b\x13\x03(\x00\x02\x00\x15\x00\x10\x1b~\x1c\xb0\x14\xa5\x00c\x04\x00\x00\xdb\xfd\xec\xff,-c\x00\xaaY\xfb\xff\xaf\xfd\xff\xffF\xfc\x02\x00\x00\x00\x00\x00T\xe5\xb5b\x13\x03(\x00\x02\x00\x03\x00\x10\x1b\xf3\x13\x16\xec\xca\x00\xb2\x03\x00\x00\xa9\x11\x00\x00U^\x9d\xff5\xb4\xf9\xff\x8a\x00\x00\x00\xbb\x03\x05\x00\x00\x00\x00\x00,p\xb5b\x13\x03(\x00\x02\x00\x1e\x00\x10\x1b(\x04\xc9\x14\xa5\x00\xe9\x03\x00\x00\x9c\xf4\x14\x00\xed\x10\xf3\xffe\x00\xa4\xff\x99\xfd\xff\xffb\x01\x02\x00\x00\x00\x00\x00\xb7\xe0\xb5b\x13\x03(\x00\x02\x00\x0c\x00\x10\x1b\xbd\x14\xda\x14\xa5\x00\xd6\n\x00\x00Vz\xc6\xff\x96<\xd0\xff\xbe\xc3\xa6\xff\xbd\xfd\xff\xffd\x00\x08\x00\x00\x00\x00\x00;\x80\xb5b\x13\x03(\x00\x02\x00\x1d\x00\x10\x1b/\x04\xda\x14\xa5\x00\x9a\x00\x00\x00\xa14-\x00\xe3\xf1\xbb\xffu\xfb\xa3\xff\x99\xfd\xff\xff/\x02\x01\x00\x00\x00\x00\x00P<\xb5b\x13\x03(\x00\x02\x00\x01\x00\x10\x1b\xd7\x12\x15\xec\xca\x00\x14\x07\x00\x00]h\xb6\xff\xca[\xfa\xff\x03\x9a\xfe\xff\x8f\x00\x00\x00\x04\xff\x01\x00\x00\x00\x00\x00\x00\xf4\xb5b\x13\x03(\x00\x02\x00\n\x00\x10\x1bk\xbc\x8d\xe7\xca\x00hY\x00\x00\x9b\x93\x9d\xff\xe01`\x00\x06\xb8\x8c\xff.\xff\xff\xff\xa0\xfe\xfa\xff\x00\x00\x00\x00\xe1+\xb5b\x13\x03(\x00\x02\x00\x1b\x00\x10\x1b\xa9\x05\x89\x14\xa5\x00\r\x04\x00\x00Km7\x00\xe0\xec\xf0\xff\xb1\xa6\xa5\xff\x9b\xfd\xff\xffR\x02\x01\x00\x00\x00\x00\x00\x17@\xb5b\x13\x03(\x00\x02\x00\t\x00\x10\x1b\n\x06H\xe9\xca\x00\x1ay\x00\x00a~\xa3\xff\xe0"\xa7\xff\x86\xfa@\x00j\xff\xff\xffu\x00\t\x00\x00\x00\x00\x00\xe0\xcc\xb5b\x13\x03(\x00\x02\x00\x17\x00\x10\x1b\xc3\x00\xc2\x14\xa5\x00f\x02\x00\x00&\xe5\x1e\x00|\x00~\x00?6P\x00\xa5\xfd\xff\xff\xd0\xfd\x02\x00\x00\x00\x00\x00\x7f\x02\xb5b\x13\x03(\x00\x02\x00\x05\x00\x10\x1bW#\xf6\xea\xca\x00D\n\x00\x007\xa2\xa1\xff\x9b\xbb\xd4\xffO\xfb\xfb\xff~\x00\x00\x00\x19\xff\x06\x00\x00\x00\x00\x00d\x0f\xb5b\x13\x03(\x00\x02\x00\x0e\x00\x10\x19C\x1b\xb9\x14\xa5\x00\xdc\x08\x00\x00>\xc7\xfd\xff\x8c\xa5\xf5\xff\x97.\xfb\xff\xa7\xfd\xff\xfft\xfd\xf4\xff\x00\x00\x00\x00\x16\xee\xb5b\x13\x03(\x00\x02\x00\x1a\x00\x10\x1b\xd2\x01\xd6\x14\xa5\x00\xd8\x08\x00\x00\x1bh#\x00\x82y\xd8\xff\rMO\x00\xa6\xfd\xff\xff\xb1\xfd\xfe\xff\x00\x00\x00\x0040\xb5b\x13\x03(\x00\x02\x00\x08\x00\x10\x1b\xcc\\o\xeb\xca\x00\xdd\x1c\x00\x00\xb1\x8b\x83\xff\x13\xbe)\x00\x80\xd0\xe7\xff6\xff\xff\xff\x15\xfd\x06\x00\x00\x00\x00\x00\xf1{\xb5b\x13\x03(\x00\x02\x00\x11\x00\xfb\x81\xb2\xbfd\xb8}\x00e\xc7\x00\x00\x98A\xc7\xff\xe4\xd6Z\x00Ege\x00\xb1\xf3\xff\xff\xdf\xff\x07\xfe\x00\x00\x00\x00L\x90\xb5b\x13\x03(\x00\x02\x00\x16\x00\x10\x1b\x7f\x1c\xb4\x14\xa5\x00\x1a\x04\x00\x00`\xd7\x18\x00\x8f\x15W\x00\xeaX\xfb\xff\xaf\xfd\xff\xff\xb7\x01\x01\x00\x00\x00\x00\x00\x90N\xb5b\x13\x03(\x00\x02\x00\x04\x00\x10\x1b2$\x91\xeb\xca\x00\xec\x08\x00\x00\x07\xc1\x87\xff\xe887\x00}o\xfb\xff\x8e\x00\x00\x003\xfc\x04\x00\x00\x00\x00\x00KC\xb5b\x13\x03(\x00\x02\x00\r\x00\x10\x1b\xfdC\x9c\xe7\xca\x00\x081\x00\x00 \xd0\xa2\xff\xc9G\x01\x00\x93a\xe6\xff.\xff\xff\xff\x11\xff\xfc\xff\x00\x00\x00\x00\xefW\xb5b\x13\x03(\x00\x02\x00\x14\x00\x10\x1b\xf5\x1c\xb8\x14\xa5\x00\xb4\x04\x00\x002\xeb\xf8\xff\x9c\xe6\xb4\xff\xa0R\xfb\xff\xb0\xfd\xff\xff9\xfc\xfe\xff\x00\x00\x00\x00\xcb\x95\xb5b\x13\x03(\x00\x02\x00\x02\x00\x10\x1b\xe2,\xbd\xeb\xca\x00H\x06\x00\x00\xf8e\xce\xff\xb9|\xb6\xff\xb9t\xff\xffd\x00\x00\x00\x15\x03\x04\x00\x00\x00\x00\x00\xfa\xf0\xb5b\x13\x03(\x00\x02\x00\x0b\x00\x10\x1b\xda\x15\xd5\x14\xa5\x00\x14\x12\x00\x00\x13c\xc3\xff\x94\xdb\xb2\xff\x14P\xa7\xff\xbf\xfd\xff\xff/\x03\x04\x00\x00\x00\x00\x00ka\xb5b\x13\x03(\x00\x02\x00\x1c\x00\x10\x1b\x94\x05\xa6\x14\xa5\x00\x07\x02\x00\x00T\xea\xc8\xff\xc5\xa9y\x00\x93\xa3\xa5\xff\x9b\xfd\xff\xff\xdf\x01\x01\x00\x00\x00\x00\x00\xc5\xc4\xb5b\x13\x03(\x00\x02\x00\x13\x00\x10\x1b\xf7\x1c\xb3\x14\xa5\x00\x1f\x06\x00\x00d>\xde\xffw&\xb2\xff\x13L\xfb\xff\xb0\xfd\xff\xff\x19\xfc\xff\xff\x00\x00\x00\x00\x06z\xb5b\x13\x03(\x00\x02\x00\x18\x00\x10\x1b\xc2\x00\xaf\x14\xa5\x00\xd2\x07\x00\x00\xf5\xa6\'\x00\xf2\x8f\xb6\xff=4P\x00\xa5\xfd\xff\xff`\x00\xf8\xff\x00\x00\x00\x006L\xb5b\x13\x03(\x00\x02\x00\x06\x00\x10\x1b\xa9\x02J\xea\xca\x006)\x00\x00n\x81\x98\xff:\xb5\xbd\xff\xe6\x0e?\x00j\xff\xff\xff\x80\x00\xf8\xff\x00\x00\x00\x00\xbb\x06\xb5b\x13\x02 \x00\x02\x00\x19\x00\x0e\x00n\x02\x0c\x00\r\x00\xb1\xff1k\xf0\xff\x86\x08\x98|\x0b\x00\x00\x00\x00\x00\x00\x00\x00\x00\xcfa\xb5b\x13\x02 \x00\x02\x00\x07\x00\x0e\x00n\x02\r\x00\r\x00\xc8\xff\x92\x15\xf0\xff\x1b\x0eSl\xef\xff\xff\xff\x00\x00\x00\x00\x00\x00\x07\x9d\xb5b\x13\x02 \x00\x02\x00"\x00\x0e\x00n\x02\t\x00\x12\x00m\x00\x92\xc0\xf1\xff`\xa9\xbbe\x8b\xff\xff\xff\x00\x00\x00\x00\x00\x00R\x87\xb5b\x13\x02 \x00\x02\x00\x15\x00\x0e\x00n\x02\x0c\x00\x0e\x00\xb1\xff1k\xf0\xffF%\xfa\xde\x8d\xfe\xff\xff\x00\x00\x00\x00\x00\x00\xeb\xb9\xb5b\x13\x02 \x00\x02\x00\x03\x00\x0e\x00n\x02\x0b\x00\x18\x00\xc8\xff\x91\x15\xf0\xff\xbf(\x91\x91\x07\x00\xff\xff\x00\x00\x00\x00\x00\x00E\x97\xb5b\x13\x02 \x00\x02\x00\x1e\x00\x0e\x00n\x02\x13\x00$\x00\xa6\xffFk\xf0\xff|&]\x1d\xf7\xfe\xf5\xff\x00\x00\x00\x00\x00\x00T\x1f\xb5b\x13\x02 \x00\x02\x00\x0c\x00\x0e\x00n\x02\x0b\x00\x18\x00^\x00\xa6\xc0\xf1\xffz\xeb\x95\x82\xf9\xff\xff\xff\x00\x00\x00\x00\x00\x00\nl\xb5b\x13\x02 \x00\x02\x00\n\x00\x0e\x00n\x02\n\x00\r\x00m\x00\x92\xc0\xf1\xff\x19\xac\x12\xb3s\xfe\xff\xff\x00\x00\x00\x00\x00\x00~\x1b\xb5b\x13\x02 \x00\x02\x00\x1b\x00\x0e\x00n\x02\r\x00\x14\x00\xb1\xff1k\xf1\xff\x89\x12D\x12C\xfe\xfd\xff\x00\x00\x00\x00\x00\x00[\x8c\xb5b\x13\x02 \x00\x02\x00\t\x00\r\x00m\x02\x0c\x00\x14\x00\xe7\xff\xaa\x15\xf0\xff\xf5\x18v\xde\xbd\xff\xfc\xff\x00\x00\x00\x00\x00\x00\x88-\xb5b\x13\x02 \x00\x02\x00$\x00\x0e\x00n\x02\r\x00\x19\x00n\x00\xa6\xc0\xf1\xff\xab\xd2S\\\xfe\xfe\xff\xff\x00\x00\x00\x00\x00\x00\xe9\x9a\xb5b\x13\x02 \x00\x02\x00\x05\x00\x0e\x00n\x02\x0b\x00\x07\x00\xc8\xff\x91\x15\xf0\xff\x01\'(\xb3\xfe\xff\x01\x00\x00\x00\x00\x00\x00\x00)*\xb5b\x13\x02 \x00\x02\x00\x1a\x00\x0e\x00n\x02\x07\x00\x1d\x00K\x00\x8c\xc0\xf1\xff\xd3\xc1\xb5\xecS\x00\x03\x00\x00\x00\x00\x00\x00\x00\x05L\xb5b\x13\x02 \x00\x02\x00\x08\x00\r\x00m\x02\x0f\x00\x13\x00\xe6\xff\xa9\x15\xf0\xff\xca!\x8du\xe4\xff\xfe\xff\x00\x00\x00\x00\x00\x00<]\xb5b\x13\x02 \x00\x02\x00\x04\x00\x0e\x00n\x02\n\x00\x04\x00\xc8\xff\x93\x15\xf0\xff\xf5\xf5\xeb#\xfb\xff\xfd\xff\x00\x00\x00\x00\x00\x00\x13S\xb5b\x13\x02 \x00\x02\x00\x1f\x00\x0e\x00n\x02\x0b\x00\x0b\x00\xb1\xff0k\xf0\xff\x15\xfe\xab\xc6\xc9\xff\xff\xff\x00\x00\x00\x00\x00\x00nu\xb5b\x13\x02 \x00\x02\x00\r\x00\x0b\x00k\x02\n\x00\x1b\x00n\x00\xa6\xc0\xf1\xffn\xcf\x0c\xf6\xe9\xff\x00\x00\x00\x00\x00\x00\x00\x00\xcc=\xb5b\x13\x02 \x00\x02\x00\x02\x00\x0e\x00n\x02\x12\x00!\x00\xb3\xffSk\xf0\xffg\x1a\xd6I\x01\x00\x01\x00\x00\x00\x00\x00\x00\x00\xeb\x16\xb5b\x13\x02 \x00\x02\x00\x0b\x00\x0e\x00n\x02\r\x00\x0e\x00^\x00\xa6\xc0\xf1\xffM\xffmNB\x064\x00\x00\x00\x00\x00\x00\x00\x12\xdc\xb5b\x13\x02 \x00\x02\x00\x13\x00\x0e\x00n\x02\x13\x00\x03\x00\xe5\xff\xde\x15\xf0\xff\x8a\xc4\xadw/\x05\n\x00\x00\x00\x00\x00\x00\x00Tk\xb5b\x13\x02 \x00\x02\x00\x18\x00\x01\x02\xe1\x01\x12\x00)\x00\xa9\xff\x8c\x89\xf1\xff\xfc \x1d>x\xff\xfa\xff\x00\x00\x00\x00\x00\x00\x03\xae\xb5b\x13\x02 \x00\x02\x00!\x00\x0e\x00n\x02\x0e\x00\x1b\x00n\x00\xa6\xc0\xf1\xff(\xb9Y\xd6\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\xd4\xda\xb5b\x13\x02 \x00\x02\x00\x0f\x00\x0e\x00n\x02\x0c\x00\x1f\x00n\x00\xa5\xc0\xf1\xffL\xcd\xed!\x8d\xff\xff\xff\x00\x00\x00\x00\x00\x00cY'
        print(f"Downloaded {len(agps_data)} bytes of A-GPS data\n")
        self._logger.debug(f"Downloaded {len(agps_data)} bytes of A-GPS data\n")

        # Step 4: Send data to device
        self._send_data_to_device(self.ser, self.message_buffer, agps_data)


    def _read_available_messages(self, ser, message_buffer):
        """
        Read all available messages from the serial port and populate the message buffer.
        This function parses all currently available UBX messages without blocking.
        """
        try:
            # Only read if there's data available
            if ser.in_waiting == 0:
                return

            ubr = UBXReader(ser, protfilter=UBX_PROTOCOL | NMEA_PROTOCOL)
            # Read available messages (non-blocking due to timeout=0 on serial)
            # Limit iterations to prevent infinite loops
            max_iterations = 100
            iteration = 0
            while ser.in_waiting > 0 and iteration < max_iterations:
                iteration += 1
                try:
                    (raw_data, parsed_data) = ubr.read()
                    if parsed_data:
                        message_buffer.add_message(
                            parsed_data)
                except (UBXStreamError, UBXParseError, EOFError):
                    # End of stream or parse error, stop reading
                    break
                except Exception:
                    # Other errors, continue trying to read
                    break
        except Exception:
            # Ignore errors during reading
            pass


    def _poll_ubx_message(self, ser, message_buffer, msg_class: str, msg_id: str, timeout=5):
        """
        Poll the device for a specific UBX message and return the full message as hex string.
        Uses the message buffer to retrieve the response.
        """
        # Create poll message using pyubx2
        poll_msg = UBXMessage(msg_class, msg_id, POLL)

        # Clear message buffer for this specific message type to avoid old messages
        message_buffer.get_all_messages(identity=msg_id, remove=True)
        time.sleep(0.01)

        # Send poll message
        ser.write(poll_msg.serialize())
        time.sleep(0.1)

        # Wait for response from message buffer, reading available messages while waiting
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Read available messages from serial
            self._read_available_messages(ser, message_buffer)

            # Check if we have the message we're looking for
            result = message_buffer.get_message(msg_id, remove=True)
            if result:
                print(f"Received message: {result.identity}" )
                self._logger.debug(f"Received message: {result.identity}" )
                return result.serialize().hex()

            time.sleep(0.01)

        return None


    def _get_device_ubx_messages(self, ser, message_buffer):
        """
        Poll the device for UBX-SEC-UNIQID and UBX-MON-VER messages.
        Returns a dict with the hex strings of both messages.
        """
        # print("Polling device for UBX-SEC-UNIQID...")
        uniqid_msg = self._poll_ubx_message(
            ser, message_buffer, "SEC", "SEC-UNIQID", timeout=5)

        if not uniqid_msg:
            raise Exception("Failed to receive UBX-SEC-UNIQID message from device")
        print(f"Received UBX-SEC-UNIQID: {uniqid_msg[:40]}...")
        self._logger.debug(f"Received UBX-SEC-UNIQID: {uniqid_msg[:40]}...")

        time.sleep(0.1)

        # print("Polling device for UBX-MON-VER...")
        monver_msg = self._poll_ubx_message(
            ser, message_buffer, "MON", "MON-VER", timeout=5)

        if not monver_msg:
            raise Exception("Failed to receive UBX-MON-VER message from device")
        print(f"Received UBX-MON-VER: {monver_msg[:40]}...")
        self._logger.debug(f"Received UBX-MON-VER: {monver_msg[:40]}...")

        return {
            "UBX-SEC-UNIQID": uniqid_msg,
            "UBX-MON-VER": monver_msg
        }


    def _get_chipcode_from_device(self, ser, message_buffer, token):
        """
        Get chipcode from u-blox ZTP API using token and device UBX messages.
        Returns chipcode and service metadata.
        """
        # print("Getting chipcode from u-blox ZTP API...")
        # print(f"Token: {token}")

        # Get UBX messages from device
        ubx_messages = self._get_device_ubx_messages(ser, message_buffer)

        # Prepare request payload
        payload = {
            "token": token,
            "messages": ubx_messages
        }

        try:
            # print(f"Posting to {ZTP_CREDENTIALS_URL}...")
            response = requests.post(ZTP_CREDENTIALS_URL, json=payload, timeout=30)

            if response.status_code == 200:
                data = response.json()
                chipcode = data.get('chipcode')
                service_url = data.get('serviceUrl', ASSISTNOW_URL)
                allowed_data = data.get('allowedData', 'ualm')

                if chipcode:
                    # print(f"Successfully obtained chipcode: {chipcode}")
                    # print(f"Service URL: {service_url}")
                    # print(f"Allowed data types: {allowed_data}")
                    return chipcode, service_url
                else:
                    raise Exception("Response did not contain chipcode")
            else:
                self._logger.error(f"Failed to get chipcode. Status: {response.status_code}, Response: {response.text}")
                print(f"Failed to get chipcode. Status: {response.status_code}, Response: {response.text}")
                raise Exception(
                    f"Failed to get chipcode. Status: {response.status_code}, Response: {response.text}")

        except requests.exceptions.RequestException as e:
            self._logger.error(f"Error connecting to ZTP API: {e}")
            print(f"Error connecting to ZTP API: {e}")
            raise Exception(f"Error connecting to ZTP API: {e}")


    def _download_agps_data(self, chipcode, service_url=None):
        """
        Download A-GPS almanac data from u-blox AssistNow service.
        Returns the binary data if successful.
        """
        if service_url is None:
            service_url = ASSISTNOW_URL

        # print(f"Connecting to u-blox AssistNow service: {service_url}")

        params = {
            'chipcode': chipcode,
            'data': 'ualm',
            'gnss': 'gps,glo,qzss,bds,gal'
        }

        try:
            r = requests.get(service_url, params=params, stream=True, timeout=30)
            # print(f"Downloading A-GPS data, status code: {r.status_code}")

            if r.status_code == 200:
                data = r.content
                self._logger.debug(f"Downloaded {len(data)} bytes of A-GPS data")
                print(f"Downloaded {len(data)} bytes of A-GPS data:")
                # print(data)
                return data
            else:
                raise Exception(
                    f"Failed to download A-GPS data. Status code: {r.status_code}, Response: {r.text}")

        except requests.exceptions.RequestException as e:
            raise Exception(f"Error downloading A-GPS data: {e}")


    def _setUbxConfig(self, ser, message_buffer, cfg_data):
        try:
            msg = UBXMessage.config_set(
                layers=SET_LAYER_RAM, transaction=TXN_NONE, cfgData=cfg_data)

            # Send the message
            ser.write(msg.serialize())
            time.sleep(0.1)

            # Wait for ACK-ACK or ACK-NAK from message buffer
            start_time = time.time()
            timeout = 2.0

            while time.time() - start_time < timeout:
                self._read_available_messages(ser, message_buffer)
                result = message_buffer.get_message(
                    'ACK-ACK', remove=True)
                if result:
                    print(f"{cfg_data[0][0]} set successfully")
                    self._logger.debug(f"{cfg_data[0][0]} set successfully")
                    return True
                result = message_buffer.get_message(
                    'ACK-NAK', remove=True)
                if result:
                    print(f"Failed to set {cfg_data[0][0]} (NAK received)")
                    self._logger.error(f"Failed to set {cfg_data[0][0]} (NAK received)")
                    return False
                time.sleep(0.01)

            print(
                f"Warning: No ACK received for set of {cfg_data[0][0]}")
            self._logger.warning(f"Warning: No ACK received for set of {cfg_data[0][0]}")
            return True  # Assume success if no response (might already be enabled)

        except Exception as e:
            print(f"Warning: Error setting {cfg_data[0][0]}: {e}")
            self._logger.error(f"Warning: Error setting {cfg_data[0][0]}: {e}")
            return False


    def _enable_ackaiding(self, ser, message_buffer):
        """
        Enable CFG-NAVSPG-ACKAIDING to use acknowledgments in RAM.
        This configures the receiver to send UBX-MGA-ACK messages for each assistance message.
        """
        # print("Enabling CFG-NAVSPG-ACKAIDING...")

        # Value: 1 (enabled)
        # Use pyubx2 configuration interface (CFG-VALSET)
        cfg_data = [('CFG_NAVSPG_ACKAIDING', 1)]
        self._setUbxConfig(ser, message_buffer, cfg_data)


    def _enable_uart_outprot_ubx(self, ser, message_buffer, uart_key="CFG_UART1OUTPROT_UBX"):
        """
        Ensure UBX output is enabled on the specified UART (default UART1).
        Uses CFG-VALSET on the RAM layer.
        """
        # print(f"Ensuring UBX output is enabled on {uart_key}...")
        cfg_data = [(uart_key, 1)]
        self._setUbxConfig(ser, message_buffer, cfg_data)


    def _extract_ubx_messages(self, data):
        """
        Extract all UBX messages from binary data using pyubx2.
        Returns a list of UBXMessage objects.
        """
        messages = []
        bio = BytesIO(data)
        # Parse only UBX messages from the blob
        ubr = UBXReader(bio, msgmode=SET, protfilter=UBX_PROTOCOL)

        while True:
            try:
                raw, parsed = ubr.read()
                if parsed:
                    messages.append(parsed)
                else:
                    # raw is None -> EOF
                    break
            except (UBXStreamError, UBXParseError, EOFError):
                # Stop parsing on stream or parse errors
                break

        return messages


    def _wait_for_mga_ack(self, ser, message_buffer, expected_msg_id, timeout=2.0):
        """
        Wait for a UBX-MGA-ACK message from the receiver.
        expected_msg_id: The message ID of the MGA message we sent (to match the ACK)
        Returns (info_code, ack_msg_id) from the ACK, or None if timeout/error.
        Uses the message buffer to retrieve ACK messages.
        info_code meanings (per u-blox):
        0 = accepted
        1 = receiver time unknown (send MGA-INI-TIME_UTC first)
        2 = message version not supported
        3 = message size mismatch
        4 = message data could not be stored
        5 = receiver not ready to use the message data
        6 = message type unknown
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Read available messages from serial
            self._read_available_messages(ser, message_buffer)

            # Check for MGA-ACK messages in the buffer
            ack_messages = message_buffer.get_all_messages(
                identity='MGA-ACK-DATA0', remove=False)
            ack_messages.extend(message_buffer.get_all_messages(
                identity='MGA-ACK', remove=False))

            for parsed in ack_messages:
                msg_id = None
                info_code = None

                if hasattr(parsed, 'msgId'):
                    msg_id = getattr(parsed, 'msgId')

                if hasattr(parsed, 'infoCode'):
                    info_code = getattr(parsed, 'infoCode')

                if msg_id is not None and msg_id == expected_msg_id[0]:
                    # Remove this message from buffer since we found it
                    message_buffer.get_message(
                        parsed.identity, remove=True)
                    return (info_code, msg_id)
            
            #if we did not receive the expected ACK yet, drop all the messages we are 
            # not interested in to improve the search performance in the message buffer.
            message_buffer.clear()

            time.sleep(0.01)

        return None


    def _send_data_to_device(self, ser, message_buffer, data):
        """
        Send A-GPS data to the u-blox device via serial port with flow control.
        Implements proper flow control by waiting for UBX-MGA-ACK after each message.
        """
        # print("Waiting for GPS to be ready...")
        # Clear message buffer to avoid old ACKs
        message_buffer.clear()
        time.sleep(0.01)

        # print("Parsing A-GPS data into UBX messages...")
        # Extract all UBX messages from the downloaded data
        messages = self._extract_ubx_messages(data)

        if not messages:
            self._logger.error("No valid UBX messages found in downloaded AGPS data")
            raise Exception("No valid UBX messages found in downloaded AGPS data")

        # print(f"Found {len(messages)} UBX messages to send")

        # Filter for MGA messages only
        mga_messages = []
        for msg in messages:
            if msg.identity.startswith('MGA-'):
                mga_messages.append(msg)

        if not mga_messages:
            raise Exception("No UBX-MGA messages found in downloaded data")

        self._logger.debug(f"Sending {len(mga_messages)} UBX-MGA messages with flow control...")

        total_sent = 0
        successful = 0
        failed = 0
        max_retries = 3

        for i, msg in enumerate(mga_messages):
            # Get message ID from the UBXMessage object
            msg_id = None
            if hasattr(msg, 'msg_id'):
                msg_id = msg.msg_id
            else:
                # Try to get from identity string (e.g., "MGA-INI-0x01" -> 0x01)
                try:
                    if hasattr(msg, 'identity'):
                        parts = msg.identity.split('-')
                        if len(parts) >= 3:
                            msg_id = int(
                                parts[-1], 16) if parts[-1].startswith('0x') else int(parts[-1])
                except Exception:
                    pass

            if msg_id is None:
                self._logger.warning(f"Could not determine message ID for message {i+1}, skipping...")
                print(
                    f"  Warning: Could not determine message ID for message {i+1}, skipping...")
                continue

            retry_count = 0
            ack_received = False

            while retry_count < max_retries and not ack_received:
                # print("Sending message: ", msg.identity)
                # Send the message
                ser.write(msg.serialize())
                total_sent += len(msg.serialize())

                # Wait for acknowledgment
                ack_result = self._wait_for_mga_ack(
                    ser, message_buffer, msg_id, timeout=1.0)

                if ack_result:
                    info_code, ack_msg_id = ack_result

                    # Info code meanings:
                    # 0 accepted
                    # 1 time unknown (needs MGA-INI-TIME_UTC first)
                    # 2 version not supported
                    # 3 size mismatch
                    # 4 could not store
                    # 5 not ready
                    # 6 message type unknown
                    if info_code == 0:  # accepted
                        successful += 1
                        ack_received = True
                        # if (i + 1) % 10 == 0:
                        #     print(
                        #         f"  Progress: {i+1}/{len(mga_messages)} messages sent and acknowledged")
                    elif info_code == 1:  # time unknown
                        retry_count += 1
                        if retry_count < max_retries:
                            self._logger.warning(f"Message {i+1} ({msg.identity}) rejected (time unknown), retrying ({retry_count}/{max_retries})...")
                            print(
                                f"  Warning: Message {i+1} ({msg.identity}) rejected (time unknown), retrying ({retry_count}/{max_retries})...")
                            time.sleep(0.01)
                        else:
                            self._logger.warning(f"Message {i+1} ({msg.identity}) rejected (time unknown) after retries")
                            print(
                                f"  Error: Message {i+1} ({msg.identity}) rejected (time unknown) after retries")
                            failed += 1
                    else:
                        # For other codes, do not retry; count as failed and move on
                        self._logger.warning(f"Message {i+1} ({msg.identity}) failed with info_code={info_code}")
                        print(
                            f"  Warning: Message {i+1} ({msg.identity}) failed with info_code={info_code}")
                        ack_received = True
                        failed += 1
                else:
                    retry_count += 1
                    if retry_count >= max_retries:
                        # self._logger.warning(f"No ACK received for message {i+1} ({msg.identity}), retrying ({retry_count}/{max_retries})...")
                        # print(
                        #     f"  Warning: No ACK received for message {i+1} ({msg.identity}), retrying ({retry_count}/{max_retries})...")
                        # time.sleep(0.01)
                        # else:
                        failed += 1
                        self._logger.warning(f"Failed to get ACK for message {i+1} ({msg.identity}) after {max_retries} retries")
                        print(
                            f"  Error: Failed to get ACK for message {i+1} ({msg.identity}) after {max_retries} retries")

            # Small delay between messages to prevent overwhelming the receiver
            # time.sleep(0.01)

        self._logger.debug(f"Transfer complete: {total_sent} bytes sent, {successful}/{len(mga_messages)} messages acknowledged, {failed} failed")
        print(f"\nTransfer complete:")
        print(f"  Total bytes sent: {total_sent}")
        print(
            f"  Messages successfully acknowledged: {successful}/{len(mga_messages)}")
        if failed > 0:
            print(f"  Messages failed: {failed}")
        # print("Done")
    
