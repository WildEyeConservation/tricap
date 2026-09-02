# backup.py
# Minimal rsync-backed backup engine. Progress is read from rsync's own output.
from __future__ import annotations

import os
import signal
import subprocess
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

from support.rsync_progress import RSYNC_PROGRESS_ARGS, iter_lines, parse_line

# Finest timestamp resolution exFAT can store: a 10 ms "centisecond" field on top of
# the 2 s DOS base, i.e. 10 ms. The source NVMe is ext4 (full-nanosecond mtimes), so
# after an rsync copy the destination mtime is the source mtime quantized to the
# nearest 10 ms. An exact-nanosecond comparison can therefore never match on exFAT.
# We compare within this tolerance instead; the sampled content fingerprint
# (size + blake2b of sampled blocks) remains the real proof of file equality.
EXFAT_MTIME_RESOLUTION_NS = 10_000_000  # 10 ms

# Wall-clock ceilings for rsync inspection passes. These are wedge detectors,
# not performance controls: a healthy scan takes seconds, so they sit far above
# any legitimate duration. Without them a hung drive blocks the calling thread
# forever.
RSYNC_SCAN_TIMEOUT_SEC = 300      # dry-run inspection passes
RSYNC_VERIFY_TIMEOUT_SEC = 1800   # verify passes may checksum the whole tree
UNMOUNT_ATTEMPTS = 5
UNMOUNT_RETRY_SEC = 2.0

