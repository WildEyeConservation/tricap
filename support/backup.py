# backup.py
# Minimal rsync-backed backup engine with simple filesystem-snapshot progress.
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

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

class RsyncManager:
    """
    Runs rsync in a background thread. Progress is derived by scanning:
      bytes_copied = Σ min(dst_size, src_size) over all source files
      files_done   = count(dst_size >= src_size)
    This is robust for 20s polling and avoids parsing rsync output.
    """
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = BackupStatus()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[str] | subprocess.Popen[bytes] | None = None

        # job config for snapshotting
        self._src: Path | None = None
        self._dst: Path | None = None
        self._excludes: list[str] = []
        self._verify: bool = False
        self._delete: bool = False

        # cache totals
        self._totals_ready = False

        # tiny cache to avoid re-scanning too often (not strictly needed for 20s poll)
        self._snap_cache_ts = 0.0
        self._snap_cache: tuple[int, int] = (0, 0)  # (bytes_copied, files_done)

    # ---------------- Public API ----------------

    def start(
        self,
        src: str,
        dst: str,
        excludes: list[str] | None = None,
        verify: bool = False,
        delete: bool = False,
    ) -> dict[str, Any]:
        excludes = excludes or []
        src_p = Path(src)
        dst_p = Path(dst)

        if not src_p.exists() or not src_p.is_dir():
            return {"success": False}
        dst_p.mkdir(parents=True, exist_ok=True)

        with self._lock:
            if self._status.running:
                return {"success": False}

            self._src = src_p.resolve()
            self._dst = dst_p.resolve()
            self._excludes = excludes
            self._verify = bool(verify)
            self._delete = bool(delete)

            # compute totals once
            total_bytes, total_files = self._scan_totals(self._src, self._excludes)
            self._status = BackupStatus(
                running=True,
                phase="copying",
                message="Copying...",
                started_at=time.time(),
                total_files=total_files,
                total_bytes=total_bytes,
            )
            self._totals_ready = True
            self._snap_cache_ts = 0.0

            self._thread = threading.Thread(target=self._run_rsync, daemon=True)
            self._thread.start()
            return {"success": True}

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
            st = asdict(self._status)
            src = self._src
            dst = self._dst
            excludes = list(self._excludes)

        # If a job is configured, compute a fresh (or cached) snapshot
        if src and dst and self._totals_ready:
            now = time.time()
            if now - self._snap_cache_ts >= 1.5:  # throttle a little
                bytes_copied, files_done = self._snapshot_progress(src, dst, excludes)
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
    # ---------------- Internals ----------------

    def _run_rsync(self) -> None:
        assert self._src is not None and self._dst is not None
        src_arg = str(self._src) + os.sep  # copy *contents*
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
        for pat in self._excludes:
            cmd += ["--exclude", pat]
        cmd += [src_arg, str(self._dst)]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False,
            )
            rc = self._proc.wait()
            with self._lock:
                self._status.running = False
                self._status.finished_at = time.time()
                if self._status.phase == "stopping":
                    # treat as user-stopped regardless of rc
                    self._status.phase = "finished"
                    self._status.message = "Stopped by user."
                elif rc == 0:
                    self._status.phase = "finished"
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

    # ---------- helpers ----------

    def _excluded(self, rel: str, patterns: list[str]) -> bool:
        r = rel.lower()
        return any(p.lower() in r for p in patterns)

    def _scan_totals(self, src: Path, excludes: list[str]) -> tuple[int, int]:
        total_bytes = 0
        total_files = 0
        for root, dirs, files in os.walk(src):
            root_p = Path(root)
            # prune excluded dirs
            dirs[:] = [d for d in dirs if not self._excluded(str((root_p / d).relative_to(src)), excludes)]
            for f in files:
                rel = (root_p / f).relative_to(src)
                if self._excluded(str(rel), excludes):
                    continue
                try:
                    total_bytes += (root_p / f).stat().st_size
                    total_files += 1
                except Exception:
                    pass
        return total_bytes, total_files

    def _snapshot_progress(self, src: Path, dst: Path, excludes: list[str]) -> tuple[int, int]:
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

        src_arg = str(src) + os.sep  # copy *contents*
        cmd: list[str] = [
            "rsync",
            "-aH",
            "--dry-run",
            "--itemize-changes",
            "--no-human-readable",          # numeric sizes in stats
            "--out-format=%i|%l|%n",        # itemize code | length | path
        ]
        # Be careful enabling --checksum here: it would re-hash everything every poll.
        # Use the manager's verify flag only if you *really* want content-compare.
        if self._verify:
            cmd.append("--checksum")
        for pat in excludes:
            cmd += ["--exclude", pat]
        cmd += [src_arg, str(dst)]

        env = os.environ.copy()
        env["LC_ALL"] = "C"  # stable parse

        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, env=env)
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

            # Compute progress from totals – clamp to sane bounds
            bytes_copied = max(0, min(total_bytes, total_bytes - remaining_bytes))
            files_done = max(0, min(total_files, total_files - remaining_files))
            return bytes_copied, files_done

        except Exception:
            # Fallback: filesystem snapshot (min(dst_size, src_size))
            bytes_present = 0
            files_done = 0
            for root, dirs, files in os.walk(src):
                root_p = Path(root)
                dirs[:] = [d for d in dirs if not self._excluded(str((root_p / d).relative_to(src)), excludes)]
                for f in files:
                    rel = (root_p / f).relative_to(src)
                    if self._excluded(str(rel), excludes):
                        continue
                    sp = root_p / f
                    try:
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
            return bytes_present, files_done

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

        src_arg = str(src) + os.sep
        dst_arg = str(dst)

        # 1) src -> dst: missing/changed
        cmd1 = ["rsync", "-rltH", "--size-only", "--dry-run", "--itemize-changes", "--out-format=%i|%n",
                 "--no-perms", "--no-owner", "--no-group"]
        if checksum:
            cmd1.append("--checksum")
        for pat in excludes:
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

        # 2) dst -> src: extra files (things that would be deleted)
        cmd2 = ["rsync", "-aH", "--dry-run", "--delete", "-v"]
        for pat in excludes:
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

        # 3) quick dst totals
        dst_bytes, dst_files = self._scan_totals(dst, excludes)

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
