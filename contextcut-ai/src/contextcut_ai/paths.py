# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Chỗ để dữ liệu: thư mục chung của máy (job, model, khoá GPU) và thư mục đi kèm project; tìm ffmpeg/ffprobe."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]


class ToolMissing(Exception):
    def __init__(self, name: str):
        super().__init__(f"Không tìm thấy {name}: cài ffmpeg (MSYS2 của dự án hoặc trên PATH) "
                         "hoặc đặt CONTEXTCUT_FFMPEG_DIR trỏ tới thư mục có ffmpeg.exe/ffprobe.exe.")


class ProjectNotSaved(Exception):
    def __init__(self) -> None:
        super().__init__("Lưu project trước (Ctrl+S) để ContextCut có chỗ lưu transcript và dữ liệu phân tích "
                         "(thư mục <tên project>.contextcut cạnh file .kdenlive), rồi gọi lại.")


def data_dir() -> Path:
    if env := os.environ.get("CONTEXTCUT_DATA_DIR"):
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "contextcut"


def jobs_dir() -> Path:
    return data_dir() / "jobs"


def models_dir() -> Path:
    if env := os.environ.get("CONTEXTCUT_MODELS"):
        return Path(env)
    return data_dir() / "models"


def gpu_lock_file() -> Path:
    return data_dir() / "gpu.lock"


def find_tool(name: str) -> str:
    """`CONTEXTCUT_FFMPEG_DIR` → ffmpeg của MSYS2 dự án (`<repo>\\..\\env\\msys64\\ucrt64\\bin`) → PATH."""
    exe = name if name.lower().endswith(".exe") or os.name != "nt" else name + ".exe"
    dirs = [os.environ.get("CONTEXTCUT_FFMPEG_DIR"),
            str(Path(os.environ.get("CONTEXTCUT_MSYS2") or REPO.parent / "env" / "msys64") / "ucrt64" / "bin")]
    for d in dirs:
        if d and (Path(d) / exe).is_file():
            return str(Path(d) / exe)
    if found := shutil.which(name):
        return found
    raise ToolMissing(name)


def companion_dir(state: dict[str, Any]) -> Path:
    """Thư mục `<project>.contextcut/` từ kết quả `get_editor_state`; project chưa lưu → `ProjectNotSaved`."""
    project = state.get("project") or {}
    if not project.get("companion_dir"):
        raise ProjectNotSaved()
    return Path(project["companion_dir"])
