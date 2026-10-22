# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import make_calibration  # noqa: E402


def seg(text, gaps=None):
    words = text.split()
    t, out = 0.0, []
    for i, w in enumerate(words):
        t += (gaps or {}).get(i, 0.0)
        out.append({"w": w, "start": t, "end": t + 0.3})
        t += 0.3
    return {"text": text, "words": out}


def test_draft_lines_split_long_segments_at_pauses():
    s = seg("một hai ba bốn năm sáu bảy tám chín mười mười_một mười_hai mười_ba mười_bốn", gaps={6: 0.8})
    assert make_calibration.draft_lines([s], max_words=10) == [
        "một hai ba bốn năm sáu", "bảy tám chín mười mười_một mười_hai mười_ba mười_bốn"]


def test_draft_lines_keeps_short_segments():
    assert make_calibration.draft_lines([seg("Ủa alo?"), seg("Nghe nè.")]) == ["Ủa alo?", "Nghe nè."]
