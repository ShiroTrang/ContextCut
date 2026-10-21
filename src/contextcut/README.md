# src/contextcut — code C++ riêng của ContextCut

Toàn bộ code C++ mới của ContextCut nằm ở đây, tách khỏi mã gốc Kdenlive để merge upstream dễ.

Dự kiến (theo `docs/specs/kien-truc-v3.md`, mục "Cấu trúc repository"):

| Thư mục | Việc | Giai đoạn |
| --- | --- | --- |
| `bridge/` | `AiBridgeServer` (QWebSocketServer `127.0.0.1` + token), JSON-RPC | P1 |
| `ops/` | Dịch ops sang lệnh mô hình timeline, gom thành một bước undo có nhãn "AI: …" | P1 |
| `vision/` | Render frame, contact sheet bằng MLT | P2 |
| `easymode/` | Giao diện Dễ, wizard, vùng cấm | P5 |
| `activity/` | Dock Hoạt động AI | P5 |

Trạng thái P0: **chỉ có README**. Thư mục này chưa được nối vào CMake; P1 thêm `add_subdirectory(contextcut)` trong `src/CMakeLists.txt` và một hook trong `Core::initGUI` (`src/core.cpp`, ngay sau `m_mainWindow = new MainWindow();`). Mỗi chỗ sửa file gốc như vậy phải ghi vào `patches.md`.
