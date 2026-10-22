# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Xuất file bằng melt trên XML scene của app (cùng engine, cùng hiệu ứng với preview và `render_frames`).

Job `export`: chờ người dùng bấm "Xuất" trong app (`get_confirmation`) → lấy scene lúc đó (file gốc thay proxy) →
melt với `<consumer mlt_service="avformat">` đặt trong XML như `RenderRequest` của Kdenlive (đường dẫn có dấu nằm trong
XML, argv của melt chỉ ASCII) → NVENC, hỏng thì x264 → kiểm bằng ffprobe → đổi tên `<tên>.part.mp4` thành file đích.
File đích chỉ xuất hiện khi đã mã hoá xong; file nguồn của project không bao giờ bị ghi.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from . import jobs
from .jobs import Cancelled
from .bridge_client import BridgeClient
from .errors import BridgeError, RpcError
from .media import NO_WINDOW
from .paths import data_dir, find_tool
from .render import MLT_DENY

WAITING_STAGE = "chờ người dùng bấm Xuất trong ContextCut"
CONFIRM_POLL_S = 0.5
STALL_S = 300  # melt không nhích frame nào chừng này thì coi như treo
AAC_FRAME = 1024  # mẫu mỗi khung AAC: phần đệm cuối làm tiếng dài hơn hình tối đa chừng này


@dataclass(frozen=True)
class Preset:
    name: str
    title: str
    size: tuple[int, int] | None = None  # None = theo project
    fps: tuple[Fraction, ...] = ()  # rỗng = theo project


PRESETS = {
    "youtube-1080p60": Preset("youtube-1080p60", "YouTube 1080p60 (H.264)", (1920, 1080), (Fraction(60), Fraction(60000, 1001))),
    "project": Preset("project", "H.264 theo kích thước và fps của project"),
}
ENCODERS = ("auto", "nvenc", "x264")


def profile_fps(profile: dict[str, Any]) -> Fraction:
    return Fraction(int(profile["fps"]["num"]), int(profile["fps"]["den"]))


def check_preset(name: str, profile: dict[str, Any]) -> Preset:
    """Preset theo tên; project không hợp preset (cỡ, fps) → `ValueError` nói rõ phải làm gì."""
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError(f"Preset {name!r} không có; chọn: {', '.join(PRESETS)}.")
    fps = profile_fps(profile)
    size = (int(profile["width"]), int(profile["height"]))
    if (preset.size and size != preset.size) or (preset.fps and fps not in preset.fps):
        want = f"{preset.size[0]}×{preset.size[1]} " if preset.size else ""
        raise ValueError(
            f"Project đang là {size[0]}×{size[1]} {float(fps):g} fps, preset {name} cần {want}"
            f"{' hoặc '.join(f'{float(f):g}' for f in preset.fps)} fps. ContextCut không tự đổi cỡ khi xuất (dễ lệch khung): "
            "nhờ người dùng đổi Project Settings, hoặc dùng preset \"project\" (giữ cỡ và fps của project).")
    return preset


def _same(a: str | os.PathLike, b: str | os.PathLike) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def part_path(output: Path) -> Path:
    """File tạm cạnh file đích (cùng ổ nên đổi tên tức thì)."""
    return output.with_name(output.stem + ".part" + output.suffix)


def check_output(path: str, *, sources: list[str], project: str | None, overwrite: bool) -> Path:
    """Đường dẫn file xuất hợp lệ, hoặc `ValueError` (câu tiếng Việt cho agent)."""
    p = Path(path)
    if not p.is_absolute():
        raise ValueError(f"output phải là đường dẫn tuyệt đối (vd. D:/Videos/Tập 1.mp4), không phải {path!r}.")
    if p.suffix.lower() != ".mp4":
        raise ValueError("output phải có đuôi .mp4 (preset xuất MP4 H.264 + AAC).")
    p = Path(os.path.abspath(p))
    if not p.parent.is_dir():
        raise ValueError(f"Thư mục {p.parent} chưa có: hỏi người dùng muốn lưu ở đâu.")
    if not _same(os.path.realpath(p.parent), p.parent) or (p.exists() and not _same(os.path.realpath(p), p)):
        raise ValueError(f"{p} đi qua symlink/junction: đưa đường dẫn thật ({os.path.realpath(p)}).")
    if p.is_dir():
        raise ValueError(f"{p} là thư mục, cần tên file .mp4.")
    for target in (p, part_path(p)):
        if project and _same(target, project):
            raise ValueError("output trùng file project: chọn tên khác.")
        for src in sources:
            if src and _same(target, src):
                raise ValueError(f"output trùng file nguồn đang dùng trong project ({src}): xuất không bao giờ ghi đè "
                                 "file nguồn. Chọn tên khác.")
    if p.exists() and not overwrite:
        raise ValueError(f"{p} đã có. Chọn tên khác, hoặc hỏi người dùng rồi gọi lại với overwrite=true.")
    return p


