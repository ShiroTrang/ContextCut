# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Job nền (phiên âm, sau này render/xuất): mỗi job là một file JSON và một tiến trình worker tách rời.

Worker sống tiếp khi client đóng MCP server; mọi MCP server trên máy đọc chung thư mục job. Một job GPU nặng một lúc
trên cả máy (`GpuLock`); worker thoát là VRAM được trả hết.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import gpu_lock_file, jobs_dir

ACTIVE = ("queued", "running")
FINISHED = ("done", "failed", "cancelled")


class Cancelled(Exception):
    """Job dừng không phải vì lỗi (người dùng huỷ, từ chối xuất…); câu trong exception thành `stage` của job.

    Ở đây chứ không ở `analysis.worker`: worker chạy bằng `python -m` nên lớp khai báo trong nó là `__main__.Cancelled`,
    khác lớp mà module job import được."""


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def job_file(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def cancel_marker(job_id: str) -> Path:
    # File riêng thay vì trường trong file job: worker ghi file job liên tục, ghi chung sẽ đè mất yêu cầu huỷ
    return jobs_dir() / f"{job_id}.cancel"


def _write(job: dict[str, Any]) -> None:
    path = job_file(job["id"])
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    for attempt in range(20):  # Windows: os.replace lỗi khi tiến trình khác đang đọc đúng lúc đó
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    os.replace(tmp, path)


def _read(job_id: str) -> dict[str, Any]:
    path = job_file(job_id)
    for attempt in range(20):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError(job_id) from None
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.02 * (attempt + 1))
    return json.loads(path.read_text(encoding="utf-8"))


def update(job_id: str, **fields: Any) -> dict[str, Any]:
    job = _read(job_id) | fields
    _write(job)
    return job


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    # os.kill trên Windows là TerminateProcess: hỏi mã thoát thay vì gửi tín hiệu
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _spawn(path: Path, log: Path) -> int:
    cmd = [sys.executable, "-m", "contextcut_ai.analysis.worker", str(path)]
    flags = 0
    if os.name == "nt":
        # Tách khỏi console và nhóm tiến trình của client; thoát khỏi Job Object của client nếu được phép
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        breakaway = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
    with log.open("ab") as out:
        for extra in ((breakaway,) if os.name == "nt" else ()) + (0,):
            try:
                return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                        creationflags=flags | extra, close_fds=True,
                                        start_new_session=os.name != "nt").pid
            except PermissionError:
                continue  # Job Object không cho breakaway
    raise RuntimeError("không khởi động được worker")


def submit(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    jobs_dir().mkdir(parents=True, exist_ok=True)
    job_id = f"{kind}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    log = jobs_dir() / f"{job_id}.log"
    job = {"id": job_id, "kind": kind, "params": params, "status": "queued", "stage": "đang khởi động worker",
           "progress": 0.0, "eta_s": None, "created_at": now(), "started_at": None, "finished_at": None, "pid": None,
           "result": None, "error": None, "log": str(log)}
    _write(job)
    pid = _spawn(job_file(job_id), log)
    current = _read(job_id)
    if current["pid"] is None:  # worker có thể đã tự ghi pid của nó
        current = update(job_id, pid=pid)
    return current


def get(job_id: str) -> dict[str, Any]:
    job = _read(job_id)
    if job["status"] in ACTIVE and job.get("pid") and not pid_alive(job["pid"]):
        time.sleep(0.2)  # worker có thể vừa ghi trạng thái cuối rồi thoát
        job = _read(job_id)
        if job["status"] in ACTIVE:
            job = update(job_id, status="failed", finished_at=now(),
                         error=f"worker dừng bất ngờ (pid {job['pid']}); xem log {job.get('log')}. "
                               "Gọi lại tool để chạy tiếp từ phần đã xong.")
    return job


def recent(limit: int = 10) -> list[dict[str, Any]]:
    if not jobs_dir().exists():
        return []
    files = sorted(jobs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [get(p.stem) for p in files]


def cancel(job_id: str) -> dict[str, Any]:
    job = get(job_id)
    if job["status"] in FINISHED:
        return job
    cancel_marker(job_id).touch()
    if job["status"] == "queued":
        return update(job_id, status="cancelled", finished_at=now(), stage="đã huỷ trước khi chạy")
    return job


def cancel_requested(job_id: str) -> bool:
    return cancel_marker(job_id).exists()


class GpuLock:
    """Khoá GPU toàn máy (byte đầu của `gpu.lock`); tiến trình chết thì hệ điều hành tự nhả."""

    def __init__(self, on_wait=None, poll_s: float = 0.25):
        self._on_wait = on_wait
        self._poll_s = poll_s
        self._fh = None

    def __enter__(self) -> GpuLock:
        path = gpu_lock_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a+b")
        waited = False
        while not self._try_lock():
            if self._on_wait:
                self._on_wait(waited)
            waited = True
            time.sleep(self._poll_s)
        return self

    def _try_lock(self) -> bool:
        assert self._fh is not None
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __exit__(self, *exc: object) -> None:
        assert self._fh is not None
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._fh.close()
            self._fh = None
