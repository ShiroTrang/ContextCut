# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Phụ đề từ transcript: ghép từ thành dòng (design §8.3: 32–42 ký tự, ngắt theo khoảng nghỉ), xử lý hai người nói
chồng nhau, style câu đắt theo người nói, và bắt mép câu đắt về đúng đầu/cuối từ."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SENTENCE_END = re.compile(r"[.?!…]$")
PUNCT_END = re.compile(r"[,.?!;:…]$")
DEFAULT_COLORS = {"nhan": "#FFFFFF"}
FRIEND_COLOR = "#FFD400"


def _utterances(segments: list[dict[str, Any]], fps: float, pause_s: float, seg_gap_s: float) -> list[list[dict[str, Any]]]:
    """Chuỗi từ liền nhau của cùng một track; tách ở khoảng nghỉ ≥ pause_s, hoặc ở ranh giới câu ASR khi có nghỉ
    ≥ seg_gap_s hoặc câu trước kết thúc bằng dấu chấm/hỏi/than."""
    out: list[list[dict[str, Any]]] = []
    by_track: dict[tuple[str, int], list[tuple[int, int, dict[str, Any]]]] = {}
    for si, seg in enumerate(segments):
        for wi, w in enumerate(seg["words"]):
            item = w | {"speaker": seg.get("speaker"), "_seg": si, "_first": wi == 0}
            by_track.setdefault((seg["recording"], seg["track"]), []).append((w["start_f"], si, item))
    for words in by_track.values():
        words.sort(key=lambda x: (x[0], x[1]))
        current: list[dict[str, Any]] = []
        for _, _, w in words:
            if current:
                prev = current[-1]
                gap = (w["start_f"] - prev["end_f"]) / fps
                new_segment = w["_seg"] != prev["_seg"]
                if gap >= pause_s or (new_segment and (gap >= seg_gap_s or SENTENCE_END.search(prev["w"]))):
                    out.append(current)
                    current = []
            current.append(w)
        if current:
            out.append(current)
    return out


def _text(words: list[dict[str, Any]]) -> str:
    return " ".join(w["w"] for w in words)


def _split(words: list[dict[str, Any]], fps: float, max_chars: int, min_chars: int) -> list[list[dict[str, Any]]]:
    """Chia đệ quy ở chỗ tốt nhất: khoảng nghỉ dài nhất, rồi dấu câu, rồi cân độ dài; ưu tiên cả hai nửa ≥ min_chars."""
    text = _text(words)
    if len(text) <= max_chars or len(words) < 2:
        return [words]
    total = len(text)
    candidates = []
    for k in range(1, len(words)):
        left, right = len(_text(words[:k])), len(_text(words[k:]))
        gap = max(0.0, (words[k]["start_f"] - words[k - 1]["end_f"]) / fps)
        score = gap * 10 + (0.3 if PUNCT_END.search(words[k - 1]["w"]) else 0) - abs(left - right) / total * 0.5
        candidates.append((left >= min_chars and right >= min_chars, score, k))
    pool = [c for c in candidates if c[0]] or candidates
    k = max(pool, key=lambda c: c[1])[2]
    return _split(words[:k], fps, max_chars, min_chars) + _split(words[k:], fps, max_chars, min_chars)


def build_lines(segments: list[dict[str, Any]], fps: float, max_chars: int = 42, min_chars: int = 32, pause_s: float = 0.5,
                min_dur_s: float = 0.6, gap_f: int = 1, overlap_trim_s: float = 0.3,
                seg_gap_s: float = 0.25) -> list[dict[str, Any]]:
    """Dòng phụ đề `{start_f, end_f, text, speaker}` trên một layer, không chồng nhau, sắp theo thời gian."""
    lines = []
    for utt in _utterances(segments, fps, pause_s, seg_gap_s):
        for part in _split(utt, fps, max_chars, min_chars):
            lines.append({"start_f": part[0]["start_f"], "end_f": part[-1]["end_f"], "text": _text(part),
                          "speaker": part[0]["speaker"]})
    lines.sort(key=lambda line: (line["start_f"], line["end_f"]))

    # Hai người nói chồng nhau: chồng ít thì cắt dòng trước, chồng nhiều thì gộp thành một dòng hai hàng
    merged: list[dict[str, Any]] = []
    for line in lines:
        prev = merged[-1] if merged else None
        if prev is None or line["start_f"] >= prev["end_f"]:
            merged.append(line)
            continue
        overlap = prev["end_f"] - line["start_f"]
        two_lines = "\n" not in prev["text"] and "\n" not in line["text"]
        if overlap / fps <= overlap_trim_s or prev["speaker"] == line["speaker"] or not two_lines:
            prev["end_f"] = line["start_f"]
            if prev["end_f"] <= prev["start_f"]:
                merged.pop()
                line = line | {"start_f": prev["start_f"], "text": f"{prev['text']} {line['text']}"}
            merged.append(line)
        else:
            speakers = ", ".join(dict.fromkeys(s for s in (prev["speaker"], line["speaker"]) if s))
            merged[-1] = {"start_f": prev["start_f"], "end_f": max(prev["end_f"], line["end_f"]),
                          "text": f"– {prev['text']}\n– {line['text']}", "speaker": speakers or None}

    # Dòng quá ngắn kéo dài vào khoảng lặng phía sau, không chạm dòng kế
    min_f = int(round(min_dur_s * fps))
    for i, line in enumerate(merged):
        if line["end_f"] - line["start_f"] < min_f:
            limit = merged[i + 1]["start_f"] - gap_f if i + 1 < len(merged) else line["start_f"] + min_f
            line["end_f"] = max(line["end_f"], min(line["start_f"] + min_f, limit))
    return merged


def speaker_style(companion: str | Path | None, speaker: str | None) -> dict[str, Any]:
    """Style câu đắt theo người nói: Nhan chữ trắng, người khác vàng, in hoa, không ghi tên (màu đã nói là ai);
    `<project>.contextcut/speakers.json` ghi đè theo tên (không phân biệt hoa thường)."""
    if not speaker:
        return {}
    style = {"color": DEFAULT_COLORS.get(speaker.lower(), FRIEND_COLOR), "uppercase": True, "label": False}
    file = Path(companion) / "speakers.json" if companion else None
    if file and file.exists():
        table = {k.lower(): v for k, v in json.loads(file.read_text(encoding="utf-8")).items()}
        style |= {k: v for k, v in table.get(speaker.lower(), {}).items() if k in style}
    return style


def snap_caption(op: dict[str, Any], words: list[dict[str, Any]], fps: float,
                 window_s: float = 0.4) -> tuple[dict[str, Any], dict[str, list[int]] | None]:
    """Đưa `start_f` về đầu từ gần nhất và `end_f` về cuối từ gần nhất (của cùng người nói nếu có) trong ±window_s."""
    speaker = (op.get("speaker") or "").lower()
    pool = [w for w in words if speaker and (w.get("speaker") or "").lower() == speaker] or words
    if not pool:
        return op, None
    window = int(round(window_s * fps))
    out, info = dict(op), {}
    for key, edge in (("start_f", "start_f"), ("end_f", "end_f")):
        if key not in op:
            continue
        best = min(pool, key=lambda w: abs(w[edge] - op[key]))
        if best[edge] != op[key] and abs(best[edge] - op[key]) <= window:
            out[key] = best[edge]
            info[key] = [op[key], best[edge]]
    if out.get("end_f", 1) <= out.get("start_f", 0):
        return op, None
    return out, info or None
