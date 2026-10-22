# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Sơ đồ track audio của từng bản ghi (design §8.1) và `recordings.json` trong thư mục đi kèm project.

OBS ghi 5 track: 1 trộn chung, 2 Mic (Nhan), 3 Discord (bạn bè), 4 game, 5 desktop dự phòng. Tên stream (đặt trong OBS)
thắng thứ tự; người dùng sửa được bằng `set_track_map`, sơ đồ đã sửa giữ tới khi file đổi.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from . import media

ROLES = ("mix", "mic", "discord", "game", "desktop", "other")
OBS_ORDER = ("mix", "mic", "discord", "game", "desktop")
SPEAKERS = {"mic": "Nhan", "discord": "bạn bè"}
TITLE_RULES = [  # (role, mẫu trên tên đã bỏ dấu, chữ thường)
    ("mic", re.compile(r"\b(mic|micro|microphone|voice|giong)\b")),
    ("discord", re.compile(r"\b(discord|friends?|ban|ban be)\b")),
    ("game", re.compile(r"\b(game|gameplay)\b")),
    ("desktop", re.compile(r"\b(desktop)\b")),
    ("mix", re.compile(r"\b(mix|tron|tron chung)\b")),
]


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower()).replace("đ", "d")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def role_from_title(title: str | None) -> str | None:
    if not title:
        return None
    plain = _plain(title)
    for role, pattern in TITLE_RULES:
        if pattern.search(plain):
            return role
    return None


def _entry(stream: media.AudioStream, position: int, role: str, speaker: str | None, transcribe: bool) -> dict[str, Any]:
    return {"index": stream.index, "obs_track": position + 1, "title": stream.title, "channels": stream.channels,
            "role": role, "speaker": speaker, "transcribe": transcribe}


def default_map(streams: list[media.AudioStream]) -> list[dict[str, Any]]:
    if len(streams) == 1:
        return [_entry(streams[0], 0, "mix", None, True)]
    titled = [role_from_title(s.title) for s in streams]
    taken = {r for r in titled if r}
    roles = []
    for i, role in enumerate(titled):
        if role is None:
            positional = OBS_ORDER[i] if i < len(OBS_ORDER) else "other"
            role = "other" if positional in taken else positional
        roles.append(role)
    has_voice = any(r in SPEAKERS for r in roles)
    return [_entry(s, i, r, SPEAKERS.get(r), r in SPEAKERS or (r == "mix" and not has_voice))
            for i, (s, r) in enumerate(zip(streams, roles, strict=True))]


class RecordingStore:
    """`recordings.json`: mỗi bản ghi (id = `kdenlive:id`) → đường dẫn, hash, stream, `track_map`."""

    def __init__(self, companion: str | Path):
        self.companion = Path(companion)
        self.file = self.companion / "recordings.json"

    def _load(self) -> dict[str, Any]:
        if not self.file.exists():
            return {"schema": 1, "recordings": {}}
        return json.loads(self.file.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.companion.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)

    def get(self, rec_id: str) -> dict[str, Any] | None:
        return self._load()["recordings"].get(rec_id)

    def ensure(self, rec_id: str, path: str | Path) -> dict[str, Any]:
        """Bản ghi đã có và file không đổi (đường dẫn, kích thước, mtime) → giữ nguyên, kể cả sơ đồ người dùng sửa."""
        p = Path(path)
        st = p.stat()
        data = self._load()
        rec = data["recordings"].get(rec_id)
        if rec and rec["path"] == p.as_posix() and rec["size"] == st.st_size and rec["mtime"] == int(st.st_mtime):
            return rec
        probed = media.probe(p)
        rec = {"path": p.as_posix(), "size": st.st_size, "mtime": int(st.st_mtime), "file_hash": media.fast_hash(p),
               "duration_s": probed.duration_s,
               "streams": [{"index": s.index, "title": s.title, "channels": s.channels, "sample_rate": s.sample_rate}
                           for s in probed.streams],
               "track_map": default_map(probed.streams)}
        data["recordings"][rec_id] = rec
        self._save(data)
        return rec

    def set_track_map(self, rec_id: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        data = self._load()
        rec = data["recordings"].get(rec_id)
        if rec is None:
            raise KeyError(rec_id)
        streams = {s["index"]: (pos, s) for pos, s in enumerate(rec["streams"])}
        has_voice = any(e.get("role") in SPEAKERS for e in entries)
        track_map = []
        for e in entries:
            index = e.get("index")
            if index not in streams:
                raise ValueError(f"bản ghi {rec_id} không có stream audio index {index} "
                                 f"(có: {', '.join(map(str, streams))})")
            role = e.get("role")
            if role not in ROLES:
                raise ValueError(f"role {role!r} không hợp lệ (một trong {', '.join(ROLES)})")
            pos, s = streams[index]
            speaker = e.get("speaker", SPEAKERS.get(role))
            track_map.append({"index": index, "obs_track": pos + 1, "title": s["title"], "channels": s["channels"],
                              "role": role, "speaker": speaker,
                              "transcribe": bool(e.get("transcribe", role in SPEAKERS or (role == "mix" and not has_voice)))})
        rec["track_map"] = track_map
        self._save(data)
        return rec
