# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Backend nhận dạng giọng nói: Whisper qua CTranslate2 (large-v3, PhoWhisper đã chuyển) và Parakeet CTC qua NeMo.

Mọi backend nhận audio mono 16 kHz float32 và trả `Segment` có từng từ (giây tính từ đầu đoạn audio đưa vào).
Model chỉ nạp từ cache khi chưa được phép tải; thiếu thì `ModelMissing` nói tên, dung lượng và cách lấy.
"""

from __future__ import annotations

import gc
import importlib.util
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..paths import models_dir

SAMPLE_RATE = 16000
DEFAULT_MODEL = "large-v3"  # khi không model nào có sẵn (transcribe báo thiếu model kèm dung lượng)
# Thứ tự ưu tiên theo số đo (docs/measurements/P2a-asr.md): tạm theo bộ bài hát SongMV, chốt lại trên bản ghi của Nhan
PREFERENCE = ("parakeet-ctc-vi", "phowhisper-large", "large-v3")


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float | None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


def join_punctuation(text: str) -> str:
    """Parakeet tách dấu câu thành token riêng ("ngời , Bối"): dính lại vào chữ trước."""
    return re.sub(r"\s+([,.!?;:…])", r"\1", text).strip()


def gb(size: float) -> str:
    return f"{size:.1f}".replace(".", ",") + " GB"


class ModelMissing(Exception):
    def __init__(self, name: str, size_gb: float, how: str):
        self.name, self.size_gb, self.how = name, size_gb, how
        super().__init__(f"Chưa có model {name} ({gb(size_gb)}) trên máy. {how}")


class EngineMissing(Exception):
    def __init__(self, extra: str, detail: str):
        super().__init__(f"Thiếu thư viện cho model này ({detail}). Cài: uv sync --directory contextcut-ai "
                         f"--extra {extra} (tải thư viện lớn; hỏi người dùng trước).")


@dataclass(frozen=True)
class ModelInfo:
    name: str
    engine: str  # "ctranslate2" | "nemo"
    size_gb: float
    repo: str | None = None  # repo HuggingFace chính thức
    filename: str | None = None  # một file trong repo (NeMo) thay vì cả repo
    local: str | None = None  # thư mục trong models_dir() (model chuyển tại máy)
    how: str = ""

    def locate(self, allow_download: bool = False) -> str:
        if self.local:
            path = models_dir() / self.local
            if (path / "model.bin").exists():
                return str(path)
            raise ModelMissing(self.name, self.size_gb, self.how)
        from huggingface_hub import hf_hub_download, snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
        try:
            if self.filename:
                return hf_hub_download(self.repo, self.filename, local_files_only=not allow_download)
            return snapshot_download(self.repo, local_files_only=not allow_download)
        except (LocalEntryNotFoundError, FileNotFoundError, OSError) as e:
            if allow_download:
                raise
            raise ModelMissing(self.name, self.size_gb,
                               f"Tải từ HuggingFace {self.repo} bằng transcribe(..., allow_download=true) sau khi "
                               "người dùng đồng ý.") from e


MODELS: dict[str, ModelInfo] = {
    "large-v3": ModelInfo("large-v3", "ctranslate2", 3.1, repo="Systran/faster-whisper-large-v3"),
    "phowhisper-large": ModelInfo(
        "phowhisper-large", "ctranslate2", 3.1, local="phowhisper-large-ct2",
        how="Chuyển một lần tại máy từ vinai/PhoWhisper-large (6,2 GB trong cache HuggingFace): "
            "uv run --directory contextcut-ai --extra analysis --extra parakeet --with transformers "
            "python tools/convert_phowhisper.py"),
    "parakeet-ctc-vi": ModelInfo("parakeet-ctc-vi", "nemo", 2.6, repo="nvidia/parakeet-ctc-0.6b-Vietnamese",
                                 filename="parakeet-ctc-0.6b-vi.nemo"),
}


class Backend(Protocol):
    name: str
    device: str
    max_chunk_s: float

    def transcribe(self, audio: Any, language: str, prompt: str | None) -> list[Segment]: ...

    def close(self) -> None: ...


def _cuda_available_ct2() -> bool:
    import ctranslate2
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 — thiếu DLL CUDA: coi như không có GPU
        return False


class FasterWhisperBackend:
    max_chunk_s = 300.0

    def __init__(self, name: str, path: str, device: str):
        from . import gpu
        gpu.add_cuda_dll_dirs()
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise EngineMissing("analysis", "faster-whisper") from e
        if device == "auto":
            device = "cuda" if _cuda_available_ct2() else "cpu"
        compute = "int8_float16" if device == "cuda" else "int8"
        self.name, self.device, self.compute_type = name, device, compute
        # Bản fine-tune (PhoWhisper) không sinh token timestamp đáng tin: giải mã không timestamp, mốc từ vẫn lấy
        # từ alignment heads (DTW)
        self._without_timestamps = name != "large-v3"
        self._model = WhisperModel(path, device=device, compute_type=compute)

    def transcribe(self, audio: Any, language: str, prompt: str | None) -> list[Segment]:
        segments, _ = self._model.transcribe(
            audio, language=language, task="transcribe", beam_size=5, word_timestamps=True, vad_filter=True,
            condition_on_previous_text=False, initial_prompt=prompt, without_timestamps=self._without_timestamps)
        out = []
        for s in segments:
            words = [Word(w.word.strip(), round(w.start, 3), round(w.end, 3), round(w.probability, 3))
                     for w in (s.words or []) if w.word.strip()]
            out.append(Segment(round(s.start, 3), round(s.end, 3), s.text.strip(), words, s.avg_logprob,
                               s.no_speech_prob))
        return out

    def close(self) -> None:
        del self._model
        gc.collect()


class ParakeetBackend:
    max_chunk_s = 120.0  # FastConformer chú ý toàn cục: bộ nhớ tăng theo bình phương độ dài đoạn

    def __init__(self, name: str, path: str, device: str):
        try:
            import torch
            from nemo.collections.asr.models import ASRModel
        except ImportError as e:
            raise EngineMissing("parakeet", "nemo_toolkit[asr] + torch") from e
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.name, self.device = name, device
        self._torch = torch
        # Nạp lên CPU rồi mới chuyển: restore_from(map_location="cuda") giữ hai bản trọng số trên GPU (4,7 GB thay vì
        # 2,4 GB), card 6 GB tràn sang RAM chung và chạy chậm hàng trăm lần (đo 22/10/2026)
        self._model = ASRModel.restore_from(path, map_location="cpu").eval().to(device)

    def transcribe(self, audio: Any, language: str, prompt: str | None) -> list[Segment]:
        with self._torch.inference_mode():
            [hyp] = self._model.transcribe([audio], batch_size=1, timestamps=True, verbose=False)
        stamps = getattr(hyp, "timestamp", None) or {}
        words = [Word(join_punctuation(w["word"]), round(float(w["start"]), 3), round(float(w["end"]), 3), None)
                 for w in stamps.get("word", []) if w.get("word", "").strip()]
        # Dấu câu đứng riêng thành "từ": nhập vào từ trước
        merged: list[Word] = []
        for w in words:
            if merged and re.fullmatch(r"[,.!?;:…]+", w.text):
                merged[-1].text += w.text
                merged[-1].end = max(merged[-1].end, w.end)
            else:
                merged.append(w)
        words = merged
        segments = []
        for seg in stamps.get("segment", []) or [{"segment": hyp.text, "start": words[0].start if words else 0,
                                                  "end": words[-1].end if words else 0}]:
            if not seg.get("segment", "").strip():
                continue
            start, end = round(float(seg["start"]), 3), round(float(seg["end"]), 3)
            inside = [w for w in words if start - 0.01 <= w.start < end + 0.01]
            segments.append(Segment(start, end, join_punctuation(seg["segment"]), inside))
        return segments

    def close(self) -> None:
        del self._model
        gc.collect()
        if self.device == "cuda":
            self._torch.cuda.empty_cache()


def load(name: str | None = None, device: str = "auto", allow_download: bool = False) -> Backend:
    name = name or default_model()
    if name not in MODELS:
        raise ValueError(f"model {name!r} không có; chọn một trong: {', '.join(MODELS)}")
    info = MODELS[name]
    path = info.locate(allow_download)
    if info.engine == "nemo":
        return ParakeetBackend(name, path, device)
    return FasterWhisperBackend(name, path, device)


def model_available(name: str) -> bool:
    """Thư viện của engine đã cài và model có trên máy (không tải gì)."""
    engine = {"ctranslate2": "faster_whisper", "nemo": "nemo"}[MODELS[name].engine]
    if importlib.util.find_spec(engine) is None:
        return False
    try:
        MODELS[name].locate(False)
    except (ModelMissing, ImportError):
        return False
    return True


def default_model() -> str:
    return next((name for name in PREFERENCE if model_available(name)), DEFAULT_MODEL)
