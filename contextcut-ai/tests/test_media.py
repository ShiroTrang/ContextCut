# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from p2_fixture import make_obs_mkv  # noqa: E402

from contextcut_ai import media, paths  # noqa: E402

NAMED = ("Mix", "Mic", "Discord", "Game", "Desktop")


@pytest.fixture(scope="module")
def obs_mkv(tmp_path_factory) -> Path:
    return make_obs_mkv(tmp_path_factory.mktemp("rec") / "Bắt Nạt Hải Sản 02-24-56.mkv", titles=NAMED)


def test_find_tool_finds_ffprobe():
    assert Path(paths.find_tool("ffprobe")).name.lower().startswith("ffprobe")


def test_find_tool_missing_raises(monkeypatch):
    with pytest.raises(paths.ToolMissing):
        paths.find_tool("khong-co-cong-cu-nay")


def test_probe_fixture_unicode_path(obs_mkv):
    probe = media.probe(obs_mkv)
    assert probe.has_video
    assert abs(probe.duration_s - 8) < 0.3
    assert [s.index for s in probe.streams] == [1, 2, 3, 4, 5]
    assert [s.title for s in probe.streams] == list(NAMED)
    assert [s.channels for s in probe.streams] == [2, 1, 1, 1, 1]
    assert probe.streams[0].sample_rate == 48000


def test_fast_hash_stable(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(bytes(range(256)) * 20000)
    h = media.fast_hash(f)
    assert len(h) == 16 and h == media.fast_hash(f)
    data = bytearray(f.read_bytes())
    data[-1] ^= 0xFF
    f.write_bytes(bytes(data))
    assert media.fast_hash(f) != h


def test_extract_audio_16k_mono(obs_mkv, tmp_path):
    out = media.extract_audio(obs_mkv, 2, tmp_path / "mic.wav")
    with wave.open(str(out)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert abs(w.getnframes() / 16000 - 8) < 0.1
    part = media.extract_audio(obs_mkv, 3, tmp_path / "discord.wav", start_s=2, end_s=5)
    with wave.open(str(part)) as w:
        assert abs(w.getnframes() / 16000 - 3) < 0.05
