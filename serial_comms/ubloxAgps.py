import time
from io import BytesIO
import socket
import requests
import logging
from pyubx2 import (
    SET_LAYER_RAM,
    TXN_NONE,
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

    def __init__(self, messageArray=None):
        self._messages = messageArray if messageArray is not None else []

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
    def __init__(self, serialport, messageArray=None):
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
    
