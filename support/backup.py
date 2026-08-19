# backup.py
# Minimal rsync-backed backup engine with simple filesystem-snapshot progress.
from __future__ import annotations

import os
import signal
import subprocess
from collections import defaultdict
import threading
import time
import shutil
import tempfile
import hashlib
import concurrent.futures
import logging
import csv
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable
from app import tricap_manager
from support.gps_geotag import (
    ExifToolARW,
    GPSIndex,
    fsync_file_and_parent,
    required_gps_present,
)

# Finest timestamp resolution exFAT can store: a 10 ms "centisecond" field on top of
# the 2 s DOS base, i.e. 10 ms. The source NVMe is ext4 (full-nanosecond mtimes), so
# after an rsync copy the destination mtime is the source mtime quantized to the
# nearest 10 ms. An exact-nanosecond comparison can therefore never match on exFAT.
# We compare within this tolerance instead; the sampled content fingerprint
# (size + blake2b of sampled blocks) remains the real proof of file equality.
EXFAT_MTIME_RESOLUTION_NS = 10_000_000  # 10 ms
LIVE_TELEMETRY_NAMES = {"gpsData.csv", "phoneGpsData.csv", "altitudeData.csv", "accelData.bin"}
BACKUP_BENCHMARK_LOG = Path(
    os.environ.get("SKYSEEKER_BACKUP_BENCHMARK_LOG", "/home/radxa/tricap/logs/backup_benchmark.csv")
)

@dataclass
class BackupStatus:
    running: bool = False
    phase: str = "idle"                # idle | copying | stopping | finished | error
    message: str = ""
    started_at: float | None = None
    finished_at: float | None = None

    # Totals (computed once at start)
    total_files: int = 0
    total_bytes: int = 0

    # Snapshotted progress (recomputed on status())
    files_done: int = 0
    bytes_copied: int = 0

    # Verification / deletion helpers
    verify_mode: str = "none"           # none | checksum | sha256
    verified: bool = False
    verify_missing: int = 0
    verify_changed: int = 0
    verify_extra: int = 0
    verify_samples: list[str] | None = None
    dst_files: int = 0
    dst_bytes: int = 0
    ready_to_delete: bool = False

    current_file: str = ""
    gps_tagged: int = 0
    gps_interpolated: int = 0
    gps_nearest: int = 0
    gps_unresolved: int = 0
    gps_failed: int = 0
    tag_gps: bool = False
    planned_bytes: int = 0
    planned_files: int = 0
    elapsed_seconds: float = 0.0
    copy_seconds: float = 0.0
    tag_seconds: float = 0.0
    throughput_mib_s: float = 0.0


    def __post_init__(self) -> None:
        if self.verify_samples is None:
            self.verify_samples = []


@dataclass
class VerifyDeleteStatus:
    running: bool = False
    phase: str = "idle"              # idle | verifying | deleting | finished | error
    message: str = ""
    completed: int = 0
    total: int = 0
    matched: int = 0
    deleted: int = 0
    success: bool | None = None
    started_at: float | None = None
    finished_at: float | None = None
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

