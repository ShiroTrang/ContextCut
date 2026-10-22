# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Tiến trình worker của một job: `python -m contextcut_ai.analysis.worker <jobs/<id>.json>`.

Đọc job, lấy khoá GPU nếu loại job cần, chạy, ghi `done`/`failed`/`cancelled`. Lỗi đầy đủ (traceback) vào file log.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import jobs

Report = Callable[..., None]


class Cancelled(Exception):
    pass


def sleep_kind(params: dict[str, Any], report: Report) -> dict[str, Any]:
    """Chỉ để test: giữ GPU `seconds` giây, báo tiến độ mỗi 0,1 s."""
    seconds = float(params.get("seconds", 1))
    start = time.monotonic()
    while (elapsed := time.monotonic() - start) < seconds:
        report("đang ngủ", progress=elapsed / seconds)
        time.sleep(min(0.1, seconds - elapsed))
    return {"slept": seconds}


# loại job → (hàm "module:tên", cần khoá GPU); import muộn để worker "sleep" không cần thư viện nặng
KINDS: dict[str, tuple[str, bool]] = {
    "sleep": ("contextcut_ai.analysis.worker:sleep_kind", True),
    "transcribe": ("contextcut_ai.analysis.transcribe:run", True),
}


def resolve(target: str) -> Callable[[dict[str, Any], Report], dict[str, Any]]:
    module, name = target.split(":")
    return getattr(importlib.import_module(module), name)


def run(job_id: str) -> int:
    job = jobs.update(job_id, pid=os.getpid())
    if job["status"] != "queued" or jobs.cancel_requested(job_id):
        return 0  # đã huỷ trước khi worker kịp chạy
    target, needs_gpu = KINDS[job["kind"]]

    def report(stage: str, progress: float | None = None, eta_s: float | None = None) -> None:
        if jobs.cancel_requested(job_id):
            raise Cancelled()
        fields: dict[str, Any] = {"stage": stage}
        if progress is not None:
            fields["progress"] = round(max(0.0, min(1.0, progress)), 4)
        if eta_s is not None:
            fields["eta_s"] = round(eta_s)
        jobs.update(job_id, **fields)

    def waiting(_: bool) -> None:
        if jobs.cancel_requested(job_id):
            raise Cancelled()
        jobs.update(job_id, stage="chờ GPU (job khác đang chạy)")

    try:
        fn = resolve(target)
        lock = jobs.GpuLock(on_wait=waiting) if needs_gpu else None
        if lock:
            lock.__enter__()
        try:
            if jobs.cancel_requested(job_id):
                raise Cancelled()
            jobs.update(job_id, status="running", started_at=jobs.now(), stage="bắt đầu")
            result = fn(job["params"], report)
        finally:
            if lock:
                lock.__exit__(None, None, None)
        jobs.update(job_id, status="done", progress=1, eta_s=0, stage="xong", result=result, finished_at=jobs.now())
    except Cancelled:
        jobs.update(job_id, status="cancelled", stage="đã huỷ", finished_at=jobs.now())
    except Exception as e:  # noqa: BLE001 — mọi lỗi của job phải thành trạng thái failed, không để worker chết lặng
        traceback.print_exc()
        jobs.update(job_id, status="failed", error=f"{type(e).__name__}: {e}", finished_at=jobs.now())
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    return run(Path(argv[1]).stem)


if __name__ == "__main__":
    sys.exit(main())
