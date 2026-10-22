# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
from contextcut_ai import guide

EXPECTED = ["workflow", "editing-rules", "software", "styles/gaming", "patterns/irony-cut", "patterns/meanwhile",
            "patterns/beat-montage", "patterns/reaction-zoom", "patterns/subtitles"]


def test_expected_topics():
    names = [t.name for t in guide.load_topics()]
    assert sorted(names) == sorted(EXPECTED)
    assert names[:3] == ["workflow", "editing-rules", "software"]


def test_every_topic_has_front_matter():
    for t in guide.load_topics():
        assert t.title and t.summary, t.name
        assert t.body.startswith("# "), t.name
        assert "\r" not in t.body


def test_find_topic_aliases():
    assert guide.find_topic("styles/gaming").name == "styles/gaming"
    assert guide.find_topic("gaming").name == "styles/gaming"
    assert guide.find_topic("gaming.md").name == "styles/gaming"
    assert guide.find_topic(" Patterns/Irony-Cut ").name == "patterns/irony-cut"
    assert guide.find_topic("irony-cut").name == "patterns/irony-cut"
    assert guide.find_topic("nope") is None


def test_editing_rules_cover_design_8_6():
    body = guide.find_topic("editing-rules").body
    for phrase in ["Chỉ chuyển khi có lý do", "trọn vẹn", "Nhân trước, quả sau", "Trong lúc đó:", "1,5 giây",
                   "giữa một từ", "Không bịa", "lố", "hạn mức"]:
        assert phrase in body, phrase


def test_software_explains_frames():
    body = guide.find_topic("software").body
    for phrase in ["[start_f, end_f)", "base_revision", "stale_cursor", "frame × den / num", "linked"]:
        assert phrase in body, phrase


def test_instructions_short():
    text = guide.instructions()
    assert len(text) <= 1500
    assert "get_guide" in text and "Mở ContextCut trước" in text
    assert not text.startswith("---")


def test_index_lists_all_topics():
    index = guide.index_text()
    for name in EXPECTED:
        assert f"- {name}:" in index


def test_guide_dir_env_override(tmp_path, monkeypatch):
    (tmp_path / "instructions.md").write_text("Ngắn.\n", encoding="utf-8")
    (tmp_path / "x.md").write_bytes("---\r\ntitle: X\r\nsummary: s\r\n---\r\n# X\r\nthân\r\n".encode())
    monkeypatch.setenv("CONTEXTCUT_GUIDE_DIR", str(tmp_path))
    [topic] = guide.load_topics()
    assert (topic.name, topic.title, topic.summary, topic.body) == ("x", "X", "s", "# X\nthân\n")
    assert guide.instructions() == "Ngắn."


def test_guide_covers_transcripts_and_subtitles():
    instructions = guide.instructions()
    for phrase in ["get_transcript", "add_subtitles"]:
        assert phrase in instructions, phrase
    assert "Chưa nghe lời thoại" not in instructions
    workflow = guide.find_topic("workflow").body
    for phrase in ["transcribe", "get_job", "get_transcript", "add_subtitles", "dung lượng"]:
        assert phrase in workflow, phrase
    software = guide.find_topic("software").body
    for phrase in ["track_map", "clear_subtitles", "uppercase", "speakers.json", "Lưu project trước", "on=\"source\""]:
        assert phrase in software, phrase
