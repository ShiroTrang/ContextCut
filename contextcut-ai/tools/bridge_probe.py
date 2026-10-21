# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets==16.0"]
# ///
# SPDX-FileCopyrightText: 2026 ContextCut contributors
# SPDX-License-Identifier: GPL-3.0-only OR LicenseRef-KDE-Accepted-GPL
"""Thử cầu nối AI của ContextCut (docs/protocol.md) từ dòng lệnh.

    uv run contextcut-ai/tools/bridge_probe.py check [--quick]
    uv run contextcut-ai/tools/bridge_probe.py call get_timeline limit=5 start_f=0
    uv run contextcut-ai/tools/bridge_probe.py watch [--seconds 60]

App phải đang chạy (nó ghi %LOCALAPPDATA%\\contextcut\\bridge.json; đổi bằng CONTEXTCUT_BRIDGE_FILE).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import ClientConnection, connect

PROTOCOL = 1
MAX_MESSAGE = 16 * 1024 * 1024


class RpcError(Exception):
    def __init__(self, error: dict):
        self.code = error.get("code")
        self.data = error.get("data") or {}
        self.kind = self.data.get("kind")
        super().__init__(f"{self.code} {self.kind}: {error.get('message')}")


class BridgeUnavailable(Exception):
    """bridge.json thiếu hoặc app không nghe ở cổng ghi trong file."""


def default_bridge_file() -> Path:
    if env := os.environ.get("CONTEXTCUT_BRIDGE_FILE"):
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "contextcut" / "bridge.json"


def load_bridge_file(path: str | Path | None = None) -> dict:
    path = Path(path) if path else default_bridge_file()
    if not path.is_file():
        raise BridgeUnavailable(f"không thấy {path} — Mở ContextCut trước")
    return json.loads(path.read_text(encoding="utf-8"))


class Bridge:
    """Một kết nối WebSocket tới cầu nối; `call` gửi JSON-RPC và chờ đúng id."""

    def __init__(self, info: dict, *, token: str | None = None, auth: bool = True, origin: str | None = None):
        self.info = info
        self.url = f"ws://{info['host']}:{info['port']}/"
        self._next_id = 0
        try:
            self.ws: ClientConnection = connect(
                self.url, origin=origin, open_timeout=5, close_timeout=2, max_size=MAX_MESSAGE, compression=None
            )
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            if isinstance(e, InvalidStatus):
                raise
            raise BridgeUnavailable(f"không nối được {self.url} ({e}) — Mở ContextCut trước") from e
        if auth:
            self.auth_result = self.call("auth", {"token": token or info["token"], "client": "bridge_probe"})

    def send_raw(self, frame: str | bytes) -> None:
        self.ws.send(frame)

    def recv_json(self, timeout: float = 10) -> dict:
        return json.loads(self.ws.recv(timeout=timeout))

    def request(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        while True:
            reply = self.recv_json(timeout)
            if reply.get("id") == self._next_id:
                return reply

    def call(self, method: str, params: dict | None = None) -> dict:
        reply = self.request(method, params)
        if "error" in reply:
            raise RpcError(reply["error"])
        return reply["result"]

    def close_code(self, timeout: float = 5) -> int | None:
        """Chờ server đóng kết nối, trả mã đóng (None nếu server không đóng)."""
        try:
            while True:
                self.ws.recv(timeout=timeout)
        except ConnectionClosed as e:
            return e.rcvd.code if e.rcvd else None
        except TimeoutError:
            return None

    def close(self) -> None:
        self.ws.close()


# ---------------------------------------------------------------- check


class Checker:
    def __init__(self):
        self.failed = 0

    def report(self, ok: bool | None, name: str, detail: str = "") -> None:
        tag = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
        if ok is False:
            self.failed += 1
        print(f"{tag}  {name}" + (f" — {detail}" if detail else ""), flush=True)


def expect_error(fn, code: int, kind: str) -> tuple[bool, str]:
    try:
        result = fn()
    except RpcError as e:
        return (e.code == code and e.kind == kind, str(e))
    return (False, f"không lỗi: {json.dumps(result)[:200]}")


def lan_addresses() -> list[str]:
    addrs = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # UDP connect không gửi gói nào
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127."))


def tcp_reachable(host: str, port: int, family: int = socket.AF_INET) -> bool:
    try:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect((host, port))
            return True
    except OSError:
        return False


def run_check(args) -> int:
    c = Checker()
    # 1. bridge.json
    try:
        info = load_bridge_file(args.file)
    except BridgeUnavailable as e:
        c.report(False, "1 bridge.json", str(e))
        return 1
    ok = (
        info.get("protocol") == PROTOCOL
        and info.get("host") == "127.0.0.1"
        and isinstance(info.get("port"), int)
        and re.fullmatch(r"[0-9a-f]{64}", info.get("token", "")) is not None
        and bool(info.get("session"))
        and isinstance(info.get("pid"), int)
    )
    shown = {k: ("…" if k == "token" else v) for k, v in info.items()}
    c.report(ok, "1 bridge.json đủ trường", json.dumps(shown, ensure_ascii=False))
    try:
        Bridge(info, auth=False).close()
    except BridgeUnavailable as e:
        c.report(False, "1 kết nối", str(e))
        return 1

    # 2. gọi method khi chưa auth
    b = Bridge(info, auth=False)
    ok, detail = expect_error(lambda: b.call("get_editor_state"), -32001, "unauthorized")
    code = b.close_code()
    c.report(ok and code == 4401, "2 chưa auth → unauthorized + đóng 4401", f"{detail}; close={code}")

    # 3. token sai
    b = Bridge(info, auth=False)
    wrong = ("0" if info["token"][0] != "0" else "1") + info["token"][1:]
    ok, detail = expect_error(lambda: b.call("auth", {"token": wrong}), -32001, "unauthorized")
    code = b.close_code()
    c.report(ok and code == 4401, "3 token sai → unauthorized + đóng 4401", f"{detail}; close={code}")
    b = Bridge(info, auth=False)
    ok, detail = expect_error(lambda: b.call("auth", {}), -32001, "unauthorized")
    code = b.close_code()
    c.report(ok and code == 4401, "3 thiếu token → unauthorized + đóng 4401", f"{detail}; close={code}")

    # 4. trình duyệt (có Origin)
    try:
        Bridge(info, auth=False, origin="http://example.com").close()
        c.report(False, "4 Origin bị từ chối", "bắt tay thành công")
    except InvalidStatus as e:
        c.report(True, "4 Origin bị từ chối", f"HTTP {e.response.status_code}")
    except BridgeUnavailable as e:
        c.report(True, "4 Origin bị từ chối", str(e))

    # 5. auth đúng
    b = Bridge(info)
    a = b.auth_result
    ok = a.get("session") == info["session"] and a.get("protocol") == PROTOCOL and isinstance(a.get("revision"), int)
    c.report(ok, "5 auth đúng", json.dumps(a, ensure_ascii=False))

    # 6. get_editor_state
    has_project = True
    try:
        st = b.call("get_editor_state")
        fps = st.get("profile", {}).get("fps", {})
        tracks = st.get("tracks", [])
        ok = (
            isinstance(st.get("revision"), int)
            and isinstance(fps.get("num"), int)
            and isinstance(fps.get("den"), int)
            and bool(st.get("sequence", {}).get("uuid"))
            and isinstance(st.get("playhead_f"), int)
            and all({"id", "tag", "kind"} <= t.keys() for t in tracks)
        )
        c.report(
            ok,
            "6 get_editor_state",
            f"project={st.get('project', {}).get('path')} fps={fps} tracks={[t.get('tag') for t in tracks]} "
            f"counts={st.get('counts')} revision={st.get('revision')}",
        )
    except RpcError as e:
        has_project = False
        c.report(e.kind in ("no_project", "busy"), "6 get_editor_state", f"{e} (chưa mở project)")

    # 7. phân trang get_timeline
    if has_project:
        try:
            full = b.call("get_timeline", {"limit": 1000})
            order = {t["id"]: i for i, t in enumerate(full["tracks"])}
            items = full["items"]
            sorted_ok = items == sorted(items, key=lambda it: (it["start_f"], order[it["track"]], it["id"]))
            paged, cursor, pages, page_ok = [], None, 0, True
            while True:
                params = {"limit": 1} | ({"cursor": cursor} if cursor else {})
                page = b.call("get_timeline", params)
                pages += 1
                page_ok &= len(page["items"]) <= 1
                paged += page["items"]
                cursor = page.get("next_cursor")
                if not cursor or pages > len(items) + 2:
                    break
            ids = [it["id"] for it in paged]
            ok = sorted_ok and page_ok and paged == items and len(ids) == len(set(ids)) and full.get("next_cursor") is None
            c.report(ok, "7 get_timeline phân trang", f"{len(items)} item, {pages} trang, sắp đúng={sorted_ok}")
            if items:
                print("      item đầu:", json.dumps(items[0], ensure_ascii=False))
        except RpcError as e:
            c.report(False, "7 get_timeline phân trang", str(e))

        # 8. tham số sai, cursor cũ
        rev = b.call("get_editor_state")["revision"]
        for name, params, code, kind in [
            ("cursor cũ", {"cursor": f"{rev - 1}.1"}, -32004, "stale_cursor"),
            ("limit sai kiểu", {"limit": "x"}, -32602, "invalid_params"),
            ("end_f < start_f", {"start_f": 10, "end_f": 5}, -32602, "invalid_params"),
            ("track không có", {"tracks": ["V99"]}, -32008, "not_found"),
        ]:
            ok, detail = expect_error(lambda p=params: b.call("get_timeline", p), code, kind)
            c.report(ok, f"8 get_timeline {name}", detail)

        # 9. list_recordings
        try:
            rec = b.call("list_recordings")
            rs = rec.get("recordings", [])
            ok = isinstance(rec.get("revision"), int) and all(
                isinstance(r.get("id"), str) and r.get("type") in ("av", "video") and isinstance(r.get("audio_streams"), list)
                for r in rs
            )
            c.report(ok, "9 list_recordings", f"{len(rs)} bản ghi: {[r.get('name') for r in rs]}")
        except RpcError as e:
            c.report(False, "9 list_recordings", str(e))
    else:
        c.report(None, "7–9 timeline/recordings", "chưa mở project")

    # 10. lỗi khung
    ok, detail = expect_error(lambda: b.call("no_such_method"), -32601, "method_not_found")
    c.report(ok, "10 method lạ", detail)
    b.send_raw("{not json")
    r = b.recv_json()
    c.report(r.get("error", {}).get("code") == -32700, "10 frame không phải JSON", json.dumps(r))
    b.send_raw(b"\x00\x01")
    r = b.recv_json()
    c.report(r.get("error", {}).get("code") == -32600, "10 frame nhị phân", json.dumps(r))
    b.close()

    # 11. chỉ loopback
    port = info["port"]
    addrs = lan_addresses()
    if addrs:
        reached = [a for a in addrs if tcp_reachable(a, port)]
        c.report(not reached, "11 không nối được qua IP khác loopback", f"thử {addrs}:{port}, nối được: {reached}")
    else:
        c.report(None, "11 không nối được qua IP khác loopback", "máy không có IPv4 nào ngoài loopback")
    c.report(not tcp_reachable("::1", port, socket.AF_INET6), "11 không nghe IPv6 ::1", f"[::1]:{port}")

    # 12. hết giờ auth
    if args.quick:
        c.report(None, "12 hết giờ auth → đóng 4408", "--quick")
    else:
        b = Bridge(info, auth=False)
        code = b.close_code(timeout=8)
        c.report(code == 4408, "12 hết giờ auth → đóng 4408", f"close={code}")

    print(f"\n{'OK' if not c.failed else f'{c.failed} mục FAIL'}")
    return 1 if c.failed else 0


# ---------------------------------------------------------------- call / watch


def parse_kv(pairs: list[str]) -> dict:
    params = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if key == "cursor":  # "<revision>.<offset>" looks like a float but must stay a string
            params[key] = value
            continue
        try:
            params[key] = json.loads(value)
        except json.JSONDecodeError:
            params[key] = value
    return params


def run_call(args) -> int:
    b = Bridge(load_bridge_file(args.file))
    try:
        result = b.call(args.method, parse_kv(args.params) if args.params else None)
    except RpcError as e:
        print(f"lỗi: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_watch(args) -> int:
    b = Bridge(load_bridge_file(args.file))
    last = None
    deadline = time.monotonic() + args.seconds if args.seconds else None
    while deadline is None or time.monotonic() < deadline:
        try:
            rev = b.call("get_editor_state")["revision"]
        except RpcError as e:
            rev = e.kind
        if rev != last:
            print(time.strftime("%H:%M:%S"), "revision", rev, flush=True)
            last = rev
        time.sleep(args.interval)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", help="đường dẫn bridge.json (mặc định %%LOCALAPPDATA%%\\contextcut\\bridge.json)")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check", help="chạy các kiểm tra của cổng P1a")
    pc.add_argument("--quick", action="store_true", help="bỏ kiểm hết giờ auth (mất 6 giây)")
    pcall = sub.add_parser("call", help="gọi một method, tham số dạng key=value (value là JSON)")
    pcall.add_argument("method")
    pcall.add_argument("params", nargs="*")
    pw = sub.add_parser("watch", help="in revision mỗi khi nó đổi")
    pw.add_argument("--seconds", type=float, default=0, help="dừng sau N giây (0 = tới khi Ctrl+C)")
    pw.add_argument("--interval", type=float, default=0.5)
    args = p.parse_args()
    try:
        return {"check": run_check, "call": run_call, "watch": run_watch}[args.cmd](args)
    except BridgeUnavailable as e:
        print(f"lỗi: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
