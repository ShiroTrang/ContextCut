# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Đọc `transcript.json` (giây trên bản ghi gốc) và đổi sang frame: frame nguồn, hoặc frame timeline qua các clip của
bản ghi đang nằm trên timeline (clip bị trim/cắt chỉ cho thấy phần từ còn hiện; clip lặp thì lời lặp)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Placement:
    start_f: int  # frame timeline của src_in_f
    src_in_f: int
    src_out_f: int


def load(companion: str | Path, file_hash: str) -> dict[str, Any] | None:
    path = Path(companion) / "analysis" / file_hash / "transcript.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def placements(items: list[dict[str, Any]], rec_id: str) -> list[Placement]:
    """Mỗi đoạn của bản ghi trên timeline một lần: clip hình và clip tiếng đi cặp (hoặc nhiều stream audio cùng chỗ)
    trùng `start_f` + `src_in_f` chỉ tính một. Clip đổi tốc độ bỏ qua (P2a chưa ánh xạ)."""
    seen: dict[tuple[int, int], Placement] = {}
    for it in items:
        if it.get("kind") != "clip" or it.get("source") != rec_id or float(it.get("speed", 1.0)) != 1.0:
            continue
        key = (it["start_f"], it["src_in_f"])
        place = Placement(it["start_f"], it["src_in_f"], it["src_out_f"])
        if key not in seen or place.src_out_f > seen[key].src_out_f:
            seen[key] = place
    return sorted(seen.values(), key=lambda p: (p.start_f, p.src_in_f))


def _frame(t: float, fps: float) -> int:
    return int(round(t * fps))


def _timed(seg: dict[str, Any], rec_id: str, words: list[dict[str, Any]], partial: bool) -> dict[str, Any]:
    text = " ".join(w["w"] for w in words) if partial else seg["text"]
    return {"recording": rec_id, "track": seg["track"], "speaker": seg.get("speaker"), "start_f": words[0]["start_f"],
            "end_f": words[-1]["end_f"], "text": text, "words": words, "partial": partial,
            "flags": seg.get("flags", [])}


def on_source(tr: dict[str, Any], fps: float, rec_id: str) -> list[dict[str, Any]]:
    out = []
    for seg in tr["segments"]:
        words = [w | {"start_f": _frame(w["start"], fps), "end_f": max(_frame(w["end"], fps), _frame(w["start"], fps) + 1)}
                 for w in seg["words"]]
        if words:
            out.append(_timed(seg, rec_id, words, False))
    return out


def on_timeline(tr: dict[str, Any], places: list[Placement], fps: float, rec_id: str) -> list[dict[str, Any]]:
    """Từ bắt đầu trong `[src_in_f, src_out_f)` của một placement thì hiện; cuối từ bị cắt theo mép clip."""
    out = []
    for place in places:
        shift = place.start_f - place.src_in_f
        for seg in tr["segments"]:
            visible = []
            for w in seg["words"]:
                sf = _frame(w["start"], fps)
                if not place.src_in_f <= sf < place.src_out_f:
                    continue
                ef = min(max(_frame(w["end"], fps), sf + 1), place.src_out_f)
                visible.append(w | {"start_f": sf + shift, "end_f": ef + shift})
            if visible:
                out.append(_timed(seg, rec_id, visible, len(visible) < len(seg["words"])))
    out.sort(key=lambda s: (s["start_f"], s["track"]))
    return out


def timecode(frame: int, fps: float) -> str:
    """`mm:ss.ff` (thêm giờ khi ≥ 1 giờ); ff là frame trong giây."""
    per_sec = max(1, int(round(fps)))
    seconds, ff = divmod(int(frame), per_sec)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}.{ff:02d}" if hours else f"{minutes:02d}:{secs:02d}.{ff:02d}"
