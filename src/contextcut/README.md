# src/contextcut — code C++ riêng của ContextCut

Toàn bộ code C++ mới của ContextCut nằm ở đây, tách khỏi mã gốc Kdenlive để merge upstream dễ. Nguồn được biên dịch chung vào `kdenliveLib` qua `CMakeLists.txt` của thư mục này (nối từ `src/CMakeLists.txt`, xem `patches.md`).

| Thư mục | Việc | Giai đoạn |
| --- | --- | --- |
| `bridge/` | `AiBridgeServer` (QWebSocketServer `127.0.0.1` + token, `bridge.json`), khung JSON-RPC (`jsonrpc`), `RevisionTracker` | P1a ✔ |
| `model/` | `EditorReader`: đọc project/timeline/bin ra JSON (`get_editor_state`, `get_timeline`, `list_recordings`) | P1a ✔ |
| `ops/` | Dịch ops sang lệnh mô hình timeline, gom thành một bước undo có nhãn "AI: …" | P1c |
| `vision/` | Render frame, contact sheet bằng MLT | P2 |
| `easymode/` | Giao diện Dễ, wizard, vùng cấm | P5 |
| `activity/` | Dock Hoạt động AI | P5 |

Hợp đồng giao thức: `docs/protocol.md`. Điểm gắn duy nhất vào mã gốc: một dòng trong `Core::initGUI` (`src/core.cpp`).

Thêm method mới: viết hàm `JsonRpc::RpcResult f(const QJsonObject &params)` rồi `AiBridgeServer::registerMethod("ten_method", …)` (xem `EditorReader::registerReadOnlyMethods`). Handler chạy trên GUI thread, tuần tự; đọc revision bằng `server.revisions()->current()`; báo lỗi bằng các hàm `JsonRpc::invalidParams`, `noProject`, `notFound`… (không dùng exception).

Thử nhanh khi app đang chạy: `uv run contextcut-ai/tools/bridge_probe.py check`.
