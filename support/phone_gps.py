"""Receive and durably store backup GPS fixes supplied by an operator's phone."""
from __future__ import annotations

import csv
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PHONE_GPS_FILENAME = "phoneGpsData.csv"
PHONE_GPS_HEADER = (
    "timestamp", "match_timestamp", "received_at", "latitude", "longitude", "altitude",
    "accuracy", "altitude_accuracy", "speed", "bearing", "device_id",
    "client_ip",
)
MAX_BATCH_SIZE = 600
FRESH_SECONDS = 15.0
MIN_TIMESTAMP = 946684800.0   # 2000-01-01 UTC
MAX_TIMESTAMP = 4102444800.0  # 2100-01-01 UTC


@dataclass(frozen=True)
class PhoneLocation:
    timestamp: float
    latitude: float
    longitude: float
    altitude: float | None
    accuracy: float
    altitude_accuracy: float | None
    speed: float | None
    bearing: float | None
    device_id: str


def _number(value: Any, name: str, *, required: bool = True) -> float | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{name} is required")
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def normalize_phone_location(payload: dict[str, Any], default_device_id: str = "") -> PhoneLocation:
    """Validate the native-app payload and normalize timestamps to Unix seconds."""
    if not isinstance(payload, dict):
        raise ValueError("each fix must be a JSON object")

    timestamp_ms = payload.get("timestampMs")
    raw_timestamp = timestamp_ms if timestamp_ms is not None else payload.get("timestamp", payload.get("time"))
    timestamp = _number(raw_timestamp, "timestamp")
    if timestamp_ms is not None or timestamp > 100_000_000_000:
        timestamp /= 1000.0
    if not MIN_TIMESTAMP <= timestamp <= MAX_TIMESTAMP:
        raise ValueError("timestamp is outside the supported 2000-2100 range")

    latitude = _number(payload.get("latitude", payload.get("lat")), "latitude")
    longitude = _number(payload.get("longitude", payload.get("lon", payload.get("lng"))), "longitude")
    if not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude must be between -180 and 180")

    accuracy = _number(payload.get("accuracy", payload.get("horizontalAccuracy")), "accuracy")
    if not 0.0 <= accuracy <= 1000.0:
        raise ValueError("accuracy must be between 0 and 1000 metres")

    altitude = _number(payload.get("altitude"), "altitude", required=False)
    altitude_accuracy = _number(
        payload.get("altitudeAccuracy", payload.get("verticalAccuracy")),
        "altitudeAccuracy", required=False,
    )
    if altitude_accuracy is not None and altitude_accuracy < 0:
        raise ValueError("altitudeAccuracy cannot be negative")
    speed = _number(payload.get("speed"), "speed", required=False)
    if speed is not None and speed < 0:
        raise ValueError("speed cannot be negative")
    bearing = _number(payload.get("bearing", payload.get("heading")), "bearing", required=False)
    if bearing is not None:
        bearing %= 360.0

    device_id = str(payload.get("deviceId") or default_device_id or "phone").strip()
    device_id = " ".join(device_id.split())[:80] or "phone"
    return PhoneLocation(
        timestamp, latitude, longitude, altitude, accuracy,
        altitude_accuracy, speed, bearing, device_id,
    )