LIVE_TELEMETRY_NAMES = {"gpsData.csv", "altitudeData.csv", "flightData.csv"}
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

    # Progress (updated live from rsync output)
    files_done: int = 0
    bytes_copied: int = 0
    current_file: str = ""

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

    planned_bytes: int = 0
    planned_files: int = 0
    elapsed_seconds: float = 0.0
    copy_seconds: float = 0.0
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
    Runs rsync in a background thread and reads progress from its output, so
    status() is a plain read and costs the drives nothing.
    """
    def __init__(
        self,
        unmount: Callable[[], bool] | None = None,
        refresh_usage: Callable[[], Any] | None = None,
        claim_storage: Callable[[str], Any] | None = None,
        release_storage: Callable[[str], Any] | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._status = BackupStatus()
        self._thread: threading.Thread | None = None
        self._verify_thread: threading.Thread | None = None
        self._verify_status = VerifyDeleteStatus()
        self._proc: subprocess.Popen[str] | subprocess.Popen[bytes] | None = None
        self._unmount = unmount
        self._refresh_usage = refresh_usage
        self._claim_storage = claim_storage or (lambda _job: True)
        self._release_storage = release_storage or (lambda _job: None)

        # job config
        self._src: Path | None = None
        self._dst: Path | None = None
        self._files_from: Path | None = None
        self._verify: bool = False
        self._delete: bool = False
        self._remove_source: bool = False
        self._partial: bool = False   # set when free space forced a files-from subset

        # Progress parts: files already on the destination at start, then
        # bytes/files reported by the live rsync.
        self._base_bytes = 0
        self._base_files = 0
        self._rsync_bytes = 0
        self._rsync_files = 0

    # ---------------- Public API ----------------

    def verify_delete_status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._verify_status)

    def start_verify_and_delete(self, src: str, dst: str) -> dict[str, Any]:
        """Start verification/deletion without holding an HTTP request open."""
        if not os.path.ismount(dst):
            return {
                "success": False,
                "code": "destination_not_mounted",
                "msg": "Destination is not mounted",
            }
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
        self._claim_storage("verify")
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
            if not os.path.ismount(dst):
                raise RuntimeError("Destination is not mounted")
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
                self._verify_status.phase = "error"
                self._verify_status.success = False
                self._verify_status.message = f"Verification failed: {exc}"
                self._verify_status.errors = [str(exc)]
                self._verify_status.finished_at = time.time()
        finally:
            self._release_storage_claim("verify")
            unmounted = self._unmount_storage_with_retries()
            with self._lock:
                self._verify_status.running = False
                self._verify_status.finished_at = time.time()
                if not unmounted:
                    self._verify_status.phase = "error"
                    self._verify_status.success = False
                    self._verify_status.message = (
                        "Verification completed, but the SSD could not be unmounted; "
                        "remove it only after a restart."
                    )

    def start(
        self,
        src: str,
        dst: str,
        files_from: str | None = None,
        verify: bool = False,
        delete: bool = False,
        remove_source: bool = False,
    ) -> dict[str, Any]:
        src_p = Path(src)
        dst_p = Path(dst)

        if not src_p.exists() or not src_p.is_dir():
            return {"success": False}
        if not os.path.ismount(dst):
            return {
                "success": False,
                "code": "destination_not_mounted",
                "msg": "Destination is not mounted",
            }

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
            self._remove_source = bool(remove_source)
            self._status = BackupStatus(
                running=True,
                phase="indexing",
                message="Indexing backup...",
                started_at=time.time(),
            )
            self._base_bytes = self._base_files = 0
            self._rsync_bytes = self._rsync_files = 0

            self._thread = threading.Thread(target=self._run_rsync, daemon=True)
        self._claim_storage("backup")
        self._thread.start()
        return {"success": True, "msg": "Backup started"}

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
        except Exception:
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        return {"success": True}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def _set_progress(self) -> None:
        """Recompute bytes_copied/files_done from the parts. Caller holds the lock."""
        st = self._status
        st.bytes_copied = min(st.total_bytes, self._base_bytes + self._rsync_bytes)
        st.files_done = min(st.total_files, self._base_files + self._rsync_files)


    def verify_now(
        self,
        src: str,
        dst: str,
        mode: str = "checksum",
        sample_limit: int = 25,
        excludes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Run verification immediately (synchronous). Returns the verify result dict
        and updates the status fields.
        """
        checksum = (mode == "checksum")
        res = self._verify_pass(
            Path(src),
            Path(dst),
            excludes or [],
            checksum=checksum,
            sample_limit=sample_limit,
        )

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
        errors: list[str] = []
        checked = 0

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
                        checked += 1
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
                # The mount root and ext4's lost+found are not flight data.
                if p == src_p or p.name == "lost+found":
                    continue
                try:
                    if not any(p.iterdir()):
                        p.rmdir()
                except OSError:
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
        if not os.path.ismount(dst_root):
            return {
                "success": False,
                "code": "destination_not_mounted",
                "msg": "Destination is not mounted",
            }

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
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, env=env,
                                          timeout=RSYNC_SCAN_TIMEOUT_SEC)
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
        try:
            if not self._prepare_backup():
                return
            self._run_rsync_job()
        except Exception as exc:
            with self._lock:
                self._status.phase = "error"
                self._status.message = f"Error: {exc}"
        finally:
            self._refresh_storage_usage()
            self._release_storage_claim("backup")
            unmounted = self._unmount_storage_with_retries()
            with self._lock:
                if not unmounted:
                    self._status.phase = "error"
                    self._status.message = (
                        "The SSD could not be unmounted; remove it only after a restart."
                    )
                self._status.running = False
                self._status.finished_at = time.time()
            self._proc = None
            self._finalize_benchmark()

    def _prepare_backup(self) -> bool:
        assert self._src is not None and self._dst is not None
        total_bytes, total_files = self._scan_totals(self._src, self._files_from)
        free_bytes = self._disk_free_bytes(self._dst)
        remaining_bytes, remaining_files = self._estimate_delta_bytes(
            self._src,
            self._dst,
            self._files_from,
            total_bytes,
            total_files,
        )
        partial = False
        if remaining_bytes > 0 and free_bytes < remaining_bytes + 256 * 1024 * 1024:
            plan = self.generate_partial_files_from(
                str(self._src),
                str(self._dst),
                margin_bytes=256 * 1024 * 1024,
            )
            if not plan.get("success") or not plan.get("planned_files"):
                with self._lock:
                    self._status.phase = "error"
                    self._status.message = "Insufficient space"
                    self._status.total_bytes = total_bytes
                    self._status.total_files = total_files
                    self._status.planned_bytes = int(plan.get("planned_bytes") or 0)
                    self._status.planned_files = int(plan.get("planned_files") or 0)
                return False
            self._files_from = Path(plan["files_from"]).resolve()
            total_bytes, total_files = self._scan_totals(self._src, self._files_from)
            remaining_bytes = int(plan["planned_bytes"])
            remaining_files = int(plan["planned_files"])
            partial = True

        with self._lock:
            self._status.total_bytes = total_bytes
            self._status.total_files = total_files
            self._status.planned_bytes = remaining_bytes
            self._status.planned_files = remaining_files
            self._status.message = "Backup indexed"
            self._partial = partial
            self._base_bytes = max(0, total_bytes - remaining_bytes)
            self._base_files = max(0, total_files - remaining_files)
            self._set_progress()
        return True

    def _run_rsync_job(self) -> None:
        assert self._src is not None and self._dst is not None

        cmd: list[str] = [
            "rsync",
            "-aH",                # archive + preserve hardlinks
            "--partial",
            "--append-verify",    # safe resume
        ]
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

        cmd += RSYNC_PROGRESS_ARGS + [src_arg, str(self._dst)]

        try:
            copy_started = time.monotonic()
            with self._lock:
                self._status.phase = "copying"
                action = "Moving" if self._remove_source else "Copying"
                scope = "files that fit" if self._partial else "files"
                self._status.message = f"{action} {scope}..."
            if not os.path.ismount(self._dst):
                raise RuntimeError("Destination is not mounted")
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd,
                                          env={**os.environ, "LC_ALL": "C"})
            rsync_error = ""
            for line in iter_lines(self._proc.stdout):
                parsed = parse_line(line)
                if not parsed:
                    continue
                kind, value = parsed
                with self._lock:
                    if kind == "bytes":
                        self._rsync_bytes = value
                    elif kind == "file":
                        self._rsync_files += 1
                        self._status.current_file = value
                    elif not rsync_error:
                        rsync_error = value
                    self._set_progress()
            rc = self._proc.wait()
            with self._lock:
                self._status.copy_seconds = max(0.0, time.monotonic() - copy_started)
            cleanup_deleted = 0
            cleanup_failed = False
            if rc == 0 and self._remove_source:
                with self._lock:
                    stopping = self._status.phase == "stopping"
                if not stopping:
                    if not os.path.ismount(self._dst):
                        raise RuntimeError("Destination is not mounted")
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
                    cleanup_failed = not cleanup.get("success")
                    # rsync deletes transferred files in-flight, so the reported
                    # count is measured from what remains on source rather than
                    # from the cleanup pass alone.
                    with self._lock:
                        selected_files = self._status.total_files
                    _, remaining_files = self._scan_totals(self._src, self._files_from)
                    cleanup_deleted = max(0, selected_files - remaining_files)
            with self._lock:
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
                    else:
                        self._status.message = "Completed."
                else:
                    self._status.phase = "error"
                    self._status.message = rsync_error or f"exited with code {rc}"
        except Exception as e:
            with self._lock:
                self._status.phase = "error"
                self._status.message = f"Error: {e}"

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
            "started_at", "finished_at", "result", "elapsed_seconds",
            "copy_seconds", "planned_bytes", "planned_files", "total_bytes",
            "total_files", "throughput_mib_s",
        ]
        row = {
            "started_at": datetime.fromtimestamp(status["started_at"]).astimezone().isoformat(),
            "finished_at": datetime.fromtimestamp(status["finished_at"]).astimezone().isoformat(),
            "result": status["message"],
            "elapsed_seconds": f'{status["elapsed_seconds"]:.3f}',
            "copy_seconds": f'{status["copy_seconds"]:.3f}',
            "planned_bytes": status["planned_bytes"],
            "planned_files": status["planned_files"],
            "total_bytes": status["total_bytes"],
            "total_files": status["total_files"],
            "throughput_mib_s": f'{status["throughput_mib_s"]:.3f}',
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

    def _unmount_storage(self) -> bool:
        return True if self._unmount is None else bool(self._unmount())

    def _unmount_storage_with_retries(self) -> bool:
        for attempt in range(UNMOUNT_ATTEMPTS):
            try:
                if self._unmount_storage():
                    return True
            except Exception as exc:
                self._logger.warning("Could not unmount external storage: %s", exc)
            if attempt + 1 < UNMOUNT_ATTEMPTS:
                time.sleep(UNMOUNT_RETRY_SEC)
        return False

    def _release_storage_claim(self, job: str) -> None:
        try:
            self._release_storage(job)
        except Exception as exc:
            self._logger.warning("Could not release external storage claim: %s", exc)

    def _refresh_storage_usage(self) -> None:
        if self._refresh_usage is not None:
            try:
                self._refresh_usage()
            except Exception as exc:
                self._logger.warning("Could not refresh storage usage: %s", exc)

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

    def _estimate_delta_bytes(
        self,
        src: Path,
        dst: Path,
        files_from: Path | None,
        total_bytes: int,
        total_files: int,
    ) -> tuple[int, int]:
        """Estimate remaining bytes/files that would be transferred if we ran rsync now.

        Uses rsync --dry-run itemization. Falls back to treating the whole dataset
        as remaining if rsync fails for any reason.
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
                timeout=RSYNC_SCAN_TIMEOUT_SEC,
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

            remaining_bytes = max(0, min(total_bytes, remaining_bytes))
            remaining_files = max(0, min(total_files, remaining_files))
            return remaining_bytes, remaining_files

        except Exception:
            # If rsync inspection fails, fall back to worst-case: everything remaining.
            return total_bytes, total_files

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
            out1 = subprocess.check_output(cmd1, text=True, stderr=subprocess.STDOUT, env=env,
                                           timeout=RSYNC_VERIFY_TIMEOUT_SEC)
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
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
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

        # 2) dst -> src: extra files (things that would be deleted)
        cmd2 = ["rsync", "-aH", "--dry-run", "--delete", "-v"]
        for pat in effective_excludes:
            cmd2 += ["--exclude", pat]
        cmd2 += [str(dst) + os.sep, str(src)]

        extra = 0
        try:
            out2 = subprocess.check_output(cmd2, text=True, stderr=subprocess.STDOUT, env=env,
                                           timeout=RSYNC_VERIFY_TIMEOUT_SEC)
            for line in out2.splitlines():
                if line.startswith("deleting "):
                    extra += 1
                    if len(samples) < sample_limit:
                        samples.append(f"EXTRA: {line[len('deleting '):]}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            return {
                "ok": False,
                "missing": -1,
                "changed": -1,
                "extra": -1,
                "samples": [f"VERIFY ERROR (dst->src): {e}"],
                "dst_files": 0,
                "dst_bytes": 0,
            }

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

__all__ = ["BackupStatus", "RsyncManager"]
