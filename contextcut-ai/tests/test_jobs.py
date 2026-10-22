# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json
import time
from datetime import datetime

import pytest

from contextcut_ai import jobs


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "Dữ liệu"))
    return tmp_path / "Dữ liệu"


def wait_for(job_id, statuses, timeout=20.0, seen=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if seen is not None:
            seen.append(job)
        if job["status"] in statuses:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} vẫn {jobs.get(job_id)['status']} sau {timeout} s")


def interval(job):
    return datetime.fromisoformat(job["started_at"]), datetime.fromisoformat(job["finished_at"])


def test_submit_runs_worker_to_done():
    job = jobs.submit("sleep", {"seconds": 0.2})
    assert job["status"] == "queued" and job["kind"] == "sleep"
    done = wait_for(job["id"], {"done", "failed"})
    assert done["status"] == "done", done
    assert done["result"] == {"slept": 0.2} and done["progress"] == 1


def test_second_gpu_job_waits():
    a = jobs.submit("sleep", {"seconds": 1.0})
    wait_for(a["id"], {"running"})
    b = jobs.submit("sleep", {"seconds": 1.0})
    seen: list[dict] = []
    done_b = wait_for(b["id"], {"done", "failed"}, seen=seen)
    done_a = wait_for(a["id"], {"done", "failed"})
    assert done_a["status"] == done_b["status"] == "done"
    assert any(j["status"] == "queued" and "chờ GPU" in (j["stage"] or "") for j in seen)
    a_start, a_end = interval(done_a)
    b_start, b_end = interval(done_b)
    assert b_start >= a_end or a_start >= b_end


def test_dead_worker_marked_failed(data_dir):
    jobs.jobs_dir().mkdir(parents=True, exist_ok=True)
    (jobs.jobs_dir() / "j-dead.json").write_text(json.dumps(
        {"id": "j-dead", "kind": "sleep", "params": {}, "status": "running", "stage": "x", "progress": 0.3,
         "pid": 999999, "created_at": "2026-10-22T08:00:00+07:00"}), encoding="utf-8")
    job = jobs.get("j-dead")
    assert job["status"] == "failed" and "dừng bất ngờ" in job["error"]


def test_cancel_queued_and_running():
    a = jobs.submit("sleep", {"seconds": 30})
    wait_for(a["id"], {"running"})
    b = jobs.submit("sleep", {"seconds": 0.1})
    assert jobs.cancel(b["id"])["status"] == "cancelled"
    assert jobs.cancel(a["id"])["status"] in {"running", "cancelled"}
    assert wait_for(a["id"], {"cancelled", "done", "failed"}, timeout=10)["status"] == "cancelled"
    time.sleep(1.0)  # worker của b thấy dấu huỷ và thoát, không chạy
    assert jobs.get(b["id"])["status"] == "cancelled" and jobs.get(b["id"])["started_at"] is None


def test_job_file_unicode_params(data_dir):
    job = jobs.submit("sleep", {"seconds": 0.1, "note": "Bắt Nạt Hải Sản"})
    wait_for(job["id"], {"done"})
    raw = json.loads((jobs.jobs_dir() / f"{job['id']}.json").read_text(encoding="utf-8"))
    assert raw["params"]["note"] == "Bắt Nạt Hải Sản"
    assert [j["id"] for j in jobs.recent()][0] == job["id"]


def test_unknown_job_raises():
    with pytest.raises(KeyError):
        jobs.get("khong-co")