def encoder_props(encoder: str, fps: Fraction, *, force_fail: bool = False) -> dict[str, str]:
    """Tham số consumer avformat cho một lần mã hoá (`nvenc` | `x264`): H.264 GOP nửa giây, 2 B-frame, AAC 320k."""
    gop = str(max(1, round(fps / 2)))
    if encoder == "nvenc":
        video = {"vcodec": "h264_nvenc", "preset": "p5", "tune": "hq", "rc": "vbr", "cq": "19", "vb": "0",
                 "maxrate": "40M", "bufsize": "80M", "spatial-aq": "1"}
        if force_fail:
            video["gpu"] = "99"  # ép NVENC hỏng thật (encoder không mở được) để thử đường rơi về x264
    elif encoder == "x264":
        video = {"vcodec": "libx264", "preset": "medium", "crf": "18"}
    else:
        raise ValueError(encoder)
    return {"f": "mp4", **video, "g": gop, "bf": "2", "pix_fmt": "yuv420p", "acodec": "aac", "ab": "320k",
            "ar": "48000", "channels": "2", "movflags": "+faststart", "real_time": "-1"}


_CONSUMER = re.compile(r"<consumer\b[^>]*/>|<consumer\b.*?</consumer>", re.S)


def export_xml(scene_xml: str, target: Path, start_f: int, end_f: int, props: dict[str, str]) -> str:
    """Scene của app + một consumer avformat ghi `[start_f, end_f)` vào `target` (bỏ consumer có sẵn nếu có)."""
    attrs = {"mlt_service": "avformat", "target": Path(target).as_posix(), "in": str(start_f), "out": str(end_f - 1)}
    attrs |= props
    consumer = "<consumer " + " ".join(f"{k}={quoteattr(v)}" for k, v in attrs.items()) + "/>"
    xml = _CONSUMER.sub("", scene_xml)
    cut = xml.rfind("</mlt>")
    if cut < 0:
        raise ValueError("scene không phải XML MLT (thiếu </mlt>)")
    return xml[:cut] + consumer + "\n" + xml[cut:]


def probe_streams(path: Path) -> dict[str, Any]:
    out = subprocess.run([find_tool("ffprobe"), "-v", "error", "-count_packets", "-print_format", "json", "-show_format",
                          "-show_streams", str(path)], capture_output=True, check=True, creationflags=NO_WINDOW).stdout
    return json.loads(out.decode("utf-8"))


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def verify(path: Path, *, frames: int, fps: Fraction, width: int, height: int) -> dict[str, Any]:
    """Kiểm file xuất bằng ffprobe: stream, số frame, thời lượng, lệch đầu hình/tiếng, độ dài tiếng, cỡ và fps."""
    info = probe_streams(path)
    streams = info.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    frame_s = 1 / float(fps)
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    check("streams", len(videos) == 1 and len(audios) == 1 and videos[0].get("codec_name") == "h264"
          and audios[0].get("codec_name") == "aac",
          " + ".join(f"{s.get('codec_type')} {s.get('codec_name')}" for s in streams) or "không có stream")
    v = videos[0] if videos else {}
    a = audios[0] if audios else {}
    got = int(v.get("nb_read_packets") or 0)
    check("frames", got == frames, f"{got} frame, cần {frames}")
    v_dur, a_dur = _num(v.get("duration")), _num(a.get("duration"))
    want_s = frames * frame_s
    check("duration", v_dur is not None and abs(v_dur - want_s) < frame_s,
          f"hình {v_dur if v_dur is not None else '?'} s, timeline {want_s:.3f} s")
    v_start, a_start = _num(v.get("start_time")), _num(a.get("start_time"))
    offset = abs(v_start - a_start) if v_start is not None and a_start is not None else None
    check("av_offset", offset is not None and offset < frame_s,
          f"lệch đầu hình/tiếng {offset * 1000:.1f} ms (< 1 frame = {frame_s * 1000:.1f} ms)" if offset is not None
          else "thiếu start_time")
    rate = int(a.get("sample_rate") or 48000)
    slack = frame_s + AAC_FRAME / rate
    check("audio_length", v_dur is not None and a_dur is not None and abs(a_dur - v_dur) <= slack,
          f"tiếng {a_dur} s, hình {v_dur} s (cho phép lệch {slack * 1000:.0f} ms: 1 frame + 1 khung AAC)")
    v_fps = None
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            v_fps = Fraction(v.get(key) or "")
            break
        except (ValueError, ZeroDivisionError):
            continue
    check("format", (v.get("width"), v.get("height")) == (width, height) and v_fps == fps,
          f"{v.get('width')}×{v.get('height')} {float(v_fps) if v_fps else '?'} fps, cần {width}×{height} {float(fps):g} fps")
    size = path.stat().st_size
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "size_mb": round(size / 1e6, 1),
            "video": {"codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
                      "fps": str(v_fps) if v_fps else None, "frames": got, "duration_s": v_dur,
                      "bitrate_kbps": round(int(v.get("bit_rate") or 0) / 1000) or None},
            "audio": {"codec": a.get("codec_name"), "sample_rate": a.get("sample_rate"), "channels": a.get("channels"),
                      "duration_s": a_dur}}


