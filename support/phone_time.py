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
