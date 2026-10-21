# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Guide cho AI agent: một nguồn markdown trong `contextcut-ai/guide/` (design §10).

Mỗi file (trừ `instructions.md`) là một topic, tên = đường dẫn tương đối không đuôi (`styles/gaming`),
mở đầu bằng front matter `title`/`summary`/`order` giữa hai dòng `---`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

INSTRUCTIONS = "instructions.md"


@dataclass(frozen=True)
class Topic:
    name: str
    title: str
    summary: str
    order: int
    body: str


def guide_dir() -> Path:
    if env := os.environ.get("CONTEXTCUT_GUIDE_DIR"):
        return Path(env)
    return Path(__file__).resolve().parents[2] / "guide"


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    # read_text dịch CRLF → LF, nên chỉ cần xử lý "\n"
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, body


def _read(path: Path, name: str) -> Topic:
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
    return Topic(name=name, title=meta.get("title", name), summary=meta.get("summary", ""),
                 order=int(meta.get("order", 100)), body=body.strip() + "\n")


def load_topics() -> list[Topic]:
    root = guide_dir()
    topics = [_read(p, p.relative_to(root).with_suffix("").as_posix())
              for p in root.rglob("*.md") if p.relative_to(root).as_posix() != INSTRUCTIONS]
    return sorted(topics, key=lambda t: (t.order, t.name))


def find_topic(name: str) -> Topic | None:
    """Tìm theo tên đầy đủ (`styles/gaming`) hoặc tên ngắn không trùng (`gaming`), có/không `.md`."""
    key = name.strip().lower().removesuffix(".md").strip("/")
    topics = load_topics()
    for t in topics:
        if t.name == key:
            return t
    short = [t for t in topics if t.name.rsplit("/", 1)[-1] == key]
    return short[0] if len(short) == 1 else None


def instructions() -> str:
    _, body = _split_front_matter((guide_dir() / INSTRUCTIONS).read_text(encoding="utf-8"))
    return body.strip()


def index_text() -> str:
    lines = ["Hướng dẫn ContextCut. Đọc bằng get_guide(topic) hoặc resource contextcut://guide/<topic>:"]
    lines += [f"- {t.name}: {t.title}. {t.summary}" for t in load_topics()]
    return "\n".join(lines) + "\n"
