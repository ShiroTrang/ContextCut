# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_bridge import FakeBridge  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"  # websockets chỉ chạy trên asyncio


@pytest.fixture
async def bridge(tmp_path, monkeypatch):
    """Cầu nối giả đang chạy; CONTEXTCUT_BRIDGE_FILE trỏ vào bridge.json của nó."""
    fake = FakeBridge(tmp_path / "bridge.json")
    monkeypatch.setenv("CONTEXTCUT_BRIDGE_FILE", str(fake.path))
    async with fake:
        yield fake
