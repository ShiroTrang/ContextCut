# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""GPU: nạp DLL CUDA từ wheel `nvidia-*` của PyPI (Windows) và đo VRAM toàn card bằng NVML."""

from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path

_dll_dirs_added = False


def add_cuda_dll_dirs() -> list[str]:
    """Thư mục `site-packages/nvidia/*/bin` (cuBLAS, cuDNN) vào đường tìm DLL, trước khi import ctranslate2.

    Thêm cả PATH: cuDNN tự nạp các DLL con bằng LoadLibrary thường, không theo `os.add_dll_directory`.
    """
    global _dll_dirs_added
    if os.name != "nt" or _dll_dirs_added:
        return []
    spec = importlib.util.find_spec("nvidia")
    dirs = []
    for root in (spec.submodule_search_locations or []) if spec else []:
        for sub in sorted(Path(root).iterdir()):
            if (sub / "bin").is_dir():
                dirs.append(str(sub / "bin"))
    for d in dirs:
        os.add_dll_directory(d)
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    _dll_dirs_added = True
    return dirs


class VramMonitor:
    """`with VramMonitor() as m:` — đọc VRAM đã dùng của card 0 mỗi `interval_s`; `peak_mib`/`baseline_mib` là MiB
    toàn card (Windows WDDM không cho số theo tiến trình). Không có NVML → các trường là None."""

    def __init__(self, interval_s: float = 0.2):
        self.interval_s = interval_s
        self.baseline_mib: int | None = None
        self.peak_mib: int | None = None
        self.total_mib: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._handle = None

    def _used(self) -> int:
        import pynvml
        return pynvml.nvmlDeviceGetMemoryInfo(self._handle).used // (1 << 20)

    def __enter__(self) -> VramMonitor:
        try:
            import pynvml
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.total_mib = pynvml.nvmlDeviceGetMemoryInfo(self._handle).total // (1 << 20)
        except Exception:  # noqa: BLE001 — không có driver/thư viện NVML: không đo, không lỗi
            return self
        self.baseline_mib = self.peak_mib = self._used()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.peak_mib = max(self.peak_mib or 0, self._used())

    def __exit__(self, *exc: object) -> None:
        if self._thread:
            self._stop.set()
            self._thread.join()
            self.peak_mib = max(self.peak_mib or 0, self._used())
            import pynvml
            pynvml.nvmlShutdown()

    def summary(self) -> dict[str, int | None]:
        return {"vram_baseline_mib": self.baseline_mib, "vram_peak_mib": self.peak_mib, "vram_total_mib": self.total_mib}
