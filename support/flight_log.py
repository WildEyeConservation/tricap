"""Live, user-friendly flight log written beside the raw GPS and altimeter logs.

``gpsData.csv`` and ``altitudeData.csv`` are the raw, append-only sensor logs.
This module writes a third file, ``flightData.csv``, into the same day folder
as each GPS fix arrives, so the friendly version already exists on disk no
matter how the folder is copied off the device (app backup, manual rsync, or
pulling the drive). Each row carries the laser altimeter's most recent last
return, or a blank when the laser was not measuring at the time.
"""

from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime

FLIGHT_LOG_FILENAME = "flightData.csv"
FLIGHT_LOG_HEADER = (
    "Fix Quality",
    "GPS Time",
    "GPS Timestamp",
    "System Time",
    "System Timestamp",
    "Latitude",
    "Longitude",
    "GPS Altitude",
    "Laser Altitude",
    "HDOP",
)
# A laser sample older than this is not joined onto a GPS fix.
LASER_FRESH_SECONDS = 2.0

_laser_lock = threading.Lock()
_laser_value: float | None = None
_laser_at: float | None = None


def record_laser_altitude(last_return: float | None, at: float | None = None) -> None:
    """Remember the altimeter's latest last-return distance (metres, or None)."""
    global _laser_value, _laser_at
    with _laser_lock:
        _laser_value = last_return
        _laser_at = time.monotonic() if at is None else at


def latest_laser_altitude(now: float | None = None,
                          fresh_seconds: float = LASER_FRESH_SECONDS) -> float | None:
    """Return the latest last-return distance if it is recent enough, else None."""
    with _laser_lock:
        value, at = _laser_value, _laser_at
    if value is None or at is None:
        return None
    now = time.monotonic() if now is None else now
    if now - at > fresh_seconds:
        return None
    return value


def signed_coordinate(value, hemisphere, negative: str) -> float:
    """Turn a magnitude plus N/S or E/W hemisphere into a signed decimal degree."""
    number = abs(float(value))
    if str(hemisphere).strip().upper() == negative:
        return -number
    return number


def _number(value, digits: int) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return ""


def _time(value: datetime) -> str:
    return value.isoformat(sep=" ", timespec="milliseconds")


def _timestamp(value: datetime) -> str:
    """Epoch seconds, matching the raw gpsData.csv columns."""
    return str(value.timestamp())


def format_row(quality, gps_time: datetime, system_time: datetime,
               latitude, ns, longitude, ew, gps_altitude, hdop,
               laser_altitude: float | None) -> list[str]:
    """Build one flight-log row in the order of FLIGHT_LOG_HEADER."""
    return [
        "" if quality is None else str(quality),
        _time(gps_time),
        _timestamp(gps_time),
        _time(system_time),
        _timestamp(system_time),
        _number(signed_coordinate(latitude, ns, "S"), 7),
        _number(signed_coordinate(longitude, ew, "W"), 7),
        _number(gps_altitude, 2),
        _number(laser_altitude, 2),
        _number(hdop, 2),
    ]


def append_fix(directory: str, quality, gps_time: datetime, system_time: datetime,
               latitude, ns, longitude, ew, gps_altitude, hdop,
               laser_altitude: float | None = None,
               use_latest_laser: bool = True) -> str:
    """Append one GPS fix to ``flightData.csv`` in *directory*, creating it with
    a header when needed. Returns the path written.

    When *use_latest_laser* is true the altimeter's latest fresh last return is
    joined on; pass ``laser_altitude`` explicitly (and set it false) to override.
    """
    if use_latest_laser:
        laser_altitude = latest_laser_altitude()
    row = format_row(quality, gps_time, system_time, latitude, ns, longitude, ew,
                     gps_altitude, hdop, laser_altitude)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, FLIGHT_LOG_FILENAME)
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(FLIGHT_LOG_HEADER)
        writer.writerow(row)
    return path
