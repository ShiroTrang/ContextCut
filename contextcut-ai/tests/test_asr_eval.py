# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import asr_eval  # noqa: E402


def test_normalize_keeps_tones():
    assert asr_eval.normalize("Ủa, ALO… được chưa?!") == ["ủa", "alo", "được", "chưa"]
    assert asr_eval.normalize("Ừ ") == ["ừ"]


def test_wer_basic():
    assert asr_eval.wer("ủa alo được chưa", "ủa a lô được chưa") == 0.5
    assert asr_eval.wer("ủa alo", "Ủa, alo!") == 0.0
    assert asr_eval.wer("một hai ba", "") == 1.0


def test_align_words_pairs_equal_tokens():
    ref = asr_eval.normalize("ủa alo được chưa")
    hyp = asr_eval.normalize("ủa a lô được chưa")
    assert asr_eval.align_words(ref, hyp) == [(0, 0), (2, 3), (3, 4)]


def test_timing_errors_on_matched_words():
    ref = [{"w": "ủa", "start": 1.00, "end": 1.20}, {"w": "alo", "start": 1.30, "end": 1.70}]
    hyp = [{"w": "Ủa,", "start": 1.05, "end": 1.25}, {"w": "a", "start": 1.3, "end": 1.4},
           {"w": "lô", "start": 1.4, "end": 1.7}]
    errs = asr_eval.timing_errors(ref, hyp)
    assert errs["word_start_ms"] == [50] and errs["word_end_ms"] == [50] and errs["matched"] == 1


def test_line_edge_errors():
    lines = [{"start": 1.0, "end": 2.0, "words": [{"w": "ủa", "start": 1.0, "end": 1.4}, {"w": "alo", "start": 1.5, "end": 2.0}]},
             {"start": 3.0, "end": 3.5, "words": [{"w": "hả", "start": 3.0, "end": 3.5}]}]
    hyp = [{"w": "ủa", "start": 1.08, "end": 1.4}, {"w": "alo", "start": 1.5, "end": 2.12},
           {"w": "hả", "start": 2.95, "end": 3.47}]
    errs = asr_eval.line_errors(lines, hyp)
    assert errs["line_start_ms"] == [80, 50] and errs["line_end_ms"] == [120, 30]


def test_summary_median_p90():
    s = asr_eval.summarize([10, 20, 30, 40, 1000])
    assert s == {"n": 5, "median": 30, "p90": 616, "mean": 220}
    assert asr_eval.summarize([]) == {"n": 0, "median": None, "p90": None, "mean": None}


def test_reference_window_and_words(tmp_path):
    cal = {"format": "lyric-calibration/1", "lines": [
        {"text": "Một hai", "start": 10.0, "end": 11.0, "words": [{"w": "Một", "start": 10.0, "end": 10.5, "source": "tap"},
                                                                {"w": "hai", "start": 10.5, "end": 11.0, "source": "tap"}]},
        {"text": "ba", "start": 12.0, "end": 12.4, "words": [{"w": "ba", "start": 12.0, "end": 12.4, "source": "auto"}]}]}
    ref = asr_eval.reference(cal, tapped_only=True)
    assert [w["w"] for w in ref["words"]] == ["Một", "hai"] and ref["window"] == (10.0, 11.0)
    assert len(asr_eval.reference(cal, tapped_only=False)["lines"]) == 2
    with pytest.raises(ValueError):
        asr_eval.reference({"format": "khác"}, tapped_only=True)
