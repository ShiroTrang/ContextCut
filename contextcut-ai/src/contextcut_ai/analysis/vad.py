# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Tìm đoạn có tiếng nói và chia audio dài thành chunk để phiên âm chạy tiếp được khi bị ngắt."""

from __future__ import annotations

import math

import numpy as np

from . import refine


def energy_regions(audio: np.ndarray, sr: int = 16000, margin_db: float = 12.0, min_speech_s: float = 0.15,
                   min_silence_s: float = 0.3) -> list[tuple[float, float]]:
    """Đoạn có năng lượng vượt nền ồn + `margin_db`: dự phòng khi không có Silero, và cho tín hiệu thử."""
    env = refine.envelope(audio, sr)
    if len(env) == 0:
        return []
    voiced = env >= float(np.percentile(env, 10)) + margin_db
    regions: list[list[float]] = []
    start = None
    for j, v in enumerate(np.append(voiced, False)):
        if v and start is None:
            start = j
        elif not v and start is not None:
            a, b = start * refine.HOP_S, j * refine.HOP_S
            if regions and a - regions[-1][1] < min_silence_s:
                regions[-1][1] = b
            else:
                regions.append([a, b])
            start = None
    return [(round(a, 3), round(b, 3)) for a, b in regions if b - a >= min_speech_s]


def silero_regions(audio: np.ndarray, sr: int = 16000) -> list[tuple[float, float]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    stamps = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=500, speech_pad_ms=200), sampling_rate=sr)
    return [(round(s["start"] / sr, 3), round(s["end"] / sr, 3)) for s in stamps]


def speech_regions(audio: np.ndarray, sr: int = 16000, method: str = "silero") -> list[tuple[float, float]]:
    if method == "silero":
        try:
            return silero_regions(audio, sr)
        except ImportError:
            pass
    return energy_regions(audio, sr)


def plan_chunks(regions: list[tuple[float, float]], max_chunk_s: float = 300.0,
                pad_s: float = 0.4) -> list[tuple[float, float]]:
    """Gom các đoạn có tiếng thành chunk ≤ `max_chunk_s`, cắt ở khoảng lặng dài nhất; một đoạn nói liền dài hơn thì
    chia đều."""
    padded = [(max(0.0, round(a - pad_s, 3)), round(b + pad_s, 3)) for a, b in regions]

    def split(group: list[tuple[float, float]]) -> list[tuple[float, float]]:
        span = (group[0][0], group[-1][1])
        if span[1] - span[0] <= max_chunk_s:
            return [span]
        if len(group) == 1:
            parts = math.ceil((span[1] - span[0]) / max_chunk_s)
            step = (span[1] - span[0]) / parts
            edges = [round(span[0] + i * step, 3) for i in range(parts)] + [span[1]]
            return list(zip(edges[:-1], edges[1:], strict=True))
        gaps = [group[i + 1][0] - group[i][1] for i in range(len(group) - 1)]
        cut = int(np.argmax(gaps)) + 1
        return split(group[:cut]) + split(group[cut:])

    return split(padded) if padded else []
