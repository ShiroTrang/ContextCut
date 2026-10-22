# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Chuyển vinai/PhoWhisper-large (đã có trong cache HuggingFace) sang CTranslate2 float16 để faster-whisper chạy được.

    uv run --directory contextcut-ai --extra analysis --extra parakeet --with transformers python tools/convert_phowhisper.py

Chạy một lần tại máy, không tải gì (chỉ đọc cache; thiếu thì báo). Kết quả ~3,1 GB ở
`%LOCALAPPDATA%\\contextcut\\models\\phowhisper-large-ct2` (đổi bằng CONTEXTCUT_MODELS). PhoWhisper (BSD-3) được
fine-tune từ whisper-large-v2 và giữ `alignment_heads`, nên faster-whisper vẫn lấy được timestamp từng từ.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time

from contextcut_ai.paths import models_dir

REPO = "vinai/PhoWhisper-large"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="ghi đè bản đã chuyển")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import snapshot_download

    try:
        src = snapshot_download(REPO, local_files_only=True)
    except Exception as e:  # noqa: BLE001
        print(f"Chưa có {REPO} trong cache HuggingFace (6,2 GB). Tải bằng huggingface_hub rồi chạy lại. ({e})")
        return 2
    out = models_dir() / "phowhisper-large-ct2"
    free_gb = shutil.disk_usage(out.parent if out.parent.exists() else models_dir().anchor).free / 1e9
    print(f"Nguồn: {src}\nĐích:  {out} (~3,1 GB, ổ còn {free_gb:.0f} GB)")
    out.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    converter = TransformersConverter(src, copy_files=["tokenizer.json", "preprocessor_config.json"],
                                      load_as_float16=True)
    converter.convert(str(out), quantization="float16", force=args.force)
    print(f"Xong sau {time.monotonic() - start:.0f} s: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
