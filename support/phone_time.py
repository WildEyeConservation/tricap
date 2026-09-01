"""Validation and system-clock updates for browser-supplied phone time."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import subprocess
import time


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


def set_system_timezone_from_phone(offset_minutes):
    """Point the system timezone at the phone's UTC offset; returns the zone or None.

    Fixed-offset zones carry no daylight-saving rules, which is fine because the
    rig is re-synchronised every time a dashboard client connects. The change
    is best-effort and never fails the clock update.
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


def set_system_time_from_phone(epoch_ms):
    """Set Linux system time and persist it to the RTC.

    ``date`` is used instead of ``timedatectl set-time`` because timedatectl
    rejects manual changes while systemd-timesyncd is enabled. The RTC update
    is best-effort: a missing or inaccessible RTC must not undo a successful
    system-clock update.
    """
    target_seconds = epoch_ms / 1000.0
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
