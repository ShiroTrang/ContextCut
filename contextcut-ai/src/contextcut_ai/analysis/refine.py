# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Tinh chỉnh ranh giới lời nói bằng năng lượng trên track sạch (Mic/Discord riêng của OBS).

Timestamp từ của Whisper hay lệch 100–300 ms ở đầu câu và kéo cuối câu vào khoảng lặng. Track Mic chỉ có giọng một
người, nên chỗ bắt đầu/hết nói là chỗ năng lượng vượt/xuống dưới nền ồn: đưa đầu và cuối câu về đó (trong ±0,3 s).
"""

from __future__ import annotations

import numpy as np

HOP_S = 0.01
WIN_S = 0.02


def envelope(audio: np.ndarray, sr: int = 16000, hop_s: float = HOP_S, win_s: float = WIN_S) -> np.ndarray:
    """Mức RMS (dBFS) mỗi `hop_s`; khung j căn giữa tại j·hop_s."""
    hop, win = int(sr * hop_s), int(sr * win_s)
    padded = np.pad(audio.astype(np.float32), (win // 2, win // 2))
    n = len(audio) // hop
    squares = np.concatenate(([0.0], np.cumsum(padded.astype(np.float64) ** 2)))
    idx = np.arange(n) * hop
    rms = np.sqrt((squares[idx + win] - squares[idx]) / win)
    return (20 * np.log10(rms + 1e-9)).astype(np.float32)


def refine_edges(env: np.ndarray, start: float, end: float, window_s: float = 0.3, hop_s: float = HOP_S,
                 margin_db: float = 12.0, floor_s: float = 5.0) -> tuple[float, float]:
    """Đưa `start` về chỗ bắt đầu có tiếng và `end` về chỗ hết tiếng gần nhất trong ±`window_s`; không thấy ranh giới
    rõ (tiếng liên tục, nền ồn quá to) thì giữ nguyên."""
    n = len(env)
    if n == 0:
        return start, end
    w = int(round(window_s / hop_s))
    mid = min(n - 1, max(0, int(round((start + end) / 2 / hop_s))))
    lo, hi = max(0, mid - int(floor_s / hop_s)), min(n, mid + int(floor_s / hop_s))
    local = env[lo:hi]
    floor = float(np.percentile(local, 10))
    if float(np.percentile(local, 95)) - floor < margin_db:
        return start, end
    voiced = env >= floor + margin_db

    i0 = min(n - 1, max(0, int(round(start / hop_s))))
    onset = None
    if voiced[i0]:
        j = i0
        while j > max(0, i0 - w) and voiced[j - 1]:
            j -= 1
        if j > max(0, i0 - w) or j == 0:
            onset = j
    else:
        for j in range(i0, min(n, i0 + w + 1)):
            if voiced[j]:
                onset = j
                break

    k0 = min(n - 1, max(0, int(round(end / hop_s)) - 1))
    offset = None
    if voiced[k0]:
        k = k0
        while k < min(n - 1, k0 + w) and voiced[k + 1]:
            k += 1
        if k < min(n - 1, k0 + w) or k == n - 1:
            offset = k
    else:
        for k in range(k0, max(-1, k0 - w - 1), -1):
            if voiced[k]:
                offset = k
                break

    new_start = round(onset * hop_s, 3) if onset is not None else start
    new_end = round(offset * hop_s, 3) if offset is not None else end
    if new_end <= new_start:
        return start, end
    return new_start, new_end