class PhoneGPSRecorder:
    """Thread-safe CSV recorder with a small in-memory connection status."""

    def __init__(
        self,
        primary_root: Path = Path("/mnt/ext_cam_storage"),
        fallback_root: Path = Path("/home/radxa/GPS_IMU_Data"),
        mount_check: Callable[[str], bool] = os.path.ismount,
    ) -> None:
        self.primary_root = Path(primary_root)
        self.fallback_root = Path(fallback_root)
        self.mount_check = mount_check
        self._lock = threading.Lock()
        self._last: PhoneLocation | None = None
        self._last_received_at: float | None = None
        self._last_received_monotonic: float | None = None
        self._stored = 0
        self._logger = logging.getLogger(__name__)

    def _root(self) -> Path:
        return self.primary_root if self.mount_check(str(self.primary_root)) else self.fallback_root

    @staticmethod
    def _row(
        fix: PhoneLocation,
        match_timestamp: float,
        received_at: float,
        client_ip: str,
    ) -> list[Any]:
        return [
            f"{fix.timestamp:.3f}", f"{match_timestamp:.3f}", f"{received_at:.3f}",
            f"{fix.latitude:.10f}", f"{fix.longitude:.10f}",
            "" if fix.altitude is None else f"{fix.altitude:.3f}",
            f"{fix.accuracy:.3f}",
            "" if fix.altitude_accuracy is None else f"{fix.altitude_accuracy:.3f}",
            "" if fix.speed is None else f"{fix.speed:.3f}",
            "" if fix.bearing is None else f"{fix.bearing:.3f}",
            fix.device_id, client_ip,
        ]

    def record(self, payload: dict[str, Any], client_ip: str = "") -> dict[str, Any]:
        raw_fixes = payload.get("fixes") if isinstance(payload, dict) else None
        if raw_fixes is None:
            raw_fixes = [payload]
        if not isinstance(raw_fixes, list) or not raw_fixes:
            raise ValueError("fixes must be a non-empty array")
        if len(raw_fixes) > MAX_BATCH_SIZE:
            raise ValueError(f"a batch may contain at most {MAX_BATCH_SIZE} fixes")

        default_device_id = str(payload.get("deviceId") or "") if isinstance(payload, dict) else ""
        fixes = [normalize_phone_location(item, default_device_id) for item in raw_fixes]
        received_at = time.time()
        received_monotonic = time.monotonic()

        # Browser timestamps use the phone's correct UTC clock, while an offline
        # rig may retain an old system clock.  Keep both: the phone timestamp is
        # authoritative for GPS EXIF, and the translated timestamp is used only
        # to match fixes to images captured on the rig/camera clock.
        raw_client_sent_at = payload.get("clientSentAtMs") if isinstance(payload, dict) else None
        try:
            client_sent_at = float(raw_client_sent_at)
            if client_sent_at > 100_000_000_000:
                client_sent_at /= 1000.0
            if not math.isfinite(client_sent_at) or not MIN_TIMESTAMP <= client_sent_at <= MAX_TIMESTAMP:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            client_sent_at = fixes[-1].timestamp
        clock_offset = received_at - client_sent_at

        # Group by the translated rig date so the log lands beside the image
        # session even when the rig has no RTC, GPS, or internet time source.
        rows_by_path: dict[Path, list[list[Any]]] = {}
        root = self._root()
        for fix in fixes:
            match_timestamp = fix.timestamp + clock_offset
            day = datetime.fromtimestamp(match_timestamp).strftime("%Y_%m_%d")
            path = root / day / PHONE_GPS_FILENAME
            rows_by_path.setdefault(path, []).append(
                self._row(fix, match_timestamp, received_at, client_ip)
            )

        with self._lock:
            for path, rows in rows_by_path.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                new_file = not path.exists() or path.stat().st_size == 0
                with path.open("a", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    if new_file:
                        writer.writerow(PHONE_GPS_HEADER)
                    writer.writerows(rows)
                    handle.flush()
                    os.fsync(handle.fileno())
            self._last = fixes[-1]
            self._last_received_at = received_at
            self._last_received_monotonic = received_monotonic
            self._stored += len(fixes)

        self._logger.debug("Stored %d phone GPS fix(es) from %s", len(fixes), client_ip or "unknown")
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            last = self._last
            received_at = self._last_received_at
            received_monotonic = self._last_received_monotonic
            stored = self._stored
        age = None if received_monotonic is None else max(0.0, time.monotonic() - received_monotonic)
        connected = age is not None and age <= FRESH_SECONDS
        if connected:
            message = "Phone GPS backup is active."
        elif last is not None:
            message = "Phone GPS backup is stale; keep the dashboard open or restart sharing."
        else:
            message = "Waiting for phone GPS from the dashboard."
        return {
            "available": True,
            "connected": connected,
            "fresh": connected,
            "lastUpdate": None if age is None else round(age, 1),
            "lastReceivedAt": received_at,
            "fixTimestamp": None if last is None else last.timestamp,
            "accuracy": None if last is None else last.accuracy,
            "deviceId": None if last is None else last.device_id,
            "storedThisRun": stored,
            "message": message,
        }


phone_gps_recorder = PhoneGPSRecorder()


__all__ = [
    "FRESH_SECONDS", "MAX_BATCH_SIZE", "PHONE_GPS_FILENAME", "PHONE_GPS_HEADER",
    "PhoneGPSRecorder", "PhoneLocation", "normalize_phone_location", "phone_gps_recorder",
]
