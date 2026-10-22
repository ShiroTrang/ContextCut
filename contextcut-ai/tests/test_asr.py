# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Backend ASR thật: cần extra `analysis` (và model trong cache); tự bỏ qua khi thiếu."""
import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("huggingface_hub")

from contextcut_ai.analysis import asr, gpu  # noqa: E402


def test_model_missing_message_has_size(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTCUT_MODELS", str(tmp_path / "models"))
    with pytest.raises(asr.ModelMissing) as e:
        asr.MODELS["phowhisper-large"].locate(allow_download=False)
    assert "3,1 GB" in str(e.value) and "convert_phowhisper" in str(e.value)
    info = asr.ModelInfo("thu", "ctranslate2", 1.2, repo="nvidia/khong-co-model-nay-2026")
    with pytest.raises(asr.ModelMissing) as e:
        info.locate(allow_download=False)
    assert "1,2 GB" in str(e.value) and "allow_download" in str(e.value)


def test_unknown_model_lists_choices():
    with pytest.raises(ValueError) as e:
        asr.load("whisper-tiny-xyz")
    assert "large-v3" in str(e.value) and "parakeet-ctc-vi" in str(e.value)


def test_vram_monitor_reports_peak():
    with gpu.VramMonitor(interval_s=0.05) as mon:
        pass
    if mon.peak_mib is None:
        pytest.skip("không có NVML (máy không có GPU NVIDIA)")
    assert mon.baseline_mib > 0 and mon.peak_mib >= mon.baseline_mib and mon.total_mib >= mon.peak_mib


@pytest.fixture(scope="module")
def large_v3():
    try:
        backend = asr.load("large-v3")
    except (asr.ModelMissing, asr.EngineMissing) as e:
        pytest.skip(str(e))
    yield backend
    backend.close()


def test_large_v3_transcribes_silence_as_nothing(large_v3):
    assert large_v3.transcribe(np.zeros(16000 * 3, dtype=np.float32), "vi", None) == []


def test_parakeet_punctuation_joined():
    assert asr.join_punctuation("ngời , Bối rối , tâm trí tôi ?") == "ngời, Bối rối, tâm trí tôi?"
    assert asr.join_punctuation("ngời ,") == "ngời,"
