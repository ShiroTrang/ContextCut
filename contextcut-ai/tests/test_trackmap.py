# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import make_obs_mkv  # noqa: E402

from contextcut_ai import paths, trackmap  # noqa: E402
from contextcut_ai.media import AudioStream  # noqa: E402


def streams(*titles: str) -> list[AudioStream]:
    return [AudioStream(index=i + 1, title=t, channels=2 if i == 0 else 1, sample_rate=48000, codec="aac")
            for i, t in enumerate(titles)]


def roles(entries):
    return [e["role"] for e in entries]


def test_default_map_obs_order():
    m = trackmap.default_map(streams("Track1", "Track2", "Track3", "Track4", "Track5"))
    assert roles(m) == ["mix", "mic", "discord", "game", "desktop"]
    assert [e["speaker"] for e in m] == [None, "Nhan", "bạn bè", None, None]
    assert [e["transcribe"] for e in m] == [False, True, True, False, False]
    assert [e["obs_track"] for e in m] == [1, 2, 3, 4, 5]
    assert [e["index"] for e in m] == [1, 2, 3, 4, 5]


def test_default_map_titles_win():
    m = trackmap.default_map(streams("Track1", "Discord", "Mic", "Tiếng game", "Track5"))
    assert roles(m) == ["mix", "discord", "mic", "game", "desktop"]
    assert m[2]["speaker"] == "Nhan" and m[1]["speaker"] == "bạn bè"


def test_default_map_vietnamese_titles():
    m = trackmap.default_map(streams("Trộn chung", "Giọng Nhan", "Bạn bè"))
    assert roles(m) == ["mix", "mic", "discord"]


def test_extra_streams_are_other():
    m = trackmap.default_map(streams(*[f"Track{i}" for i in range(1, 7)]))
    assert roles(m)[5] == "other" and m[5]["transcribe"] is False


def test_single_stream_is_mix_and_transcribed():
    [e] = trackmap.default_map(streams("Track1"))
    assert e["role"] == "mix" and e["transcribe"] is True and e["speaker"] is None


def test_two_streams_mix_and_mic():
    m = trackmap.default_map(streams("Track1", "Track2"))
    assert roles(m) == ["mix", "mic"]
    assert [e["transcribe"] for e in m] == [False, True]


def test_companion_dir_unsaved_raises():
    with pytest.raises(paths.ProjectNotSaved) as e:
        paths.companion_dir({"project": {"path": None, "companion_dir": None}})
    assert "Lưu project trước" in str(e.value)


def test_companion_dir_from_state(tmp_path):
    d = tmp_path / "Bắt Nạt.contextcut"
    assert paths.companion_dir({"project": {"path": "x", "companion_dir": d.as_posix()}}) == d


@pytest.fixture(scope="module")
def obs_mkv(tmp_path_factory) -> Path:
    return make_obs_mkv(tmp_path_factory.mktemp("rec") / "Ông Sang 21-00-00.mkv", seconds=3)


def test_store_ensure_writes_recordings_json(obs_mkv, tmp_path):
    store = trackmap.RecordingStore(tmp_path / "P.contextcut")
    assert store.get("4") is None
    rec = store.ensure("4", obs_mkv)
    assert rec["path"] == obs_mkv.as_posix() and len(rec["file_hash"]) == 16
    assert roles(rec["track_map"]) == ["mix", "mic", "discord", "game", "desktop"]
    data = json.loads((tmp_path / "P.contextcut" / "recordings.json").read_text(encoding="utf-8"))
    assert data["schema"] == 1 and data["recordings"]["4"]["file_hash"] == rec["file_hash"]
    assert trackmap.RecordingStore(tmp_path / "P.contextcut").get("4") == rec


def test_store_keeps_user_map_until_file_changes(obs_mkv, tmp_path):
    store = trackmap.RecordingStore(tmp_path / "P.contextcut")
    store.ensure("4", obs_mkv)
    store.set_track_map("4", [{"index": 1, "role": "mix"}, {"index": 2, "role": "discord", "speaker": "Sang"}])
    rec = store.ensure("4", obs_mkv)
    assert roles(rec["track_map"]) == ["mix", "discord"]
    assert rec["track_map"][0]["transcribe"] is False  # đã có track giọng thì không phiên âm track trộn
    assert rec["track_map"][1] | {} == {"index": 2, "obs_track": 2, "title": "Track2", "channels": 1, "role": "discord",
                                        "speaker": "Sang", "transcribe": True}


def test_set_track_map_rejects_unknown_index(obs_mkv, tmp_path):
    store = trackmap.RecordingStore(tmp_path / "P.contextcut")
    store.ensure("4", obs_mkv)
    with pytest.raises(ValueError, match="index 9"):
        store.set_track_map("4", [{"index": 9, "role": "mic"}])
    with pytest.raises(ValueError, match="role"):
        store.set_track_map("4", [{"index": 2, "role": "giọng"}])
    with pytest.raises(KeyError):
        store.set_track_map("7", [{"index": 2, "role": "mic"}])
