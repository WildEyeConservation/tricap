import math
import os
import serial
import logging
from statistics import mean
from io import BytesIO
from pyubx2 import (
    NMEA_PROTOCOL,
    UBX_PROTOCOL,
    UBXReader,
)
from datetime import datetime, timedelta, timezone
from threading import Lock

from config import FALLBACK_TELEMETRY_DIR, MOUNT_POINT
from support import flight_log

logger = logging.getLogger(__name__)

class SerialProcess():
    def __init__(self, on_first_fix=None):
        super().__init__()
        # append valid reponses
        self._requests = []
        self._hasGps = False
        self._firstGps = False
        self._clock_set_from_gps = False
        self._gpsTimestamp = 0
        self._on_first_fix = on_first_fix

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
            logger.warning('Device error: %s', e)
            return False
        except Exception as e:
            logger.warning('Parse error: %s', e)
            return False
        return True

    @staticmethod
    def gps_datetime(gps_time, now=None):
        """Aware UTC datetime for a GGA time-of-day, dated by the rig's clock.

        GGA carries UTC time of day only. The date comes from the rig, and the
        result is nudged by a day when the two straddle midnight UTC.
        """
        now = now or datetime.now(timezone.utc)
        candidate = datetime.combine(now.date(), gps_time.replace(tzinfo=None),
                                     tzinfo=timezone.utc)
        if candidate - now > timedelta(hours=12):
            candidate -= timedelta(days=1)
        elif now - candidate > timedelta(hours=12):
            candidate += timedelta(days=1)
        return candidate

    def saveGga(self, msg):
        pi_time = datetime.now()
        if msg.time != None and msg.lat != '' and msg.lon != '' and self._firstGps:
            self._hasGps = True
            # Epoch seconds, so the stored timestamp does not depend on the rig's zone.
            gps_datetime = self.gps_datetime(msg.time)
            mounted = os.path.ismount(MOUNT_POINT)
            storage_dir = MOUNT_POINT if mounted else FALLBACK_TELEMETRY_DIR
            complete_dir = os.path.join(storage_dir, datetime.now().strftime('%Y_%m_%d'))
            dest = os.path.join(complete_dir, 'gpsData.csv')
            try:
                if not os.path.isdir(complete_dir):
                    if not mounted:
                        logger.warning('Internal storage not mounted; saving GPS data to %s', complete_dir)
                    os.makedirs(complete_dir, exist_ok=True)
                alt = 0.0
                if msg.alt != None:
                    alt = msg.alt
                line=(f"{str(msg.quality)},{str(gps_datetime.timestamp())},{str(pi_time.timestamp())},{str(msg.lat)},{msg.NS},{str(msg.lon)},{msg.EW},{str(alt)},{str(msg.HDOP)},{str(msg.sep)}\n")
                with open(dest, 'ta') as f:
                    f.write(line)
            except Exception as e:
                logger.warning('GPS line not saved: %s', e)
            # Friendly flight log with the laser's latest last return joined on,
            # written live so it is complete however the folder is copied.
            try:
                flight_log.append_fix(complete_dir, msg.quality, gps_datetime, pi_time,
                                      msg.lat, msg.NS, msg.lon, msg.EW, alt, msg.HDOP)
            except Exception as e:
                logger.warning('Flight log line not saved: %s', e)
                
        else:
            self._hasGps = False

    def saveRmc(self, msg):
        if msg.date != None and msg.time != None and msg.lat != '' and msg.lon != '' and not self._clock_set_from_gps:
            self._firstGps = True
            gps_time = datetime.combine(
                msg.date, msg.time.replace(tzinfo=None), tzinfo=timezone.utc)
            # Retried on the next RMC if setting the clock fails, so a transient
            # error does not leave the rig on phone time for the whole flight.
            self._clock_set_from_gps = True
            if self._on_first_fix is not None:
                try:
                    self._on_first_fix(gps_time)
                except Exception as exc:
                    self._clock_set_from_gps = False
                    logger.warning('First GPS fix callback failed: %s', exc)

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
