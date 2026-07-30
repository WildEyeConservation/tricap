"""GPS lookup and lossless ARW geotagging helpers.

The SkySeeker GPS log is a one-Hz, headerless CSV.  This module deliberately
keeps the matching rules independent from the backup manager so they can be
tested without camera, mount, or Flask dependencies.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable


MAX_GPS_GAP_SECONDS = 3.0
MIN_IMAGE_HASH_EXIFTOOL_VERSION = (12, 63)


@dataclass(frozen=True)
class GPSFix:
    timestamp: float
    latitude: float
    longitude: float
    altitude: float | None
    quality: int
    hdop: float | None
    source: str = "onboard"
    accuracy_m: float | None = None
    utc_timestamp: float | None = None


@dataclass(frozen=True)
class GPSMatch:
    timestamp: float
    latitude: float
    longitude: float
    altitude: float | None
    hdop: float | None
    method: str  # exact | interpolated | nearest
    source: str = "onboard"
    accuracy_m: float | None = None
    utc_timestamp: float | None = None


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _coordinate(value: str, reference: str, positive: str, negative: str) -> float:
    number = float(value)
    ref = reference.strip().upper()
    if ref == positive:
        return abs(number)
    if ref == negative:
        return -abs(number)
    return number


def parse_gps_rows(rows: Iterable[list[str]]) -> list[GPSFix]:
    """Parse, validate, de-duplicate and sort SkySeeker GPS CSV rows."""
    by_timestamp: dict[float, GPSFix] = {}
    for row in rows:
        if len(row) < 9:
            continue
        try:
            quality = int(float(row[0]))
            timestamp = float(row[1])
            latitude = _coordinate(row[3], row[4], "N", "S")
            longitude = _coordinate(row[5], row[6], "E", "W")
            altitude = float(row[7])
            hdop = float(row[8])
        except (TypeError, ValueError, OverflowError):
            continue
        if quality <= 0:
            continue
        if not all(_finite(v) for v in (timestamp, latitude, longitude, altitude, hdop)):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        fix = GPSFix(timestamp, latitude, longitude, altitude, quality, hdop)
        previous = by_timestamp.get(timestamp)
        # Prefer the duplicate with the better (lower) dilution of precision.
        if previous is None or fix.hdop < previous.hdop:
            by_timestamp[timestamp] = fix
    return sorted(by_timestamp.values(), key=lambda fix: fix.timestamp)


def load_gps_csv(path: Path) -> list[GPSFix]:
    try:
        with path.open("r", newline="", encoding="utf-8", errors="ignore") as handle:
            # Power-loss/recovery has left NUL padding at the end of some field
            # logs. Ignore it while retaining every complete CSV record.
            clean_lines = (line.replace("\x00", "") for line in handle)
            return parse_gps_rows(csv.reader(clean_lines))
    except (FileNotFoundError, OSError):
        return []


def parse_phone_gps_rows(rows: Iterable[dict[str, str]]) -> list[GPSFix]:
    """Parse the separate, headered phone backup log without hiding its source."""
    by_timestamp: dict[float, GPSFix] = {}
    for row in rows:
        try:
            phone_timestamp = float(row.get("timestamp", ""))
            match_timestamp = float(row.get("match_timestamp") or phone_timestamp)
            latitude = float(row.get("latitude", ""))
            longitude = float(row.get("longitude", ""))
            accuracy = float(row.get("accuracy", ""))
            altitude_text = row.get("altitude", "").strip()
            altitude = float(altitude_text) if altitude_text else None
        except (AttributeError, TypeError, ValueError, OverflowError):
            continue
        finite_values = [phone_timestamp, match_timestamp, latitude, longitude, accuracy]
        if altitude is not None:
            finite_values.append(altitude)
        if not all(_finite(value) for value in finite_values):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        if not (0.0 <= accuracy <= 1000.0):
            continue
        # Keep both clock domains as candidates. Camera EXIF may follow either
        # the rig clock or its own previously-set UTC clock. Both candidates
        # retain the phone's actual UTC timestamp for the GPS EXIF date/time.
        candidate_timestamps = {match_timestamp, phone_timestamp}
        for timestamp in candidate_timestamps:
            fix = GPSFix(
                timestamp, latitude, longitude, altitude, 1, None,
                source="phone", accuracy_m=accuracy, utc_timestamp=phone_timestamp,
            )
            previous = by_timestamp.get(timestamp)
            if previous is None or accuracy < (previous.accuracy_m or float("inf")):
                by_timestamp[timestamp] = fix
    return sorted(by_timestamp.values(), key=lambda fix: fix.timestamp)


def load_phone_gps_csv(path: Path) -> list[GPSFix]:
    try:
        with path.open("r", newline="", encoding="utf-8", errors="ignore") as handle:
            clean_lines = (line.replace("\x00", "") for line in handle)
            return parse_phone_gps_rows(csv.DictReader(clean_lines))
    except (FileNotFoundError, OSError):
        return []


def match_gps(
    fixes: list[GPSFix],
    image_timestamp: float,
    max_gap_seconds: float = MAX_GPS_GAP_SECONDS,
) -> GPSMatch | None:
    """Match an image time by exact fix, short interpolation, then nearest fix."""
    if not fixes or not _finite(image_timestamp):
        return None
    times = [fix.timestamp for fix in fixes]
    index = bisect.bisect_left(times, image_timestamp)

    if index < len(fixes) and fixes[index].timestamp == image_timestamp:
        fix = fixes[index]
        return GPSMatch(
            fix.timestamp, fix.latitude, fix.longitude, fix.altitude, fix.hdop,
            "exact", fix.source, fix.accuracy_m, fix.utc_timestamp,
        )

    if 0 < index < len(fixes):
        before = fixes[index - 1]
        after = fixes[index]
        span = after.timestamp - before.timestamp
        if 0.0 < span <= max_gap_seconds:
            ratio = (image_timestamp - before.timestamp) / span
            altitude = None
            if before.altitude is not None and after.altitude is not None:
                altitude = before.altitude + ratio * (after.altitude - before.altitude)
            accuracy = None
            if before.accuracy_m is not None or after.accuracy_m is not None:
                accuracy = max(value for value in (before.accuracy_m, after.accuracy_m) if value is not None)
            utc_timestamp = None
            if before.utc_timestamp is not None and after.utc_timestamp is not None:
                utc_timestamp = before.utc_timestamp + ratio * (after.utc_timestamp - before.utc_timestamp)
            return GPSMatch(
                image_timestamp,
                before.latitude + ratio * (after.latitude - before.latitude),
                before.longitude + ratio * (after.longitude - before.longitude),
                altitude,
                before.hdop if ratio < 0.5 else after.hdop,
                "interpolated",
                before.source if before.source == after.source else "mixed",
                accuracy,
                utc_timestamp,
            )

    candidates: list[GPSFix] = []
    if index > 0:
        candidates.append(fixes[index - 1])
    if index < len(fixes):
        candidates.append(fixes[index])
    if not candidates:
        return None
    nearest = min(candidates, key=lambda fix: abs(fix.timestamp - image_timestamp))
    if abs(nearest.timestamp - image_timestamp) > max_gap_seconds:
        return None
    return GPSMatch(
        nearest.timestamp,
        nearest.latitude,
        nearest.longitude,
        nearest.altitude,
        nearest.hdop,
        "nearest",
        nearest.source,
        nearest.accuracy_m,
        nearest.utc_timestamp,
    )


_DATE_FORMATS = (
    "%Y:%m:%d %H:%M:%S%z",
    "%Y:%m:%d %H:%M:%S.%f%z",
    "%Y:%m:%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S.%f",
)


def image_timestamp_from_tags(tags: dict[str, Any]) -> float:
    value = str(
        tags.get("SubSecDateTimeOriginal")
        or tags.get("DateTimeOriginal")
        or tags.get("EXIF:DateTimeOriginal")
        or ""
    ).strip()
    offset = str(tags.get("OffsetTimeOriginal") or tags.get("EXIF:OffsetTimeOriginal") or "").strip()
    if offset and not re.search(r"(?:Z|[+-]\d\d:?\d\d)$", value):
        value += offset
    parsed = None
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError("ARW has no usable DateTimeOriginal")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=2)))
    # Whole-second matching is intentional even if a future camera supplies subseconds.
    parsed = parsed.replace(microsecond=0)
    return parsed.timestamp()


def required_gps_present(tags: dict[str, Any]) -> bool:
    names = {key.split(":")[-1] for key in tags}
    return {
        "GPSLatitude",
        "GPSLatitudeRef",
        "GPSLongitude",
        "GPSLongitudeRef",
        "GPSDateStamp",
        "GPSTimeStamp",
    }.issubset(names)


def gps_exif_arguments(match: GPSMatch) -> list[str]:
    utc = datetime.fromtimestamp(
        match.utc_timestamp if match.utc_timestamp is not None else match.timestamp,
        timezone.utc,
    )
    if match.source == "phone":
        method = "SkySeeker phone GPS backup"
    elif match.method == "nearest":
        method = "SkySeeker nearest onboard GPS fix"
    elif match.method == "interpolated":
        method = "SkySeeker onboard GPS interpolation"
    else:
        method = "SkySeeker onboard GPS fix"
    arguments = [
        f"-EXIF:GPSLatitude={abs(match.latitude):.10f}",
        f"-EXIF:GPSLatitudeRef={'S' if match.latitude < 0 else 'N'}",
        f"-EXIF:GPSLongitude={abs(match.longitude):.10f}",
        f"-EXIF:GPSLongitudeRef={'W' if match.longitude < 0 else 'E'}",
        f"-EXIF:GPSDateStamp={utc.strftime('%Y:%m:%d')}",
        f"-EXIF:GPSTimeStamp={utc.strftime('%H:%M:%S')}",
        "-EXIF:GPSStatus=A",
        "-EXIF:GPSMeasureMode#=3",
        "-EXIF:GPSMapDatum=WGS-84",
        f"-EXIF:GPSProcessingMethod={method}",
    ]
    if match.altitude is not None:
        arguments.extend([
            f"-EXIF:GPSAltitude={abs(match.altitude):.3f}",
            f"-EXIF:GPSAltitudeRef#={1 if match.altitude < 0 else 0}",
        ])
    if match.hdop is not None:
        arguments.append(f"-EXIF:GPSDOP={match.hdop:.3f}")
    if match.accuracy_m is not None:
        arguments.append(f"-EXIF:GPSHPositioningError={match.accuracy_m:.3f}")
    return arguments


class ExifToolARW:
    """Small subprocess wrapper with explicit output and verification semantics."""

    READ_TAGS = (
        "DateTimeOriginal", "SubSecDateTimeOriginal", "OffsetTimeOriginal",
        "GPSLatitude", "GPSLatitudeRef", "GPSLongitude", "GPSLongitudeRef",
        "GPSAltitude", "GPSAltitudeRef", "GPSDateStamp", "GPSTimeStamp",
        "OriginalImageHash", "OriginalImageHashType",
    )

    def __init__(self, executable: str = "exiftool") -> None:
        self.executable = executable
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[str] | None = None

    def cancel(self) -> None:
        with self._process_lock:
            process = self._active_process
        if process is not None and process.poll() is None:
            process.terminate()

    def version(self) -> tuple[int, ...]:
        result = subprocess.run(
            [self.executable, "-ver"], check=True, capture_output=True, text=True,
        )
        return tuple(int(part) for part in result.stdout.strip().split("."))

    def require_supported_version(self) -> None:
        if self.version() < MIN_IMAGE_HASH_EXIFTOOL_VERSION:
            raise RuntimeError("ExifTool 12.63 or newer is required for safe ARW verification")

    def read_tags(self, path: Path) -> dict[str, Any]:
        command = [self.executable, "-j", "-n"]
        command.extend(f"-{tag}" for tag in self.READ_TAGS)
        command.append(str(path))
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        if not data:
            raise RuntimeError(f"ExifTool returned no metadata for {path}")
        return data[0]

    def image_data_hash(self, path: Path) -> str:
        result = subprocess.run(
            [
                self.executable,
                "-s3",
                "-api", "RequestTags=ImageDataHash",
                "-api", "ImageHashType=SHA256",
                "-ImageDataHash",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        digest = result.stdout.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Could not calculate ARW ImageDataHash for {path}")
        return digest

    def write_copy(self, source: Path, output: Path, match: GPSMatch | None) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        command = [
            self.executable,
            "-api", "ImageHashType=SHA256",
            "-OriginalImageHash<ImageDataHash",
            "-OriginalImageHashType=SHA256",
        ]
        if match is not None:
            command.extend(gps_exif_arguments(match))
        command.extend(["-o", str(output), str(source)])
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with self._process_lock:
            self._active_process = process
        try:
            stdout, stderr = process.communicate()
        finally:
            with self._process_lock:
                if self._active_process is process:
                    self._active_process = None
        if process.returncode != 0 or not output.is_file():
            raise RuntimeError((stderr or stdout or "ExifTool output failed").strip())

    def copy_untagged(self, source: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        shutil.copy2(source, output)

    def read_verification_tags(self, path: Path) -> dict[str, Any]:
        """Read GPS, stored source hash, and destination image hash in one pass."""
        command = [
            self.executable,
            "-j", "-n",
            "-api", "RequestTags=ImageDataHash",
            "-api", "ImageHashType=SHA256",
        ]
        command.extend(f"-{tag}" for tag in self.READ_TAGS)
        command.extend(["-ImageDataHash", str(path)])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        if not data:
            raise RuntimeError(f"ExifTool returned no verification data for {path}")
        return data[0]

    def validate_tagged(self, destination: Path) -> bool:
        """Validate GPS and lossless image data using the embedded source hash.

        ``OriginalImageHash`` is calculated from the source ARW while ExifTool
        writes the tagged copy. Recalculating only the destination ImageDataHash
        therefore proves equality without reading and hashing the source again.
        """
        tags = self.read_verification_tags(destination)
        if not required_gps_present(tags):
            return False
        stored = str(tags.get("OriginalImageHash") or "").lower()
        destination_hash = str(tags.get("ImageDataHash") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", stored):
            return False
        return stored == destination_hash


class GPSIndex:
    def __init__(self, source_root: Path, max_gap_seconds: float = MAX_GPS_GAP_SECONDS) -> None:
        self.source_root = source_root
        self.max_gap_seconds = max_gap_seconds
        self._cache: dict[str, list[GPSFix]] = {}
        self._phone_cache: dict[str, list[GPSFix]] = {}

    def fixes_for_image(self, image: Path) -> list[GPSFix]:
        relative = image.resolve().relative_to(self.source_root.resolve())
        if not relative.parts:
            return []
        date_dir = relative.parts[0]
        if date_dir not in self._cache:
            self._cache[date_dir] = load_gps_csv(self.source_root / date_dir / "gpsData.csv")
        return self._cache[date_dir]

    def phone_fixes_for_image(self, image: Path) -> list[GPSFix]:
        relative = image.resolve().relative_to(self.source_root.resolve())
        if not relative.parts:
            return []
        date_dir = relative.parts[0]
        if date_dir not in self._phone_cache:
            self._phone_cache[date_dir] = load_phone_gps_csv(
                self.source_root / date_dir / "phoneGpsData.csv"
            )
        return self._phone_cache[date_dir]

    def match_image(self, image: Path, tags: dict[str, Any]) -> GPSMatch | None:
        timestamp = image_timestamp_from_tags(tags)
        onboard = match_gps(self.fixes_for_image(image), timestamp, self.max_gap_seconds)
        if onboard is not None:
            return onboard
        return match_gps(self.phone_fixes_for_image(image), timestamp, self.max_gap_seconds)


def fsync_file_and_parent(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # Some exFAT/FUSE combinations do not allow directory fsync.
        pass


__all__ = [
    "ExifToolARW", "GPSFix", "GPSIndex", "GPSMatch", "MAX_GPS_GAP_SECONDS",
    "fsync_file_and_parent", "gps_exif_arguments", "image_timestamp_from_tags",
    "load_gps_csv", "load_phone_gps_csv", "match_gps", "parse_gps_rows",
    "parse_phone_gps_rows", "required_gps_present",
]
