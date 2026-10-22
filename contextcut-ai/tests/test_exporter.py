# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""P2c Task 22: job xuất (melt + consumer avformat trong XML, NVENC → x264, kiểm ffprobe, chờ xác nhận trong app)."""

import asyncio
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import make_frame_code_video, read_frame_code  # noqa: E402

from contextcut_ai import exporter, jobs, paths, render  # noqa: E402
from fake_bridge import EDITOR_STATE  # noqa: E402

PROFILE_25 = {"fps": {"num": 25, "den": 1}, "width": 1280, "height": 720}
FPS = Fraction(25)


def nvenc_available() -> bool:
    try:
        out = subprocess.run([paths.find_tool("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    except paths.ToolMissing:
        return False
    return "h264_nvenc" in out and shutil.which("nvidia-smi") is not None


@pytest.fixture(scope="module")
def scene_xml(tmp_path_factory) -> str:
    """Scene MLT 720p 25 fps: video mã số frame 25 fps (frame timeline f = mã f) + tiếng sine, 4 s = 100 frame."""
    try:
        melt = paths.find_tool("melt")
    except paths.ToolMissing:
        pytest.skip("cần melt (MSYS2 của dự án)")
    d = tmp_path_factory.mktemp("export-scene")
    code = make_frame_code_video(d / "code.mp4", fps=25, seconds=4)
    av = d / "code-av.mp4"
    subprocess.run([paths.find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(code), "-f", "lavfi",
                    "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-c:v", "copy", "-c:a", "aac", "-shortest",
                    str(av)], check=True)
    scene = d / "scene.mlt"
    subprocess.run([melt, "-quiet", "-profile", "atsc_720p_25", str(av), "-consumer", f"xml:{scene}"], check=True,
                   env=os.environ | {"MLT_REPOSITORY_DENY": render.MLT_DENY}, capture_output=True)
    return scene.read_text(encoding="utf-8")


def frame_code_at(video: Path, index: int, tmp: Path) -> int:
    shot = tmp / f"shot-{index}.png"
    subprocess.run([paths.find_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf",
                    f"select=eq(n\\,{index})", "-frames:v", "1", str(shot)], check=True)
    return read_frame_code(shot)


def encode(scene_xml: str, out_dir: Path, name: str, start_f: int, end_f: int, encoder: str, *, force_fail=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    xml = out_dir / f"export-{encoder}.mlt"
    xml.write_text(exporter.export_xml(scene_xml, target, start_f, end_f,
                                       exporter.encoder_props(encoder, FPS, force_fail=force_fail)), encoding="utf-8")
    stages = []
    code, tail = exporter.run_melt(xml, end_f - start_f, lambda s, progress=None, eta_s=None: stages.append((s, progress)),
                                   encoder)
    return target, code, tail, stages


def test_check_preset():
    hd60 = {"fps": {"num": 60, "den": 1}, "width": 1920, "height": 1080}
    assert exporter.check_preset("youtube-1080p60", hd60).name == "youtube-1080p60"
    assert exporter.check_preset("youtube-1080p60", hd60 | {"fps": {"num": 60000, "den": 1001}}).size == (1920, 1080)
    with pytest.raises(ValueError, match="project"):
        exporter.check_preset("youtube-1080p60", PROFILE_25)
    with pytest.raises(ValueError, match="1280×720 25 fps"):
        exporter.check_preset("youtube-1080p60", PROFILE_25)
    assert exporter.check_preset("project", PROFILE_25).name == "project"
    with pytest.raises(ValueError, match="không có"):
        exporter.check_preset("4k", PROFILE_25)


def test_check_output_rules(tmp_path):
    folder = tmp_path / "Bắt Nạt Hải Sản"
    folder.mkdir()
    source = folder / "Ghi hình 01.mp4"
    source.write_bytes(b"x")
    project = folder / "Tập 1.kdenlive"
    ok = exporter.check_output(str(folder / "Tập 1.mp4"), sources=[str(source)], project=str(project), overwrite=False)
    assert ok == folder / "Tập 1.mp4"
    bad = {
        "Tập 1.mp4": "tuyệt đối",
        str(folder / "Tập 1.mkv"): ".mp4",
        str(tmp_path / "chưa có" / "a.mp4"): "chưa có",
        str(source).upper(): "file nguồn",
        str(source): "file nguồn",
    }
    for path, why in bad.items():
        with pytest.raises(ValueError, match=why):
            exporter.check_output(path, sources=[str(source)], project=str(project), overwrite=True)
    existing = folder / "cũ.mp4"
    existing.write_bytes(b"x")
    with pytest.raises(ValueError, match="overwrite"):
        exporter.check_output(str(existing), sources=[], project=None, overwrite=False)
    assert exporter.check_output(str(existing), sources=[], project=None, overwrite=True) == existing


def test_export_xml_has_consumer_and_range(tmp_path):
    scene = '<?xml version="1.0"?><mlt><profile width="1280"/><consumer mlt_service="sdl2"/><tractor id="t"/></mlt>'
    target = tmp_path / "Bắt Nạt" / "xuất & thử.part.mp4"
    root = ET.fromstring(exporter.export_xml(scene, target, 10, 60, exporter.encoder_props("x264", FPS)))
    consumers = root.findall("consumer")
    assert len(consumers) == 1
    c = consumers[0].attrib
    assert (c["mlt_service"], c["target"], c["in"], c["out"]) == ("avformat", target.as_posix(), "10", "59")
    assert (c["vcodec"], c["acodec"], c["f"], c["g"], c["real_time"]) == ("libx264", "aac", "mp4", "12", "-1")
    nv = exporter.encoder_props("nvenc", Fraction(60), force_fail=True)
    assert (nv["vcodec"], nv["cq"], nv["g"], nv["gpu"]) == ("h264_nvenc", "19", "30", "99")
    assert "gpu" not in exporter.encoder_props("nvenc", Fraction(60))


def test_encode_x264_unicode_path_verified(scene_xml, tmp_path):
    target, code, tail, stages = encode(scene_xml, tmp_path / "Bắt Nạt Hải Sản", "xuất thử.part.mp4", 10, 60, "x264")
    assert code == 0, tail
    assert exporter.is_broken(target) is None
    checks = exporter.verify(target, frames=50, fps=FPS, width=1280, height=720)
    assert checks["ok"], checks["checks"]
    assert [c["name"] for c in checks["checks"]] == ["streams", "frames", "duration", "av_offset", "audio_length", "format"]
    assert checks["video"]["frames"] == 50 and checks["audio"]["codec"] == "aac"
    assert frame_code_at(target, 0, tmp_path) == 10 and frame_code_at(target, 49, tmp_path) == 59
    assert stages and all("frame" in s for s, _ in stages)


def test_verify_detects_short_file(scene_xml, tmp_path):
    target, code, _, _ = encode(scene_xml, tmp_path, "ngắn.mp4", 0, 20, "x264")
    assert code == 0
    checks = exporter.verify(target, frames=25, fps=FPS, width=1920, height=1080)
    failed = {c["name"] for c in checks["checks"] if not c["ok"]}
    assert not checks["ok"] and {"frames", "duration", "format"} <= failed
    assert "streams" not in failed and "av_offset" not in failed


def test_nvenc_forced_fail_is_broken(scene_xml, tmp_path):
    """gpu=99: h264_nvenc không mở được (mọi máy), melt dừng; file dở bị phát hiện là hỏng."""
    target, code, tail, _ = encode(scene_xml, tmp_path, "nv.part.mp4", 0, 25, "nvenc", force_fail=True)
    assert code != 0 or exporter.is_broken(target), tail


@pytest.mark.skipif(not nvenc_available(), reason="cần GPU NVIDIA có NVENC")
def test_encode_nvenc_verified(scene_xml, tmp_path):
    target, code, tail, _ = encode(scene_xml, tmp_path, "nv.part.mp4", 25, 75, "nvenc")
    assert code == 0, tail
    checks = exporter.verify(target, frames=50, fps=FPS, width=1280, height=720)
    assert checks["ok"], checks["checks"]
    assert frame_code_at(target, 0, tmp_path) == 25


# --- job export qua worker thật + cầu nối giả ---------------------------------------------------------------------

def confirmations(*states: str):
    """get_confirmation giả: trả lần lượt các state, cái cuối lặp mãi."""
    calls = []

    def answer(params):
        calls.append(params)
        state = states[min(len(calls) - 1, len(states) - 1)]
        return {"confirm_id": params["confirm_id"], "state": state, "revision": None if state == "pending" else 77}
    return answer, calls


def export_params(tmp_path: Path, **over) -> dict:
    out_dir = tmp_path / "Xuất ra"
    out_dir.mkdir(exist_ok=True)
    return {"confirm_id": "c-1", "output": (out_dir / "Tập 1.mp4").as_posix(), "start_f": 10, "end_f": 60,
            "preset": "project", "encoder": "x264", "overwrite": False, "originals": True, "profile": PROFILE_25,
            "sources": [], "project": EDITOR_STATE["project"]["path"], "sequence": EDITOR_STATE["sequence"]["uuid"]} | over


async def wait_job(job_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job["status"] not in jobs.ACTIVE:
            return job
        await asyncio.sleep(0.2)
    raise AssertionError(f"job {job_id} chưa xong: {jobs.get(job_id)}")


@pytest.fixture
def job_env(bridge, tmp_path, monkeypatch, scene_xml):
    monkeypatch.setenv("CONTEXTCUT_DATA_DIR", str(tmp_path / "data"))
    bridge.responses["get_scene"] = {"revision": 77, "xml": scene_xml, "root": None, "profile": PROFILE_25,
                                     "duration_f": 100, "proxies": False}
    return bridge


@pytest.mark.anyio
async def test_job_waits_for_confirmation_then_exports(job_env, tmp_path):
    answer, calls = confirmations("pending", "pending", "accepted")
    job_env.responses["get_confirmation"] = answer
    params = export_params(tmp_path)
    job = jobs.submit("export", params)
    done = await wait_job(job["id"])
    assert done["status"] == "done", done
    result = done["result"]
    assert result["ok"] and result["encoder"] == "x264" and result["fallback_reason"] is None
    assert result["frames"] == 50 and result["confirmed_revision"] == 77
    out = Path(params["output"])
    assert out.exists() and not list(out.parent.glob("*.part.mp4"))
    assert len(calls) >= 3
    assert [m for m, _ in job_env.calls].count("get_scene") == 1
    assert not list((tmp_path / "data" / "export").glob("*"))  # thư mục làm việc đã dọn


@pytest.mark.anyio
async def test_job_rejected_writes_nothing(job_env, tmp_path):
    job_env.responses["get_confirmation"], _ = confirmations("pending", "rejected")
    params = export_params(tmp_path)
    done = await wait_job(jobs.submit("export", params)["id"])
    assert done["status"] == "cancelled" and "Không xuất" in done["stage"]
    assert not list(Path(params["output"]).parent.iterdir())
    assert "get_scene" not in [m for m, _ in job_env.calls]


@pytest.mark.anyio
async def test_job_cancel_while_waiting_closes_dialog(job_env, tmp_path):
    job_env.responses["get_confirmation"], _ = confirmations("pending")
    job_env.responses["cancel_confirmation"] = {"confirm_id": "c-1", "state": "cancelled", "revision": 77}
    job = jobs.submit("export", export_params(tmp_path))
    deadline = time.monotonic() + 20
    while jobs.get(job["id"])["stage"] != exporter.WAITING_STAGE and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    jobs.cancel(job["id"])
    done = await wait_job(job["id"])
    assert done["status"] == "cancelled"
    assert ("cancel_confirmation", {"confirm_id": "c-1"}) in job_env.calls


@pytest.mark.anyio
async def test_job_nvenc_failure_falls_back_to_x264(job_env, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_FORCE_NVENC_FAIL", "1")
    job_env.responses["get_confirmation"], _ = confirmations("accepted")
    params = export_params(tmp_path, encoder="auto")
    done = await wait_job(jobs.submit("export", params)["id"], timeout=90)
    assert done["status"] == "done", done
    assert done["result"]["encoder"] == "x264" and done["result"]["fallback_reason"]
    assert done["result"]["ok"]
    nvenc_only = await wait_job(jobs.submit("export", export_params(tmp_path, encoder="nvenc",
                                                                   output=(tmp_path / "Xuất ra" / "b.mp4").as_posix()))["id"])
    assert nvenc_only["status"] == "failed" and "NVENC" in nvenc_only["error"]
    assert not (tmp_path / "Xuất ra" / "b.mp4").exists() and not list((tmp_path / "Xuất ra").glob("b.*.part.mp4"))


@pytest.mark.anyio
async def test_job_timeline_shorter_after_confirmation(job_env, tmp_path):
    job_env.responses["get_confirmation"], _ = confirmations("accepted")
    job_env.responses["get_scene"]["duration_f"] = 40
    done = await wait_job(jobs.submit("export", export_params(tmp_path))["id"])
    assert done["status"] == "failed" and "40 frame" in done["error"]


@pytest.mark.anyio
async def test_job_refuses_other_project_after_confirmation(job_env, tmp_path):
    """Người dùng mở project khác rồi mới bấm Xuất ở hộp cũ: không xuất timeline của project mới."""
    job_env.responses["get_confirmation"], _ = confirmations("accepted")
    params = export_params(tmp_path, project="D:/Videos/Tập khác.kdenlive")
    done = await wait_job(jobs.submit("export", params)["id"])
    assert done["status"] == "failed" and "đã khác" in done["error"]
    assert "get_scene" not in [m for m, _ in job_env.calls] and not Path(params["output"]).exists()
