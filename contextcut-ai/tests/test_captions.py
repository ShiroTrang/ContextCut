# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json

from contextcut_ai import captions

FPS = 50.0  # 1 frame = 20 ms


def seg(speaker, words, track=2):
    """words: [(chữ, giây đầu, giây cuối)] → câu đã ở frame timeline (như transcript.on_timeline)."""
    ws = [{"w": w, "start": a, "end": b, "start_f": round(a * FPS), "end_f": round(b * FPS), "p": 0.9} for w, a, b in words]
    return {"recording": "4", "track": track, "speaker": speaker, "start_f": ws[0]["start_f"], "end_f": ws[-1]["end_f"],
            "text": " ".join(w for w, _, _ in words), "words": ws, "partial": False, "flags": []}


def run_words(text, start, step=0.3, pause_at=None, pause=0.0):
    out, t = [], start
    for i, w in enumerate(text.split()):
        if i == pause_at:
            t += pause
        out.append((w, round(t, 3), round(t + step - 0.05, 3)))
        t += step
    return out


def test_lines_respect_max_chars_and_pauses():
    text = "thôi xong rồi tụi mày ơi nó nổ tung cái nhà của tao rồi kìa trời ơi là trời luôn đó chạy đi chạy mau"
    words = run_words(text, 1.0, pause_at=11, pause=0.7)
    lines = captions.build_lines([seg("Nhan", words)], FPS)
    assert all(len(line["text"]) <= 42 for line in lines)
    joined = " ".join(line["text"] for line in lines)
    assert joined == text
    # khoảng nghỉ 0,7 s nằm trước từ thứ 12 ("của"): luôn có một dòng bắt đầu đúng ở đó
    assert any(line["text"].startswith("của tao") for line in lines)


def test_line_splits_prefer_pause_then_punctuation():
    text = "ủa alo nghe không, tao đang ở dưới hầm mỏ nè mày xuống đây"
    words = run_words(text, 0.0, pause_at=4, pause=0.25)
    [first, second] = captions.build_lines([seg("Nhan", words)], FPS, max_chars=42)
    assert first["text"] == "ủa alo nghe không," and second["text"].startswith("tao đang")


def test_line_times_are_word_edges():
    words = [("Ủa", 1.0, 1.2), ("alo?", 1.25, 1.6)]
    [line] = captions.build_lines([seg("Nhan", words)], FPS)
    assert (line["start_f"], line["end_f"], line["text"], line["speaker"]) == (50, 80, "Ủa alo?", "Nhan")


def test_min_duration_extends_into_silence_only():
    a = seg("Nhan", [("Ừ", 1.0, 1.2)])
    b = seg("Nhan", [("Đi", 1.5, 1.8), ("thôi", 1.8, 2.2)])
    l1, l2 = captions.build_lines([a, b], FPS, min_dur_s=0.6)
    assert l1["start_f"] == 50 and l1["end_f"] == 74  # muốn tới 80 nhưng dòng sau bắt đầu ở 75 (cách 1 frame)
    assert l2["end_f"] == 110
    [solo] = captions.build_lines([a], FPS, min_dur_s=0.6)
    assert solo["end_f"] == 80


def test_overlap_merge_and_trim():
    nhan = seg("Nhan", [("Chạy", 1.0, 1.3), ("đi", 1.3, 2.0)])
    short = seg("bạn bè", [("Ờ", 1.9, 2.3)], track=3)  # chồng 0,1 s → cắt dòng trước
    lines = captions.build_lines([nhan, short], FPS)
    assert [(l["start_f"], l["end_f"], l["text"]) for l in lines] == [(50, 95, "Chạy đi"), (95, 125, "Ờ")]  # "Ờ" kéo tới 0,6 s
    long = seg("bạn bè", [("Đợi", 1.2, 1.6), ("tao", 1.6, 2.4)], track=3)  # chồng 0,8 s → gộp hai hàng
    [merged] = captions.build_lines([nhan, long], FPS)
    assert merged["text"] == "– Chạy đi\n– Đợi tao" and (merged["start_f"], merged["end_f"]) == (50, 120)
    assert merged["speaker"] == "Nhan, bạn bè"


def test_lines_never_overlap():
    segs = [seg("Nhan", run_words("một hai ba bốn năm sáu bảy tám", 0.0)),
            seg("bạn bè", run_words("chín mười mười một", 0.4), track=3),
            seg("Nhan", run_words("mười hai mười ba", 1.0))]
    lines = captions.build_lines(segs, FPS)
    for a, b in zip(lines, lines[1:]):
        assert a["end_f"] <= b["start_f"] and a["start_f"] < a["end_f"]


def test_speaker_style_defaults_and_override(tmp_path):
    assert captions.speaker_style(tmp_path, "Nhan") == {"color": "#FFFFFF", "uppercase": True, "label": False}
    assert captions.speaker_style(tmp_path, "bạn bè")["color"] == "#FFD400"
    assert captions.speaker_style(tmp_path, None) == {}
    (tmp_path / "speakers.json").write_text(json.dumps({"Sang": {"color": "#00E5FF", "label": True}}), encoding="utf-8")
    assert captions.speaker_style(tmp_path, "sang") == {"color": "#00E5FF", "uppercase": True, "label": True}


def test_snap_caption_within_window():
    words = seg("Nhan", [("Ủa", 1.0, 1.2), ("alo", 1.3, 1.6)])["words"]
    for w in words:
        w["speaker"] = "Nhan"
    op = {"type": "caption", "text": "Ủa alo", "speaker": "Nhan", "start_f": 45, "end_f": 90}
    snapped, info = captions.snap_caption(op, words, FPS)
    assert (snapped["start_f"], snapped["end_f"]) == (50, 80) and info == {"start_f": [45, 50], "end_f": [90, 80]}
    far = {"type": "caption", "text": "x", "start_f": 10, "end_f": 20}
    same, info = captions.snap_caption(far, words, FPS)
    assert same == far and info is None


def test_split_prefers_asr_segment_boundary():
    # hai câu ASR dính nhau (không nghỉ), gộp lại 43 ký tự: ngắt đúng chỗ câu mới bắt đầu, không ngắt giữa câu sau
    a = seg("Nhan", [("4", 9.0, 9.2), ("sợi", 9.2, 9.4), ("dây", 9.4, 9.69)])
    b = seg("Nhan", [(w, 9.69 + i * 0.2, 9.69 + (i + 1) * 0.2) for i, w in enumerate("Thằng mù nó đang chịu vô đâu vậy?".split())])
    lines = captions.build_lines([a, b], FPS)
    assert [l["text"] for l in lines] == ["4 sợi dây", "Thằng mù nó đang chịu vô đâu vậy?"]