def is_broken(path: Path) -> str | None:
    """Lý do file ra không dùng được (không có hình nào), hoặc None."""
    if not path.exists() or path.stat().st_size == 0:
        return "không có file"
    try:
        info = probe_streams(path)
    except (subprocess.CalledProcessError, ValueError) as e:
        return f"ffprobe không đọc được file ({e})"
    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not video or not int(video[0].get("nb_read_packets") or 0):
        return "file không có hình"
    return None


def run_melt(xml: Path, total: int, report: Callable[..., None], label: str) -> tuple[int, list[str]]:
    """Chạy melt trên `xml` (cwd = thư mục của nó, đối số ASCII), báo tiến độ; `Cancelled` từ `report` giết melt."""
    proc = subprocess.Popen([find_tool("melt"), "-progress", xml.name], cwd=xml.parent,
                            env=os.environ | {"MLT_REPOSITORY_DENY": MLT_DENY}, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    state = {"frame": 0, "changed": time.monotonic()}
    tail: deque[str] = deque(maxlen=40)
    progress = re.compile(rb"Current Frame:\s*(\d+)")

    def pump() -> None:
        assert proc.stdout is not None
        buf = b""
        while chunk := proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096):
            buf += chunk
            *lines, buf = re.split(rb"[\r\n]", buf)
            for line in lines:
                if m := progress.search(line):
                    state["frame"], state["changed"] = int(m.group(1)), time.monotonic()
                elif line.strip():
                    tail.append(line.decode("utf-8", "replace").strip())

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    start = time.monotonic()
    try:
        while proc.poll() is None:
            done = min(state["frame"] + 1, total)
            elapsed = time.monotonic() - start
            eta = elapsed / done * (total - done) if done > 1 else None
            report(f"{label}: {done}/{total} frame", progress=done / total, eta_s=eta)
            if time.monotonic() - state["changed"] > STALL_S:
                proc.kill()
                tail.append(f"melt không nhích frame nào trong {STALL_S} s: đã dừng")
                break
            time.sleep(0.5)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    proc.wait()
    reader.join(timeout=5)
    return proc.returncode, list(tail)


