from __future__ import annotations

import os
import time
import hashlib
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


CHUNK_SIZE = 40 * 1024 * 1024  # 40 MiB

@dataclass
class BackupStatus:
    running: bool = False
    phase: str = "idle"  # idle | scanning | copying | stopping | finished | error
    message: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    total_files: int = 0
    files_done: int = 0

    total_bytes: int = 0
    bytes_copied: int = 0

    current_relpath: Optional[str] = None
    current_bytes_total: int = 0
    current_bytes_done: int = 0

    # computed on demand by .status()
    bytes_per_sec: float = 0.0
    eta_seconds: Optional[float] = None


class BackupManager:
    """Threaded file copy with resumable per-file progress and global status."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._status = BackupStatus()
        self._cfg: Dict[str, Any] = {}

    # ---------- Public API used by Flask ----------

    def start(self, src: str, dst: str, excludes: List[str] | None = None, verify: bool = False) -> Dict[str, Any]:
        excludes = excludes or []
        with self._lock:
            if self._status.running:
                return {"success": False}
            src_p, dst_p = Path(src), Path(dst)
            if not src_p.exists() or not src_p.is_dir():
                return {"success": False}
            dst_p.mkdir(parents=True, exist_ok=True)

            self._cfg = {
                "src": str(src_p.resolve()),
                "dst": str(dst_p.resolve()),
                "excludes": excludes,
                "verify": bool(verify),
            }
            self._stop_evt.clear()
            self._status = BackupStatus(
                running=True, phase="scanning", message="Scanning files...", started_at=time.time()
            )
            self._thread = threading.Thread(target=self._run_backup, daemon=True)
            self._thread.start()
            return {"success": True}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if not self._status.running:
                return {"success": False}
            self._status.phase = "stopping"
            self._stop_evt.set()
            return {"success": True}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            st = asdict(self._status)
            # compute speed/eta
            if self._status.running and self._status.started_at and self._status.bytes_copied > 0:
                elapsed = max(1e-6, time.time() - self._status.started_at)
                bps = self._status.bytes_copied / elapsed
                st["bytes_per_sec"] = bps
                if self._status.total_bytes > 0:
                    remain = self._status.total_bytes - self._status.bytes_copied
                    st["eta_seconds"] = max(0.0, remain / max(1e-6, bps))
            return st

    # ---------- Internal implementation ----------

    def _is_excluded(self, rel: str, patterns: List[str]) -> bool:
        if not patterns:
            return False
        low = rel.lower()
        return any(p.lower() in low for p in patterns)

    def _scan(self, src: Path, excludes: List[str]) -> List[Path]:
        files: List[Path] = []
        for root, dirs, fnames in os.walk(src):
            root_p = Path(root)
            # prune excluded dirs
            dirs[:] = [d for d in dirs if not self._is_excluded(str(Path(root_p, d).relative_to(src)), excludes)]
            for f in fnames:
                rel = str(Path(root_p, f).relative_to(src))
                if self._is_excluded(rel, excludes):
                    continue
                fp = root_p / f
                try:
                    if fp.is_file():
                        files.append(fp)
                except Exception:
                    continue
        return files

    def _hash_file(self, path: Path) -> str:
        h = hashlib.md5()
        with path.open("rb") as r:
            while True:
                chunk = r.read(8 * 1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _copy_streaming(self, src: Path, dst: Path, can_resume: bool, verify: bool) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)

        src_sz = src.stat().st_size
        self._status.current_bytes_total = src_sz
        done = 0

        mode = "wb"
        offset = 0

        if dst.exists():
            dst_sz = dst.stat().st_size
            if dst_sz >= src_sz:
                self._status.current_bytes_done = src_sz
                return
            if can_resume:
                mode = "r+b"
                offset = dst_sz
                done = dst_sz

        with src.open("rb") as rs:
            if offset:
                rs.seek(offset)
            with dst.open(mode) as ws:
                if offset:
                    ws.seek(offset)
                while not self._stop_evt.is_set():
                    buf = rs.read(CHUNK_SIZE)
                    if not buf:
                        break
                    ws.write(buf)
                    done += len(buf)
                    # hot path stats (ok without lock in CPython)
                    self._status.bytes_copied += len(buf)
                    self._status.current_bytes_done = done

        if verify and not self._stop_evt.is_set():
            if self._hash_file(src) != self._hash_file(dst):
                raise IOError("MD5 mismatch after copy")

    def _run_backup(self) -> None:
        src = Path(self._cfg["src"])
        dst = Path(self._cfg["dst"])
        excludes: List[str] = self._cfg["excludes"]
        verify: bool = self._cfg["verify"]

        try:
            files = self._scan(src, excludes)
            total_bytes = 0
            for f in files:
                try:
                    total_bytes += f.stat().st_size
                except Exception:
                    pass

            with self._lock:
                self._status.total_files = len(files)
                self._status.total_bytes = total_bytes
                self._status.phase = "copying"
                self._status.message = "Copying..."

            for i, f in enumerate(files, start=1):
                if self._stop_evt.is_set():
                    break
                rel = str(f.relative_to(src))
                with self._lock:
                    self._status.current_relpath = rel
                    self._status.current_bytes_done = 0
                    try:
                        self._status.current_bytes_total = f.stat().st_size
                    except Exception:
                        self._status.current_bytes_total = 0

                try:
                    self._copy_streaming(f, dst / rel, can_resume=True, verify=verify)
                except Exception as e:
                    with self._lock:
                        self._status.phase = "error"
                        self._status.message = f"Error copying {rel}: {e}"
                    break

                with self._lock:
                    self._status.files_done = i

            with self._lock:
                if self._stop_evt.is_set():
                    self._status.phase = "finished"
                    self._status.message = "Stopped by user."
                elif self._status.phase != "error":
                    self._status.phase = "finished"
                    self._status.message = "Completed."
                self._status.running = False
                self._status.finished_at = time.time()

        except Exception as e:
            with self._lock:
                self._status.phase = "error"
                self._status.message = f"Fatal error: {e}"
                self._status.running = False
                self._status.finished_at = time.time()


# Option A: expose a singleton manager for easy imports across the app
manager = BackupManager()

__all__ = ["BackupStatus", "BackupManager", "manager"]
