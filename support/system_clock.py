"""Validation and coordinated system-clock updates for the rig."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import subprocess
import threading
import time


logger = logging.getLogger(__name__)


MIN_PHONE_EPOCH_MS = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
MAX_PHONE_EPOCH_MS = datetime(2100, 1, 1, tzinfo=timezone.utc).timestamp() * 1000


def validate_phone_time(payload):
    """Return validated ``(epoch_ms, timezone_offset_minutes)`` values."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")

    epoch_ms = payload.get("epochMs")
    if isinstance(epoch_ms, bool) or not isinstance(epoch_ms, (int, float)):
        raise ValueError("epochMs must be a number")
    epoch_ms = float(epoch_ms)
    if not math.isfinite(epoch_ms):
        raise ValueError("epochMs must be finite")
    if not MIN_PHONE_EPOCH_MS <= epoch_ms < MAX_PHONE_EPOCH_MS:
        raise ValueError("Phone time must be between 2024 and 2100")

    timezone_offset = payload.get("timezoneOffsetMinutes")
    if timezone_offset is not None:
        if (isinstance(timezone_offset, bool) or
                not isinstance(timezone_offset, (int, float)) or
                not math.isfinite(float(timezone_offset))):
            raise ValueError("timezoneOffsetMinutes must be a number")
        timezone_offset = int(timezone_offset)
        if not -14 * 60 <= timezone_offset <= 14 * 60:
            raise ValueError("timezoneOffsetMinutes is out of range")

    return epoch_ms, timezone_offset


def timezone_name_for_offset(offset_minutes):
    """IANA zone matching a browser ``getTimezoneOffset()`` value, or None.

    The browser reports minutes *behind* UTC (UTC+2 -> -120), and the POSIX
    ``Etc/GMT`` zones are signed the same way (``Etc/GMT-2`` is UTC+2). Only
    whole-hour offsets have such a zone; the rig cannot represent others.
    """
    if offset_minutes is None or offset_minutes % 60:
        return None
    if offset_minutes == 0:
        return "Etc/UTC"
    hours = abs(offset_minutes) // 60
    return "Etc/GMT{}{}".format("+" if offset_minutes > 0 else "-", hours)


def set_system_timezone(offset_minutes) -> str | None:
    """Point the system timezone at the phone's UTC offset; returns the zone or None.

    Fixed-offset zones carry no daylight-saving rules. The change is
    best-effort and never fails the clock update.
    """
    zone = timezone_name_for_offset(offset_minutes)
    if zone is None:
        return None
    try:
        subprocess.run(
            ["timedatectl", "set-timezone", zone],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if hasattr(time, "tzset"):
        # Make the running process see the new /etc/localtime.
        time.tzset()
    return zone


def set_system_time(epoch_seconds: float) -> dict:
    """Set Linux system time and persist it to the RTC.

    ``date`` is used because it works whether or not systemd-timesyncd is
    running. The RTC update is best-effort: a missing or inaccessible RTC must
    not undo a successful system-clock update.
    """
    target_seconds = float(epoch_seconds)
    previous_seconds = time.time()

    subprocess.run(
        ["date", "--set", "@{:.3f}".format(target_seconds)],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )

    rtc_synced = True
    try:
        subprocess.run(
            ["hwclock", "--systohc", "--utc"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        rtc_synced = False

    return {
        "previousEpochMs": round(previous_seconds * 1000),
        "deviceEpochMs": round(time.time() * 1000),
        "adjustmentMs": round(target_seconds * 1000 -
                              previous_seconds * 1000),
        "rtcSynced": rtc_synced,
    }


def disable_ntp() -> bool:
    """Disable NTP so timesyncd does not fight GPS or phone time."""
    try:
        subprocess.run(
            ["timedatectl", "set-ntp", "false"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Could not disable system NTP: %s", exc)
        return False
    return True


class ClockSync:
    """Serialize clock changes and enforce GPS authority once available."""

    def __init__(self, on_synced=None):
        self._lock = threading.Lock()
        self._on_synced = on_synced
        self.source = "none"

    def _camera_result(self, source):
        cameras_synced = 0
        camera_errors = []
        if self._on_synced is not None:
            try:
                callback_result = self._on_synced(source)
                if callback_result is not None:
                    cameras_synced, camera_errors = callback_result
            except Exception as exc:
                camera_errors = [str(exc) or type(exc).__name__]
                logger.warning("Clock synced but camera clock sync failed: %s", exc)
        return {
            "camerasSynced": cameras_synced,
            "cameraErrors": camera_errors,
        }

    def sync_from_phone(self, epoch_ms, offset_minutes) -> dict:
        with self._lock:
            timezone_name = set_system_timezone(offset_minutes)
            if self.source == "gps":
                now_ms = round(time.time() * 1000)
                return {
                    "previousEpochMs": now_ms,
                    "deviceEpochMs": now_ms,
                    "adjustmentMs": 0,
                    "rtcSynced": False,
                    "source": "gps",
                    "timeApplied": False,
                    "timezone": timezone_name,
                    "camerasSynced": 0,
                    "cameraErrors": [],
                }

            result = set_system_time(epoch_ms / 1000.0)
            self.source = "phone"
            result.update({
                "source": self.source,
                "timeApplied": True,
                "timezone": timezone_name,
            })
            result.update(self._camera_result(self.source))
            return result

    def sync_from_gps(self, utc_datetime) -> dict:
        with self._lock:
            result = set_system_time(utc_datetime.timestamp())
            self.source = "gps"
            result.update({
                "source": self.source,
                "timeApplied": True,
            })
            result.update(self._camera_result(self.source))
            return result