class RsyncManager:
    """
    Runs rsync in a background thread. Progress is derived by scanning:
      bytes_copied = Σ min(dst_size, src_size) over all source files
      files_done   = count(dst_size >= src_size)
    This is robust for 20s polling and avoids parsing rsync output.
    """
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._status = BackupStatus()
        self._thread: threading.Thread | None = None
        self._verify_thread: threading.Thread | None = None
        self._verify_status = VerifyDeleteStatus()
        self._proc: subprocess.Popen[str] | subprocess.Popen[bytes] | None = None

        # job config for snapshotting
        self._src: Path | None = None
        self._dst: Path | None = None
        self._files_from: Path | None = None
        self._verify: bool = False
        self._delete: bool = False
        self._tag_gps: bool = False
        self._remove_source: bool = False

        # cache totals
        self._totals_ready = False

        # tiny cache to avoid re-scanning too often (not strictly needed for 20s poll)
        self._snap_cache_ts = 0.0
        self._snap_cache: tuple[int, int] = (0, 0)  # (bytes_copied, files_done)
        self._non_arw_total_bytes = 0
        self._non_arw_total_files = 0
        self._arw_total_bytes = 0
        self._arw_total_files = 0
        self._arw_bytes_done = 0
        self._arw_files_done = 0
        self._exiftool = ExifToolARW(os.environ.get("SKYSEEKER_EXIFTOOL", "exiftool"))
        
        # These are used to benchmark the hashing performance during verification for 
        # deletion. Not to be used in production, as it slows the hashing process down.
        # self.fingerprint_counts = defaultdict(int)
        # self.fingerprint_repeats = 0
        # self.fingerprint_names = []
        # self.fingerprint_lock = threading.Lock()

    # ---------------- Public API ----------------

    def verify_delete_status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._verify_status)

    def start_verify_and_delete(self, src: str, dst: str) -> dict[str, Any]:
        """Start verification/deletion without holding an HTTP request open."""
        with self._lock:
            if self._status.running:
                return {"success": False, "msg": "Backup is running"}
            if self._verify_status.running:
                return {"success": False, "msg": "Verification is already running"}
            self._verify_status = VerifyDeleteStatus(
                running=True,
                phase="verifying",
                message="Preparing verification...",
                started_at=time.time(),
            )
            self._verify_thread = threading.Thread(
                target=self._run_verify_and_delete,
                args=(src, dst),
                daemon=True,
            )
            self._verify_thread.start()
        return {"success": True, "started": True}

    def _set_verify_progress(self, phase: str, completed: int, total: int) -> None:
        with self._lock:
            self._verify_status.phase = phase
            self._verify_status.completed = completed
            self._verify_status.total = total
            action = "Verifying" if phase == "verifying" else "Deleting"
            self._verify_status.message = f"{action} {completed}/{total} files..."

    def _run_verify_and_delete(self, src: str, dst: str) -> None:
        try:
            result = self.verify_and_delete_matched_sampled(
                src,
                dst,
                progress_callback=self._set_verify_progress,
            )
            delete_result = result.get("delete") or {}
            deleted = int(delete_result.get("deleted") or 0)
            matched = len(result.get("matched") or [])
            success = bool(result.get("success"))
            errors = list(result.get("errors") or []) + list(delete_result.get("errors") or [])
            with self._lock:
                self._verify_status.running = False
                self._verify_status.phase = "finished" if success else "error"
                self._verify_status.success = success
                self._verify_status.matched = matched
                self._verify_status.deleted = deleted
                self._verify_status.errors = errors[:50]
                self._verify_status.finished_at = time.time()
                if success and deleted:
                    self._verify_status.message = f"Verified and deleted {deleted} files."
                elif success:
                    self._verify_status.message = "Verification completed; no matched files needed deletion."
                else:
                    self._verify_status.message = "Verification failed; unmatched files were retained."
        except Exception as exc:
            self._logger.exception("Verify and delete failed")
            with self._lock:
                self._verify_status.running = False
                self._verify_status.phase = "error"
                self._verify_status.success = False
                self._verify_status.message = f"Verification failed: {exc}"
                self._verify_status.errors = [str(exc)]
                self._verify_status.finished_at = time.time()
        finally:
            tricap_manager.unmount_disk()

    def start(
        self,
        src: str,
        dst: str,
        files_from: str | None = None,
        verify: bool = False,
        delete: bool = False,
        tag_gps: bool = False,
        remove_source: bool = False,
    ) -> dict[str, Any]:
        src_p = Path(src)
        dst_p = Path(dst)

        if not src_p.exists() or not src_p.is_dir():
            return {"success": False}
        if remove_source and tag_gps:
            return {"success": False, "msg": "remove_source is not supported with GPS tagging"}
        dst_p.mkdir(parents=True, exist_ok=True)

        if tag_gps:
            try:
                self._exiftool.require_supported_version()
            except Exception as exc:
                return {"success": False, "msg": str(exc)}

        with self._lock:
            if self._status.running:
                return {"success": False}
            if self._verify_status.running:
                return {"success": False, "msg": "Verification is running"}
            self._src = src_p.resolve()
            self._dst = dst_p.resolve()
            self._files_from = Path(files_from).resolve() if files_from else None
            self._verify = bool(verify)
            self._delete = bool(delete)
            self._tag_gps = bool(tag_gps)
            self._remove_source = bool(remove_source)

            # compute totals once
            total_bytes, total_files = self._scan_totals(self._src, self._files_from)
            arw_bytes, arw_files = self._scan_arw_totals(self._src, self._files_from) if self._tag_gps else (0, 0)
            self._arw_total_bytes = arw_bytes
            self._arw_total_files = arw_files
            self._non_arw_total_bytes = max(0, total_bytes - arw_bytes)
            self._non_arw_total_files = max(0, total_files - arw_files)
            self._arw_bytes_done = 0
            self._arw_files_done = 0

            # --- free-space preflight ---
            try:
                free_bytes = self._disk_free_bytes(self._dst)

                # Estimate only the *remaining* bytes that would be sent.
                remaining_bytes, remaining_files = self._estimate_delta_bytes(
                    self._src,
                    self._dst,
                    self._files_from,
                    total_bytes,
                    total_files,
                )

                # One tagged ARW is generated beside any existing destination before
                # atomic replacement. The fixed margin comfortably covers that peak.
                need_with_margin = remaining_bytes + 256*1024*1024 # 256MB margin
                if free_bytes < need_with_margin and remaining_bytes > 0:
                    # Mark status and refuse to start
                    self._status.running = False
                    self._status.phase = "error"
                    self._status.message = "Insufficient space"
                    return {
                        "success": False,
                        "msg": "Insufficient space",
                    }
            except Exception as e:
                # If the preflight itself fails, be conservative and refuse to start
                self._status.running = False
                self._status.phase = "error"
                self._status.message = f"Space check failed: {e}"
                return {"success": False, "msg": f"space_check_failed: {e}"}
            # --- end free-space preflight ---

            self._status = BackupStatus(
                running=True,
                phase="indexing",
                message="Indexing backup...",
                started_at=time.time(),
                total_files=total_files,
                total_bytes=total_bytes,
                tag_gps=self._tag_gps,
                planned_bytes=remaining_bytes,
                planned_files=remaining_files,
            )
            self._totals_ready = True
            self._snap_cache_ts = 0.0

            self._thread = threading.Thread(target=self._run_rsync, daemon=True)
            self._thread.start()
            return {"success": True, "msg": "Complete backup" if self._files_from is None else "Partial backup"}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._status.running:
                return {"success": False}
            self._status.phase = "stopping"
            self._status.message = "Stopping..."
            proc = self._proc

        # Try graceful stop
        try:
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
            self._exiftool.cancel()
        except Exception:
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
                self._exiftool.cancel()
            except Exception:
                pass
        return {"success": True}

    def status(self) -> dict[str, Any]:
        with self._lock:
            st = asdict(self._status)
            src = self._src
            dst = self._dst
            files_from = self._files_from

        # If a job is configured, compute a fresh (or cached) snapshot
        if src and dst and self._totals_ready and st["running"]:
            now = time.time()
            if now - self._snap_cache_ts >= 1.5:  # throttle a little
                bytes_copied, files_done = self._snapshot_progress(src, dst, files_from)
                with self._lock:
                    self._status.bytes_copied = bytes_copied
                    self._status.files_done = files_done
                    self._snap_cache = (bytes_copied, files_done)
                    self._snap_cache_ts = now
                st["bytes_copied"] = bytes_copied
                st["files_done"] = files_done
            else:
                # use cached
                bc, fd = self._snap_cache
                st["bytes_copied"] = bc
                st["files_done"] = fd

        return st


    def verify_now(self, 
                   src: str,
                   dst: str,
                   mode: str = "checksum", 
                   sample_limit: int = 25,
                   excludes: list[str] = [],
        ) -> dict[str, Any]:
        """
        Run verification immediately (synchronous). Returns the verify result dict
        and updates the status fields.
        """
        checksum = (mode == "checksum")
        res = self._verify_pass(src, dst, excludes, checksum=checksum, sample_limit=sample_limit)

        with self._lock:
            self._status.verify_mode = mode
            self._status.verified = res["ok"]
            self._status.verify_missing = res["missing"]
            self._status.verify_changed = res["changed"]
            self._status.verify_extra = res["extra"]
            self._status.verify_samples = res["samples"]
            self._status.dst_files = res["dst_files"]
            self._status.dst_bytes = res["dst_bytes"]
            self._status.ready_to_delete = res["ok"]

        out = {"success": True}
        out.update(res)
        return out


    def _sample_fingerprint(
        self,
        path: Path,
        block_size: int = 1024 * 1024,
        blocks: int = 4,
    ) -> str:
        """
        Deterministic sampled fingerprint for fast, high-confidence equality checks.

        Reads at most (block_size * blocks) bytes:
        - first block
        - last block
        - (blocks-2) interior blocks at deterministic offsets derived from file size

        NOTE: This is not a full-file cryptographic proof of equality, but for large, immutable
        camera RAW files it is usually an excellent speed/safety tradeoff.
        """
        st = path.stat()
        size = st.st_size
        if size <= 0:
            return "0:empty"

        # blake2b is fast in Python stdlib; digest_size=16 is plenty for fingerprinting
        hash = hashlib.blake2b(digest_size=16)
        with path.open("rb") as file:
            # first block
            file.seek(0)
            hash.update(file.read(min(block_size, size)))

            if size > block_size:
                # last block
                last_off = max(0, size - block_size)
                file.seek(last_off)
                hash.update(file.read(block_size))

            # interior blocks
            if blocks > 2 and size > 2 * block_size:
                interior = blocks - 2
                span = size - 2 * block_size
                step = max(block_size, span // (interior + 1))
                for i in range(1, interior + 1):
                    off = block_size + i * step
                    if off >= size - block_size:
                        break
                    file.seek(off)
                    hash.update(file.read(block_size))
        return f"{size}:{hash.hexdigest()}"

    def list_matched_files_sampled(
        self,
        src_root: str,
        dst_root: str,
        block_size: int = 1024 * 1024,
        blocks: int = 2,
        require_mtime_equal: bool = True,
        mtime_tolerance_ns: int = EXFAT_MTIME_RESOLUTION_NS,
        exclude_names: list[str] | None = None,
        workers: int | None = 16,
        queue_limit: int = 2000,
        tagged_workers: int = 2,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """
        Produce an explicit list of files that match between SRC and DST without hashing whole files.

        We only examine files that exist on DST (candidates for deletion). For each candidate:
        1) size must match
        2) (optional) mtime must match within mtime_tolerance_ns
        3) sampled fingerprint must match (fast partial read)

        Returns:
            {
            "success": bool,
            "matched": [rel, ...],        # safe-to-delete candidates
            "different": [rel, ...],      # present but doesn't match
            "missing_on_src": [rel, ...], # present on dst but missing on src
            "checked": int,
            "errors": [str, ...],
            "workers": int,
            }
        """
        src_p = Path(src_root).resolve()
        dst_p = Path(dst_root).resolve()

        if not src_p.is_dir():
            return {"success": False, "errors": ["src_not_dir"]}
        if not dst_p.is_dir():
            return {"success": False, "errors": ["dst_not_dir"]}

        exclude_set = set(exclude_names or [])

        matched: list[str] = []
        different: list[str] = []
        missing: list[str] = []
        errors: list[str] = []
        checked = 0
        # A small bound overlaps ExifTool startup and SSD reads without spawning
        # enough full-file ARW scans to saturate the USB storage path.
        arw_verify_slots = threading.Semaphore(max(1, int(tagged_workers)))

        # IO-bound. More threads can help overlap src/dst reads, but don't overdo it.
        if workers is None:
            cpu = os.cpu_count() or 4
            workers = min(16, max(4, cpu * 2))

        def iter_dst_candidates():
            # Candidates are only files that exist on DST; we further filter by name.
            for root, _dirs, files in os.walk(dst_p):
                root_path = Path(root)
                for fn in files:
                    rel = (root_path / fn).relative_to(dst_p).as_posix()
                    if fn in exclude_set:
                        continue
                    yield rel

        def check_one(rel: str) -> tuple[str, str]:
            """
            Returns (status, payload):
              status in {"matched","different","missing","error"}
            """
            source_path = src_p / rel
            destination_path = dst_p / rel
            try:
                if not source_path.is_file():
                    return ("missing", rel)

                # GPS-tagged ARWs intentionally differ in size, metadata and whole-
                # file hash. Compare only their losslessly preserved image data and
                # require the embedded source hash plus GPS tags. The preserved
                # mtime binds that tagged output to the current immutable source
                # without hashing the source ARW again.
                if self._tag_gps and source_path.suffix.lower() == ".arw":
                    source_stat = source_path.stat()
                    destination_stat = destination_path.stat()
                    if abs(source_stat.st_mtime_ns - destination_stat.st_mtime_ns) > mtime_tolerance_ns:
                        return ("different", rel)
                    with arw_verify_slots:
                        if self._exiftool.validate_tagged(destination_path):
                            return ("matched", rel)
                    return ("different", rel)

                # Stat first (no reads)
                sst = source_path.stat()
                dstst = destination_path.stat()

                if sst.st_size != dstst.st_size:
                    return ("different", rel)

                # mtime is only a fast pre-filter; the sampled fingerprint below is the
                # real equality proof. Compare within a tolerance so a destination with
                # coarser timestamps (e.g. exFAT's 10 ms granularity) still matches the
                # full-nanosecond source mtime after an rsync copy.
                if require_mtime_equal and abs(sst.st_mtime_ns - dstst.st_mtime_ns) > mtime_tolerance_ns:
                    return ("different", rel)

                # Sampled fingerprints (limited reads)
                source_fingerprint = self._sample_fingerprint(source_path, block_size=block_size, blocks=blocks)
                destination_fingerprint = self._sample_fingerprint(destination_path, block_size=block_size, blocks=blocks)

                # hashstring = source_fingerprint.split(':')[1]
                # with self.fingerprint_lock:
                #     self.fingerprint_counts[hashstring] += 1
                #     if self.fingerprint_counts[hashstring] > 1:
                #         self.fingerprint_repeats += 1
                #         self.fingerprint_names.append(source_path)
                if source_fingerprint == destination_fingerprint:
                    return ("matched", rel)
                return ("different", rel)

            except Exception as e:
                return ("error", f"{rel}: {e}")

        candidates = list(iter_dst_candidates())
        total_candidates = len(candidates)
        completed = 0
        if progress_callback is not None:
            progress_callback("verifying", 0, total_candidates)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            in_flight: set[concurrent.futures.Future] = set()

            def drain() -> None:
                nonlocal checked, completed
                done, _ = concurrent.futures.wait(
                    in_flight,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for fut in done:
                    in_flight.remove(fut)
                    status, payload = fut.result()
                    if status == "matched":
                        matched.append(payload)
                        checked += 1
                    elif status == "different":
                        # different.append(payload)
                        checked += 1
                    # elif status == "missing":
                        # missing.append(payload)
                    elif status == "error":
                        errors.append(payload)
                    completed += 1
                    if progress_callback is not None:
                        progress_callback("verifying", completed, total_candidates)

            for rel in candidates:
                in_flight.add(ex.submit(check_one, rel))
                if len(in_flight) >= int(queue_limit):
                    drain()

            while in_flight:
                drain()

        return {
            "success": len(errors) == 0,
            "matched": matched,
            # "different": different,
            # "missing_on_src": missing,
            "checked": checked,
            "errors": errors[:50],
            "workers": int(workers),
        }

    def delete_matched_files(
        self,
        src_root: str,
        matched_rel_paths: list[str],
        exclude_names: list[str] | None = None,
        dry_run: bool = False,
        prune_empty_dirs: bool = True,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Delete the given relative paths from src_root (best-effort)."""
        exclude_names = exclude_names or []
        src_p = Path(src_root).resolve()
        deleted = 0
        missing = 0
        errors: list[str] = []

        total_paths = len(matched_rel_paths)
        if progress_callback is not None:
            progress_callback("deleting", 0, total_paths)
        for index, rel in enumerate(matched_rel_paths, start=1):
            parts = Path(rel).parts
            # Never delete continuously-updated files directly under /{date}/
            if len(parts) == 2 and parts[1] in exclude_names:
                if progress_callback is not None:
                    progress_callback("deleting", index, total_paths)
                continue
            if (
                len(parts) == 2
                and parts[0] == time.strftime("%Y_%m_%d")
                and parts[1] in LIVE_TELEMETRY_NAMES
            ):
                if progress_callback is not None:
                    progress_callback("deleting", index, total_paths)
                continue

            sp = src_p / rel
            try:
                if not sp.exists():
                    missing += 1
                    continue
                if dry_run:
                    deleted += 1
                    continue
                sp.unlink()
                deleted += 1
            except Exception as e:
                errors.append(f"{rel}: {e}")
            finally:
                if progress_callback is not None:
                    progress_callback("deleting", index, total_paths)

        if prune_empty_dirs and not dry_run:
            for dirpath, _, _ in os.walk(src_p, topdown=False):
                p = Path(dirpath)
                try:
                    if not any(p.iterdir()):
                        p.rmdir()
                except Exception:
                    pass

        return {
            "success": len(errors) == 0,
            "deleted": deleted,
            "missing": missing,
            "errors": errors[:50],
            "dry_run": dry_run,
        }


    def verify_and_delete_matched_sampled(
        self,
        src_root: str,
        dst_root: str,
        dry_run: bool = False,
        exclude_names: list[str] | None = None,
        block_size: int = 1024 * 1024,
        blocks: int = 2,
        require_mtime_equal: bool = True,
        mtime_tolerance_ns: int = EXFAT_MTIME_RESOLUTION_NS,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """
        Verify using sampled fingerprinting and then delete *only* the explicitly matched files from source.
        """
        res = self.list_matched_files_sampled(
            src_root=src_root,
            dst_root=dst_root,
            block_size=block_size,
            blocks=blocks,
            require_mtime_equal=require_mtime_equal,
            mtime_tolerance_ns=mtime_tolerance_ns,
            exclude_names=exclude_names,
            progress_callback=progress_callback,
        )
        if not res.get("success"):
            return res

        delres = self.delete_matched_files(
            src_root=src_root,
            matched_rel_paths=res.get("matched", []),
            exclude_names=exclude_names,
            dry_run=dry_run,
            progress_callback=progress_callback,
        )
        out = {"success": delres.get("success", False)}
        out.update(res)
        out.update({"delete": delres})
        return out
    
    def generate_partial_files_from(
        self,
        src_root: str,
        dst_root: str,
        margin_bytes: int = 256 * 1024 * 1024,
        out_file: str | None = None,
        max_transfer_bytes: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate a files-from list (newline-delimited relative paths) for a *partial backup*.

        This uses rsync's dry-run to determine which files would be transferred from SRC -> DST,
        then selects a prefix that fits in the available free space on DST (minus margin).

        Typical usage:
          1) Normal backup attempt (full rsync)
          2) If insufficient space -> call this helper to create a files-from list
          3) Re-run start(..., files_from=<generated_path>)

        Args:
            src_root: Source root (e.g. NVMe mount)
            dst_root: Destination root (e.g. external SSD mount)
            margin_bytes: Safety margin to leave free on destination
            out_file: Optional explicit output file path. If None, a temp file is created.
            max_transfer_bytes: Optional cap; if provided, will not plan more than this many bytes.

        Returns:
            {
              "success": bool,
              "files_from": str,          # path written
              "planned_files": int,
              "planned_bytes": int,
              "budget_bytes": int,
              "free_bytes": int,
              "remaining_bytes": int,     # estimated total delta if full backup
              "remaining_files": int,
            }
        """
        src_p = Path(src_root).resolve()
        dst_p = Path(dst_root).resolve()

        if not src_p.is_dir():
            return {"success": False, "msg": "src_not_dir"}
        if not dst_p.exists():
            dst_p.mkdir(parents=True, exist_ok=True)

        free_bytes = self._disk_free_bytes(dst_p)
        budget = max(0, free_bytes - int(margin_bytes))
        if max_transfer_bytes is not None:
            budget = min(budget, int(max_transfer_bytes))

        if budget <= 0:
            return {
                "success": False,
                "msg": "no_space_after_margin",
                "free_bytes": free_bytes,
                "budget_bytes": budget,
            }

        env = os.environ.copy()
        env["LC_ALL"] = "C"

        src_arg = str(src_p) + os.sep  # copy contents
        cmd: list[str] = [
            "rsync",
            "-aH",
            "--dry-run",
            "--itemize-changes",
            "--no-human-readable",
            "--out-format=%i|%l|%n",
        ]
        if self._verify:
            cmd.append("--checksum")

        cmd += [src_arg, str(dst_p)]

        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, env=env)
        except Exception as e:
            return {"success": False, "msg": f"rsync_dry_run_failed: {e}"}

        planned_rels: list[str] = []
        planned_bytes = 0
        remaining_bytes = 0
        remaining_files = 0

        for line in out.splitlines():
            try:
                item, length_str, rel = line.split("|", 2)
            except ValueError:
                continue

            if len(item) >= 2 and item[0] == ">" and item[1] == "f":
                remaining_files += 1
                try:
                    sz = int(length_str)
                except Exception:
                    sz = 0
                remaining_bytes += sz

                if planned_bytes + sz <= budget:
                    planned_rels.append(rel)
                    planned_bytes += sz
                else:
                    break

        if out_file is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_file = str(Path(tempfile.gettempdir()) / f"rsync_files_from_partial_{ts}.txt")

        out_path = Path(out_file).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("".join(r + "\n" for r in planned_rels), encoding="utf-8")

        return {
            "success": True,
            "files_from": str(out_path),
            "planned_files": len(planned_rels),
            "planned_bytes": planned_bytes,
            "budget_bytes": budget,
            "free_bytes": free_bytes,
            "remaining_bytes": remaining_bytes,
            "remaining_files": remaining_files,
        }


    # ---------------- Internals ----------------

    def _run_rsync(self) -> None:
        assert self._src is not None and self._dst is not None

        cmd: list[str] = [
            "rsync",
            "-aH",                # archive + preserve hardlinks
            "--partial",
            "--append-verify",    # safe resume
        ]
        if self._tag_gps:
            cmd += ["--exclude=*.ARW", "--exclude=*.arw"]
        if self._verify:
            cmd.append("--checksum")    # slower; content-verify
        if self._delete:
            cmd.append("--delete-after")
        if self._remove_source:
            # rsync checksum-verifies every transferred file before the sender
            # removes it, so the copy and delete happen in a single pass.
            cmd.append("--remove-source-files")
            # Continuously-updated telemetry under today's capture directory must
            # never be removed from source; it is copied separately afterwards.
            today = time.strftime("%Y_%m_%d")
            for name in sorted(LIVE_TELEMETRY_NAMES):
                cmd.append(f"--exclude=/{today}/{name}")

        # If files-from is provided, copy only those relative paths.
        # The files list is expected to be newline-delimited (relative to src).
        cwd = None
        src_arg: str
        if self._files_from is not None:
            cmd += [f"--files-from={self._files_from}"]
            src_arg = "./"
            cwd = str(self._src)
        else:
            src_arg = str(self._src) + os.sep  # copy *contents*

        cmd += [src_arg, str(self._dst)]

        try:
            copy_started = time.monotonic()
            with self._lock:
                self._status.phase = "copying"
                if self._tag_gps:
                    self._status.message = "Copying non-ARW files..."
                elif self._remove_source:
                    self._status.message = "Moving files..."
                else:
                    self._status.message = "Copying files..."
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False,
                cwd=cwd,
            )
            rc = self._proc.wait()
            with self._lock:
                self._status.copy_seconds = max(0.0, time.monotonic() - copy_started)
            if rc == 0 and self._tag_gps:
                tag_started = time.monotonic()
                self._run_arw_backup()
                with self._lock:
                    self._status.tag_seconds = max(0.0, time.monotonic() - tag_started)
                    if self._status.phase == "stopping":
                        rc = 130
                    elif self._status.gps_failed:
                        self._status.message = f"Completed with {self._status.gps_failed} ARW errors."
                    elif self._status.gps_unresolved:
                        self._status.message = f"Completed with {self._status.gps_unresolved} unresolved GPS images."
            cleanup_deleted = 0
            cleanup_failed = False
            if rc == 0 and self._remove_source:
                with self._lock:
                    stopping = self._status.phase == "stopping"
                if not stopping:
                    self._copy_live_telemetry()
                    with self._lock:
                        self._status.phase = "cleaning"
                        self._status.message = "Removing verified source files..."
                    # --remove-source-files only removes files transferred in this
                    # run; sources that already matched the destination are cleaned
                    # up here with the same verification as "Verify & delete".
                    cleanup = self.verify_and_delete_matched_sampled(
                        str(self._src),
                        str(self._dst),
                        progress_callback=self._set_move_progress,
                    )
                    cleanup_deleted = int((cleanup.get("delete") or {}).get("deleted") or 0)
                    cleanup_failed = not cleanup.get("success")
            while True:
                if not tricap_manager.unmount_disk():
                    time.sleep(2.0)
                else:
                    break
            with self._lock:
                self._status.running = False
                self._status.finished_at = time.time()
                if self._status.phase == "stopping":
                    # treat as user-stopped regardless of rc
                    self._status.phase = "finished"
                    self._status.message = "Stopped by user."
                elif rc == 0:
                    self._status.phase = "finished"
                    if self._remove_source and cleanup_failed:
                        self._status.phase = "error"
                        self._status.message = "Copy completed but some source files could not be verified; they were retained."
                    elif self._remove_source:
                        self._status.message = f"Completed. Deleted {cleanup_deleted} source files."
                    elif not self._status.message.startswith("Completed with"):
                        self._status.message = "Completed."
                else:
                    self._status.phase = "error"
                    self._status.message = f"exited with code {rc}"
        except Exception as e:
            with self._lock:
                self._status.running = False
                self._status.finished_at = time.time()
                self._status.phase = "error"
                self._status.message = f"Error: {e}"
        finally:
            self._proc = None
            self._finalize_benchmark()

    def _copy_live_telemetry(self) -> None:
        """Copy today's continuously-updated telemetry files.

        The move pass excludes these so rsync never removes them from source;
        they are copied here (without source removal) so the backup stays complete.
        """
        assert self._src is not None and self._dst is not None
        today = time.strftime("%Y_%m_%d")
        for name in LIVE_TELEMETRY_NAMES:
            source = self._src / today / name
            if not source.is_file():
                continue
            destination = self._dst / today / name
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            except OSError as exc:
                self._logger.warning("Could not copy telemetry file %s: %s", source, exc)

    def _set_move_progress(self, phase: str, completed: int, total: int) -> None:
        with self._lock:
            action = "Verifying" if phase == "verifying" else "Deleting"
            self._status.message = f"{action} {completed}/{total} source files..."

    def _run_arw_backup(self) -> None:
        assert self._src is not None and self._dst is not None
        gps_index = GPSIndex(self._src)
        with self._lock:
            if self._status.phase == "stopping":
                return
            self._status.phase = "tagging"
            self._status.message = "Writing GPS-tagged ARWs..."

        for rel, source in self._iter_selected_files(self._src, self._files_from):
            if source.suffix.lower() != ".arw":
                continue
            with self._lock:
                if self._status.phase == "stopping":
                    return
                self._status.current_file = rel.as_posix()

            destination = self._dst / rel
            partial = destination.parent / ".skyseeker-in-progress" / destination.name
            try:
                # A validated output is already complete and can be resumed without
                # another full-file write.
                if destination.is_file():
                    source_mtime = source.stat().st_mtime_ns
                    destination_mtime = destination.stat().st_mtime_ns
                    if (
                        abs(source_mtime - destination_mtime) <= EXFAT_MTIME_RESOLUTION_NS
                        and self._exiftool.validate_tagged(destination)
                    ):
                        self._mark_arw_done(source, "existing")
                        continue

                source_tags = self._exiftool.read_tags(source)
                native_gps = required_gps_present(source_tags)
                match = None if native_gps else gps_index.match_image(source, source_tags)

                if match is None and not native_gps:
                    self._exiftool.copy_untagged(source, partial)
                    fsync_file_and_parent(partial)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(partial, destination)
                    self._preserve_mtime(source, destination)
                    with self._lock:
                        self._status.gps_unresolved += 1
                    self._mark_arw_done(source, "unresolved")
                    continue

                self._exiftool.write_copy(source, partial, match)
                fsync_file_and_parent(partial)
                if not self._exiftool.validate_tagged(partial):
                    raise RuntimeError("tagged ARW failed image-data or GPS verification")
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(partial, destination)
                self._preserve_mtime(source, destination)
                fsync_file_and_parent(destination)
                with self._lock:
                    self._status.gps_tagged += 1
                    if match is not None and match.method == "interpolated":
                        self._status.gps_interpolated += 1
                    elif match is not None and match.method == "nearest":
                        self._status.gps_nearest += 1
                self._mark_arw_done(source, match.method if match is not None else "native")
            except Exception as exc:
                self._logger.warning("ARW GPS backup failed %s: %s", rel, exc)
                with self._lock:
                    self._status.gps_failed += 1
            finally:
                # Normal failures are cleaned immediately. A hard power loss may leave
                # this file, and the next run safely replaces it before retrying.
                try:
                    if partial.exists():
                        partial.unlink()
                except OSError:
                    pass

        with self._lock:
            self._status.current_file = ""

    def _mark_arw_done(self, source: Path, _method: str) -> None:
        try:
            size = source.stat().st_size
        except OSError:
            size = 0
        with self._lock:
            self._arw_bytes_done += size
            self._arw_files_done += 1

    def _preserve_mtime(self, source: Path, destination: Path) -> None:
        try:
            source_stat = source.stat()
            os.utime(destination, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
        except OSError as exc:
            # exFAT timestamp support varies by kernel/driver. Metadata and image
            # verification are authoritative; timestamp preservation is best-effort.
            self._logger.warning("Could not preserve backup mtime for %s: %s", destination, exc)

    def _finalize_benchmark(self) -> None:
        """Finalize status metrics and append one durable row per backup run."""
        with self._lock:
            if self._status.started_at is None:
                return
            if self._status.finished_at is None:
                self._status.finished_at = time.time()
            self._status.elapsed_seconds = max(
                0.0, self._status.finished_at - self._status.started_at
            )
            if self._status.phase == "finished" and self._status.message == "Completed.":
                self._status.bytes_copied = self._status.total_bytes
                self._status.files_done = self._status.total_files
            if self._status.elapsed_seconds > 0 and self._status.planned_bytes > 0:
                self._status.throughput_mib_s = (
                    self._status.planned_bytes / 1024 / 1024 / self._status.elapsed_seconds
                )
            status = asdict(self._status)

        columns = [
            "started_at", "finished_at", "mode", "result", "elapsed_seconds",
            "copy_seconds", "tag_seconds", "planned_bytes", "planned_files",
            "total_bytes", "total_files", "throughput_mib_s", "gps_tagged",
            "gps_interpolated", "gps_nearest", "gps_unresolved", "gps_failed",
        ]
        row = {
            "started_at": datetime.fromtimestamp(status["started_at"]).astimezone().isoformat(),
            "finished_at": datetime.fromtimestamp(status["finished_at"]).astimezone().isoformat(),
            "mode": "gps_tagged" if status["tag_gps"] else "plain_copy",
            "result": status["message"],
            "elapsed_seconds": f'{status["elapsed_seconds"]:.3f}',
            "copy_seconds": f'{status["copy_seconds"]:.3f}',
            "tag_seconds": f'{status["tag_seconds"]:.3f}',
            "planned_bytes": status["planned_bytes"],
            "planned_files": status["planned_files"],
            "total_bytes": status["total_bytes"],
            "total_files": status["total_files"],
            "throughput_mib_s": f'{status["throughput_mib_s"]:.3f}',
            "gps_tagged": status["gps_tagged"],
            "gps_interpolated": status["gps_interpolated"],
            "gps_nearest": status["gps_nearest"],
            "gps_unresolved": status["gps_unresolved"],
            "gps_failed": status["gps_failed"],
        }
        try:
            BACKUP_BENCHMARK_LOG.parent.mkdir(parents=True, exist_ok=True)
            write_header = not BACKUP_BENCHMARK_LOG.exists()
            with BACKUP_BENCHMARK_LOG.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                if write_header:
                    writer.writeheader()
                writer.writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as exc:
            self._logger.warning("Could not write backup benchmark log: %s", exc)


    # ---------- helpers ----------

    def _disk_free_bytes(self, path: Path) -> int:
        try:
            return shutil.disk_usage(path).free
        except Exception:
            return 0

    def _scan_totals(self, src: Path, files_from: Path | None) -> tuple[int, int]:
        """Compute totals for whole tree or only for files listed in files_from."""
        total_bytes = 0
        total_files = 0

        if files_from is None:
            for root, _dirs, files in os.walk(src):
                root_p = Path(root)
                for f in files:
                    fp = root_p / f
                    try:
                        total_bytes += fp.stat().st_size
                        total_files += 1
                    except Exception:
                        pass
            return total_bytes, total_files

        # files-from mode: paths are relative to src
        try:
            rels = [ln.strip() for ln in files_from.read_text().splitlines() if ln.strip()]
        except Exception:
            rels = []

        for rel in rels:
            fp = src / rel
            try:
                if fp.is_file():
                    total_bytes += fp.stat().st_size
                    total_files += 1
            except Exception:
                pass

        return total_bytes, total_files

    def _iter_selected_files(self, src: Path, files_from: Path | None):
        """Yield selected regular files as (relative path, absolute path)."""
        if files_from is None:
            for root, _dirs, files in os.walk(src):
                root_path = Path(root)
                for name in files:
                    path = root_path / name
                    if path.is_file():
                        yield path.relative_to(src), path
            return
        try:
            rels = [line.strip() for line in files_from.read_text().splitlines() if line.strip()]
        except Exception:
            rels = []
        for rel_text in rels:
            rel = Path(rel_text)
            path = src / rel
            if path.is_file():
                yield rel, path

    def _scan_arw_totals(self, src: Path, files_from: Path | None) -> tuple[int, int]:
        total_bytes = 0
        total_files = 0
        for _rel, path in self._iter_selected_files(src, files_from):
            if path.suffix.lower() != ".arw":
                continue
            try:
                total_bytes += path.stat().st_size
                total_files += 1
            except OSError:
                pass
        return total_bytes, total_files

    def _estimate_delta_bytes(
        self,
        src: Path,
        dst: Path,
        files_from: Path | None,
        total_bytes: int,
        total_files: int,
    ) -> tuple[int, int]:
        """Estimate remaining bytes/files that would be transferred if we ran rsync now.

        Uses the same rsync --dry-run itemization as _snapshot_progress, but returns
        the *remaining* work instead of derived progress. Falls back to treating the
        whole dataset as remaining if rsync fails for any reason.
        """
        dst_arg = str(dst)

        cwd = None
        if files_from is not None:
            cmd_src = "./"
            cwd = str(src)
        else:
            cmd_src = str(src) + os.sep  # copy *contents*

        cmd: list[str] = [
            "rsync",
            "-aH",
            "--dry-run",
            "--itemize-changes",
            "--no-human-readable",
            "--out-format=%i|%l|%n",
        ]
        if self._tag_gps:
            cmd += ["--exclude=*.ARW", "--exclude=*.arw"]

        # Optional: if verify==True, we honor that here too (checksum-based diff)
        if self._verify:
            cmd.append("--checksum")

        if files_from is not None:
            cmd += [f"--files-from={files_from}"]

        cmd += [cmd_src, dst_arg]

        env = os.environ.copy()
        env["LC_ALL"] = "C"

        try:
            out = subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=cwd,
            )
            remaining_bytes = 0
            remaining_files = 0

            for line in out.splitlines():
                # Expect: "<itemize>|<length>|<path>"
                # Example itemize for a file to be sent: ">f.st......"
                try:
                    item, length_str, _path = line.split("|", 2)
                except ValueError:
                    continue

                if len(item) >= 2 and item[0] == ">" and item[1] == "f":
                    # This file would be transferred
                    remaining_files += 1
                    try:
                        remaining_bytes += int(length_str)
                    except Exception:
                        pass

            if self._tag_gps:
                # Tagged outputs need space only when no destination exists. Existing
                # legacy ARWs are rebuilt one at a time inside the fixed safety margin.
                for rel, source_path in self._iter_selected_files(src, files_from):
                    if source_path.suffix.lower() != ".arw":
                        continue
                    if not (dst / rel).is_file():
                        try:
                            remaining_bytes += source_path.stat().st_size
                            remaining_files += 1
                        except OSError:
                            pass
            remaining_bytes = max(0, min(total_bytes, remaining_bytes))
            remaining_files = max(0, min(total_files, remaining_files))
            return remaining_bytes, remaining_files

        except Exception:
            # If rsync inspection fails, fall back to worst-case: everything remaining.
            return total_bytes, total_files

    def _snapshot_progress(self, src: Path, dst: Path, files_from: Path | None) -> tuple[int, int]:
        """
        Progress snapshot using rsync's own difference engine:

        - Run: rsync --dry-run -aH --itemize-changes --out-format '%i|%l|%n' SRC/ DST/
        - Sum %l (size) for lines where %i indicates a file that WOULD be sent (>'f...)
        - Remaining bytes/files = those sums
        - bytes_copied = total_bytes - remaining_bytes
        - files_done   = total_files - remaining_files

        Falls back to filesystem-based snapshot if rsync errors out.
        """
        # Read totals computed at start()
        with self._lock:
            total_bytes = int(self._status.total_bytes or 0)
            total_files = int(self._status.total_files or 0)

        dst_arg = str(dst)

        cwd = None
        if files_from is not None:
            src_arg = "./"
            cwd = str(src)
        else:
            src_arg = str(src) + os.sep  # copy *contents*

        cmd: list[str] = [
            "rsync",
            "-aH",
            "--dry-run",
            "--itemize-changes",
            "--no-human-readable",          # numeric sizes in stats
            "--out-format=%i|%l|%n",        # itemize code | length | path
        ]
        if self._tag_gps:
            cmd += ["--exclude=*.ARW", "--exclude=*.arw"]
        # Be careful enabling --checksum here: it would re-hash everything every poll.
        # Use the manager's verify flag only if you *really* want content-compare.
        if self._verify:
            cmd.append("--checksum")
        if files_from is not None:
            cmd += [f"--files-from={files_from}"]
        cmd += [src_arg, dst_arg]

        env = os.environ.copy()
        env["LC_ALL"] = "C"  # stable parse

        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, env=env, cwd=cwd)
            remaining_bytes = 0
            remaining_files = 0

            for line in out.splitlines():
                # Expect: "<itemize>|<length>|<path>"
                # Example itemize for a file to be sent: ">f.st......"
                try:
                    item, length_str, _path = line.split("|", 2)
                except ValueError:
                    continue

                if len(item) >= 2 and item[0] == ">" and item[1] == "f":
                    # This file would be transferred
                    remaining_files += 1
                    try:
                        remaining_bytes += int(length_str)
                    except Exception:
                        pass

            with self._lock:
                arw_bytes_done = self._arw_bytes_done if self._tag_gps else 0
                arw_files_done = self._arw_files_done if self._tag_gps else 0
            base_total_bytes = self._non_arw_total_bytes if self._tag_gps else total_bytes
            base_total_files = self._non_arw_total_files if self._tag_gps else total_files
            non_arw_done = max(0, base_total_bytes - remaining_bytes)
            non_arw_files_done = max(0, base_total_files - remaining_files)
            bytes_copied = max(0, min(total_bytes, non_arw_done + arw_bytes_done))
            files_done = max(0, min(total_files, non_arw_files_done + arw_files_done))
            return bytes_copied, files_done

        except Exception:
            # Fallback: filesystem snapshot (min(dst_size, src_size))
            bytes_present = 0
            files_done = 0

            if files_from is None:
                for root, _dirs, files in os.walk(src):
                    root_p = Path(root)
                    for f in files:
                        sp = root_p / f
                        if self._tag_gps and sp.suffix.lower() == ".arw":
                            continue
                        try:
                            rel = sp.relative_to(src)
                            ssz = sp.stat().st_size
                        except Exception:
                            continue
                        dp = dst / rel
                        try:
                            dsz = dp.stat().st_size
                        except FileNotFoundError:
                            dsz = 0
                        bytes_present += min(ssz, dsz)
                        if dsz >= ssz:
                            files_done += 1
                with self._lock:
                    return bytes_present + self._arw_bytes_done, files_done + self._arw_files_done

            try:
                rels = [ln.strip() for ln in files_from.read_text().splitlines() if ln.strip()]
            except Exception:
                rels = []
            for rel_s in rels:
                sp = src / rel_s
                try:
                    if not sp.is_file():
                        continue
                    if self._tag_gps and sp.suffix.lower() == ".arw":
                        continue
                    ssz = sp.stat().st_size
                except Exception:
                    continue
                dp = dst / rel_s
                try:
                    dsz = dp.stat().st_size
                except FileNotFoundError:
                    dsz = 0
                bytes_present += min(ssz, dsz)
                if dsz >= ssz:
                    files_done += 1
            with self._lock:
                return bytes_present + self._arw_bytes_done, files_done + self._arw_files_done

    def _verify_pass(
        self,
        src: Path,
        dst: Path,
        excludes: list[str],
        checksum: bool,
        sample_limit: int = 25,
    ) -> dict[str, Any]:
        """
        Compare trees and report differences.

        - src->dst dry-run (with --checksum for content if requested):
            counts files that WOULD be transferred:
              * '>f+++++++++'  -> missing on dst
              * other '>f...'  -> changed on dst
        - dst->src dry-run with --delete -v:
            counts lines beginning with 'deleting ' -> extra on dst
        Also scans dest totals for convenience.
        """
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        effective_excludes = list(excludes)
        if self._tag_gps:
            effective_excludes += ["*.ARW", "*.arw"]

        src_arg = str(src) + os.sep
        dst_arg = str(dst)

        # 1) src -> dst: missing/changed
        cmd1 = ["rsync", "-rltH", "--size-only", "--dry-run", "--itemize-changes", "--out-format=%i|%n",
                 "--no-perms", "--no-owner", "--no-group"]
        if checksum:
            cmd1.append("--checksum")
        for pat in effective_excludes:
            cmd1 += ["--exclude", pat]
        cmd1 += [src_arg, dst_arg]

        changed = 0
        missing = 0
        samples: list[str] = []
        try:
            out1 = subprocess.check_output(cmd1, text=True, stderr=subprocess.STDOUT, env=env)
            for line in out1.splitlines():
                # Expect: "<itemize>|<path>"
                try:
                    item, path = line.split("|", 1)
                except ValueError:
                    continue
                if len(item) >= 2 and item[0] == ">" and item[1] in ("f", "L", "D"):
                    # New vs changed: new files usually show as >f+++++++++
                    is_missing = ("+++++++++" in item)
                    if is_missing:
                        missing += 1
                    else:
                        changed += 1
                    if len(samples) < sample_limit:
                        samples.append(f"{'MISSING' if is_missing else 'CHANGED'}: {path}")
        except subprocess.CalledProcessError as e:
            # Treat as verification failure
            return {
                "ok": False,
                "missing": -1,
                "changed": -1,
                "extra": -1,
                "samples": [f"VERIFY ERROR (src->dst): {e}"],
                "dst_files": 0,
                "dst_bytes": 0,
            }

        if self._tag_gps:
            # ARWs are metadata-transformed, so rsync cannot verify them. Validate
            # their source and destination image-data hashes plus embedded GPS tags.
            for rel, source_path in self._iter_selected_files(src, None):
                if source_path.suffix.lower() != ".arw":
                    continue
                destination_path = dst / rel
                if not destination_path.is_file():
                    missing += 1
                    if len(samples) < sample_limit:
                        samples.append(f"MISSING: {rel.as_posix()}")
                    continue
                try:
                    valid = self._exiftool.validate_tagged(source_path, destination_path)
                except Exception:
                    valid = False
                if not valid:
                    changed += 1
                    if len(samples) < sample_limit:
                        samples.append(f"CHANGED: {rel.as_posix()}")

        # 2) dst -> src: extra files (things that would be deleted)
        cmd2 = ["rsync", "-aH", "--dry-run", "--delete", "-v"]
        for pat in effective_excludes:
            cmd2 += ["--exclude", pat]
        cmd2 += [str(dst) + os.sep, str(src)]

        extra = 0
        try:
            out2 = subprocess.check_output(cmd2, text=True, stderr=subprocess.STDOUT, env=env)
            for line in out2.splitlines():
                if line.startswith("deleting "):
                    extra += 1
                    if len(samples) < sample_limit:
                        samples.append(f"EXTRA: {line[len('deleting '):]}")
        except subprocess.CalledProcessError as e:
            return {
                "ok": False,
                "missing": -1,
                "changed": -1,
                "extra": -1,
                "samples": [f"VERIFY ERROR (dst->src): {e}"],
                "dst_files": 0,
                "dst_bytes": 0,
            }

        if self._tag_gps:
            for rel, destination_path in self._iter_selected_files(dst, None):
                if destination_path.suffix.lower() == ".arw" and not (src / rel).is_file():
                    extra += 1
                    if len(samples) < sample_limit:
                        samples.append(f"EXTRA: {rel.as_posix()}")

        # 3) quick dst totals
        dst_bytes, dst_files = self._scan_totals(dst, None)

        ok = (missing == 0 and changed == 0 and extra == 0)
        return {
            "ok": ok,
            "missing": missing,
            "changed": changed,
            "extra": extra,
            "samples": samples,
            "dst_files": dst_files,
            "dst_bytes": dst_bytes,
        }

# Singleton for easy import in api.py
manager = RsyncManager()
__all__ = ["BackupStatus", "RsyncManager", "manager"]