def _bridge_wait_and_scene(confirm_id: str, originals: bool, report: Callable[..., None]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Chờ người dùng trả lời hộp xác nhận; đồng ý → scene lúc đó. Huỷ job khi đang chờ → đóng hộp trong app."""

    async def main() -> tuple[dict[str, Any], dict[str, Any]]:
        client = BridgeClient()
        try:
            while True:
                answer = await client.call("get_confirmation", {"confirm_id": confirm_id})
                if answer["state"] == "accepted":
                    return answer, await client.call("get_scene", {"originals": originals})
                if answer["state"] != "pending":
                    reason = {"rejected": "người dùng bấm Không xuất", "expired": "hết 15 phút không ai trả lời",
                              "cancelled": "hộp xác nhận đã bị huỷ"}.get(answer["state"], answer["state"])
                    raise Cancelled(f"không xuất: {reason}")
                try:
                    report(WAITING_STAGE, progress=0.0)
                except Cancelled:
                    try:
                        await client.call("cancel_confirmation", {"confirm_id": confirm_id})
                    except (BridgeError, RpcError):
                        pass
                    raise
                await asyncio.sleep(CONFIRM_POLL_S)
        except RpcError as e:
            if e.kind == "not_found":
                raise RuntimeError("ContextCut đã khởi động lại trong lúc chờ xác nhận: gọi export lại") from e
            raise RuntimeError(f"ContextCut báo lỗi khi chờ xác nhận: {e}") from e
        except BridgeError as e:
            raise RuntimeError(f"mất kết nối tới ContextCut trong lúc chờ xác nhận ({e})") from e
        finally:
            await client.close()

    return asyncio.run(main())


def run(params: dict[str, Any], report: Callable[..., None]) -> dict[str, Any]:
    """Job `export`. params: `confirm_id, output, start_f, end_f, preset, encoder, overwrite, originals, profile,
    sources, project`."""
    output = Path(params["output"])
    start_f, end_f = int(params["start_f"]), int(params["end_f"])
    frames = end_f - start_f
    answer, scene = _bridge_wait_and_scene(params["confirm_id"], bool(params.get("originals", True)), report)
    profile = scene["profile"]
    if (profile["width"], profile["height"], profile_fps(profile)) != (
            params["profile"]["width"], params["profile"]["height"], profile_fps(params["profile"])):
        raise RuntimeError("cỡ/fps của project đổi sau khi hỏi xác nhận: gọi export lại")
    if end_f > scene["duration_f"]:
        raise RuntimeError(f"timeline bây giờ chỉ dài {scene['duration_f']} frame, ngắn hơn khoảng xuất (sửa trong lúc "
                           "chờ xác nhận?): gọi export lại")
    fps = profile_fps(profile)
    work = data_dir() / "export" / uuid.uuid4().hex[:12]
    work.mkdir(parents=True, exist_ok=True)
    part = part_path(output)
    force_fail = os.environ.get("CONTEXTCUT_FORCE_NVENC_FAIL") == "1"
    encoder = params.get("encoder", "auto")
    attempts = ["nvenc", "x264"] if encoder == "auto" else [encoder]
    start = time.monotonic()
    fallback_reason = None
    used = None
    try:
        for enc in attempts:
            part.unlink(missing_ok=True)
            xml = work / f"export-{enc}.mlt"
            xml.write_text(export_xml(scene["xml"], part, start_f, end_f, encoder_props(enc, fps, force_fail=force_fail)),
                           encoding="utf-8")
            label = "xuất bằng NVENC" if enc == "nvenc" else "xuất bằng x264"
            if enc == "nvenc":
                def waiting(_: bool) -> None:
                    report("chờ GPU (job khác đang chạy)")
                with jobs.GpuLock(on_wait=waiting):
                    code, tail = run_melt(xml, frames, report, label)
            else:
                code, tail = run_melt(xml, frames, report, label)
            broken = f"melt dừng với mã {code}" if code != 0 else is_broken(part)
            if broken is None:
                used = enc
                break
            detail = " | ".join(line for line in tail if "Current Frame" not in line)[-600:]
            reason = f"{broken}: {detail}" if detail else broken
            print(f"[export] {enc} hỏng: {reason}", flush=True)
            part.unlink(missing_ok=True)
            if enc == "nvenc" and encoder == "auto":
                fallback_reason = reason
                continue
            raise RuntimeError(f"{label} hỏng: {reason}")
        encode_s = time.monotonic() - start
        report("kiểm file bằng ffprobe", progress=0.99)
        checks = verify(part, frames=frames, fps=fps, width=int(profile["width"]), height=int(profile["height"]))
        if output.exists() and not params.get("overwrite"):
            raise RuntimeError(f"{output} vừa xuất hiện trong lúc xuất (không ghi đè): file mới để ở {part}")
        try:
            os.replace(part, output)
        except PermissionError as e:
            raise RuntimeError(f"không thay được {output} (chương trình khác đang mở file?): file mới để ở {part}") from e
    except Cancelled:
        part.unlink(missing_ok=True)
        raise
    except BaseException:
        if used is None:
            part.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"output": output.as_posix(), "ok": checks["ok"], "checks": checks["checks"], "encoder": used,
            "fallback_reason": fallback_reason, "range": [start_f, end_f], "frames": frames,
            "encode_s": round(encode_s, 1), "realtime_x": round(frames / float(fps) / encode_s, 2) if encode_s else None,
            "size_mb": checks["size_mb"], "video": checks["video"], "audio": checks["audio"],
            "preset": params.get("preset"), "scene_revision": scene.get("revision"), "confirmed_revision": answer.get("revision")}
