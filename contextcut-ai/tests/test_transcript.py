# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
from contextcut_ai import transcript

FPS = 10.0  # 1 frame = 0,1 s cho dễ tính


def word(w, start, end, p=0.9):
    return {"w": w, "start": start, "end": end, "p": p}


TR = {"schema": "contextcut-transcript/1", "language": "vi", "model": "large-v3",
      "segments": [{"track": 2, "speaker": "Nhan", "start": 1.0, "end": 3.5, "text": "A, b c.", "flags": [],
                    "words": [word("A,", 1.0, 1.5), word("b", 2.0, 2.5, 0.2), word("c.", 3.0, 3.5)]},
                   {"track": 3, "speaker": "bạn bè", "start": 5.0, "end": 5.5, "text": "Ừ", "flags": [],
                    "words": [word("Ừ", 5.0, 5.5)]}]}


def clip(cid, start_f, src_in_f, src_out_f, source="4", content="audio", linked=None, speed=1.0):
    return {"id": cid, "kind": "clip", "source": source, "start_f": start_f, "end_f": start_f + src_out_f - src_in_f,
            "src_in_f": src_in_f, "src_out_f": src_out_f, "content": content, "linked": linked, "speed": speed}


def frames(segs):
    return [(s["text"], s["start_f"], s["end_f"], [(w["w"], w["start_f"], w["end_f"]) for w in s["words"]]) for s in segs]


def test_maps_trimmed_clip_only_visible_words():
    places = transcript.placements([clip(1, 100, 18, 33)], "4")
    [seg] = transcript.on_timeline(TR, places, FPS, "4")
    assert frames([seg]) == [("b c.", 102, 115, [("b", 102, 107), ("c.", 112, 115)])]
    assert seg["partial"] is True and seg["speaker"] == "Nhan" and seg["track"] == 2 and seg["recording"] == "4"


def test_cut_range_gap_drops_words():
    places = transcript.placements([clip(1, 0, 0, 22), clip(2, 22, 28, 60)], "4")
    segs = transcript.on_timeline(TR, places, FPS, "4")
    assert frames(segs) == [("A, b", 10, 22, [("A,", 10, 15), ("b", 20, 22)]),
                            ("c.", 24, 29, [("c.", 24, 29)]),
                            ("Ừ", 44, 49, [("Ừ", 44, 49)])]


def test_duplicate_clip_repeats_words():
    places = transcript.placements([clip(1, 0, 0, 40), clip(2, 100, 0, 40)], "4")
    segs = transcript.on_timeline(TR, places, FPS, "4")
    assert [s["start_f"] for s in segs] == [10, 110]
    assert segs[0]["partial"] is False and segs[0]["text"] == "A, b c."


def test_linked_av_not_duplicated():
    items = [clip(1, 0, 0, 60, content="video", linked=2), clip(2, 0, 0, 60, linked=1),
             clip(3, 0, 0, 60, content="audio"), clip(9, 0, 0, 60, source="7"),
             clip(5, 200, 0, 60, speed=2.0)]
    places = transcript.placements(items, "4")
    assert places == [transcript.Placement(0, 0, 60)]


def test_source_mode_frames():
    segs = transcript.on_source(TR, FPS, "4")
    assert frames(segs)[0] == ("A, b c.", 10, 35, [("A,", 10, 15), ("b", 20, 25), ("c.", 30, 35)])
    assert segs[1]["start_f"] == 50


def test_timecode():
    assert transcript.timecode(0, 60) == "00:00.00"
    assert transcript.timecode(3725, 60) == "01:02.05"
    assert transcript.timecode(60 * 3600 + 30, 60) == "1:00:00.30"


def test_contiguous_pieces_merge():
    # zoom cắt clip ở frame 23 (giữa từ "b") và 40: ba mảnh liền nhau cả trên timeline lẫn trong nguồn = một đoạn
    items = [clip(1, 0, 0, 23, content="video", linked=4), clip(2, 23, 23, 40, content="video", linked=5),
             clip(3, 40, 40, 60, content="video", linked=6),
             clip(4, 0, 0, 23, linked=1), clip(5, 23, 23, 40, linked=2), clip(6, 40, 40, 60, linked=3)]
    places = transcript.placements(items, "4")
    assert places == [transcript.Placement(0, 0, 60)]
    segs = transcript.on_timeline(TR, places, FPS, "4")
    assert [(s["text"], s["partial"]) for s in segs] == [("A, b c.", False), ("Ừ", False)]
    # nối liền trên timeline nhưng nhảy trong nguồn (đã cắt bỏ một đoạn) thì không gộp
    assert len(transcript.placements([clip(1, 0, 0, 22), clip(2, 22, 28, 60)], "4")) == 2
