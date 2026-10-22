# Các chỗ ContextCut sửa vào mã gốc Kdenlive

ContextCut là bản fork mỏng của Kdenlive. Code mới nằm trong `src/contextcut/`, `contextcut-ai/`, `packaging/build.*`, `packaging/run.ps1` và `docs/`. Mọi chỗ **buộc phải** sửa file có sẵn của Kdenlive được liệt kê dưới đây, kèm lý do, để mỗi lần merge bản phát hành KDE Gear mới biết phải kiểm lại chỗ nào.

Quy ước: tại chỗ sửa trong code có chú thích `// ContextCut:` (C++) hoặc `# ContextCut:` (CMake, gitignore…). Tìm nhanh:

```bash
git grep -n "ContextCut:" -- ':!docs' ':!patches.md'
git diff --stat v26.08.2 -- . ':!docs' ':!src/contextcut' ':!contextcut-ai' ':!packaging/build.sh' ':!packaging/build.ps1' ':!packaging/run.ps1' ':!CLAUDE.md' ':!AGENTS.md' ':!patches.md'
```

Gốc upstream: tag `v26.08.2` (`ef54398259f2af1d29095a798cab48ca4c52f141`).

## Danh sách

| File | Thay đổi | Lý do | GĐ |
| --- | --- | --- | --- |
| `.gitignore` | Thêm `/stage/` | Thư mục cài thử của `packaging/build.sh` | P0 |
| `.gitattributes` (mới) | `*.sh text eol=lf` | Máy Windows có `core.autocrlf=true`; bash không chạy được script CRLF | P0 |
| `CMakeLists.txt` | `DATA_INSTALL_PREFIX` `/kdenlive` → `/contextcut` | Qt trên Windows tìm dữ liệu app ở `<exe>/data/<applicationName>`; tên app giờ là `contextcut` | P0 |
| `src/CMakeLists.txt` | `OUTPUT_NAME contextcut` cho target `kdenlive` | Exe tên `contextcut.exe`; giữ tên target để không phải sửa các `target_link_libraries` | P0 |
| `data/CMakeLists.txt` | Cài `kdenlive.notifyrc` thành `contextcut.notifyrc` | KNotification tìm `knotifications6/<applicationName>.notifyrc` | P0 |
| `src/uiresources.qrc` | Prefix `/kxmlgui5/contextcut`, alias `contextcutui.rc` | KXmlGui tìm `kxmlgui5/<componentName>/<componentName>ui.rc` | P0 |
| `src/main.cpp` (`resetConfig`) | `kdenlive` → `contextcut` ở tên config và đường dẫn kxmlgui | Reset sau crash chỉ xoá file của ContextCut, không đụng `kdenliverc` của Kdenlive gốc | P0 |
| `src/main.cpp` (`MLT_REPOSITORY_DENY`) | Thêm `libmltjackrack:libmltladspa` | Chặn plugin Waves SoundGrid (+3,5 s khởi động, crash lúc thoát sau khi xuất clip dài). Phải sửa ở đây vì Kdenlive ghi đè biến này; `kdenlive_render` thừa hưởng biến môi trường | P0 |
| `src/main.cpp` (`KAboutData`) | componentName `contextcut`, tên hiển thị `ContextCut`, mô tả "dựa trên Kdenlive", homepage + báo lỗi về GitHub ContextCut, thêm component "Kdenlive"; giữ version `KDENLIVE_VERSION` và toàn bộ tác giả Kdenlive | Tách config/data (`contextcutrc`, `%LOCALAPPDATA%\contextcut`), không dùng Kdenlive làm tên sản phẩm, không gửi lỗi của fork lên KDE | P0 |
| `src/core.cpp` | Đường dẫn kxmlgui khi kiểm crash lần đầu → `kxmlgui5/contextcut/contextcutui.rc` | Như `resetConfig` | P0 |
| `src/core.cpp` (`initGUI`) | `#include "contextcut/bridge/aibridgeserver.h"` + một dòng `ContextCut::AiBridgeServer::start(m_mainWindow);` ngay sau `m_mainWindow = new MainWindow();` | Khởi động cầu nối AI (WebSocket `127.0.0.1` + token, `docs/protocol.md`). Không có hook nào khác; app vẫn chạy nếu cầu nối không mở được cổng | P1a |
| `src/CMakeLists.txt` | `add_subdirectory(contextcut)`; sau khối link Qt: `find_package(Qt6 … WebSockets)` + `target_link_libraries(kdenliveLib PUBLIC Qt6::WebSockets)` | Biên dịch `src/contextcut/` vào `kdenliveLib` như các thư mục con khác; cầu nối dùng `QWebSocketServer` | P1a |
| `src/jobs/proxytask.cpp` (`run`) | Hai `connect(readyReadStandardError → processLogInfo)` (nhánh MLT và ffmpeg) thêm `Qt::DirectConnection` | Sửa lỗi **treo khi tạo proxy** (bản ghi OBS HEVC): `QProcess` tạo và chờ trong luồng worker của `QThreadPool`, còn `ProxyTask` sống ở luồng giao diện → slot chạy ở luồng giao diện, `readAllStandardError()` đua với worker trên bộ đệm đọc của `QProcess` (không thread-safe) → đọc ra nhiều byte hơn tiến trình ghi, rồi luồng giao diện quay mãi trong `processLogInfo` hoặc crash. Giống cách `TranscodeTask` (nhánh ffmpeg) đã làm. Upstream `master` chưa sửa (kiểm 22/10/2026); bỏ patch khi upstream sửa | P2a |

## Phụ thuộc API nội bộ (không phải patch)

`src/contextcut/ops/timelineaccess.h` gọi vài thành viên `protected` của Kdenlive qua lớp dẫn xuất (con trỏ-tới-thành-viên), không sửa file gốc. Merge bản KDE Gear mới mà các chữ ký này đổi thì lỗi biên dịch ở file đó:

| Lớp | Thành viên | Dùng cho |
| --- | --- | --- |
| `TimelineModel` | `requestClipCreation`, `getTrackById_const`, `getClipPtr`, `m_groups` | `insert_clip`/`add_music`/chữ (tạo clip một stream, không hộp thoại), kiểm mix, độ dài nguồn, nhóm V+A |
| `ClipModel` | `getMaxDuration` | Kiểm `trim` không vượt nguồn |
| `MarkerListModel` | `addMarker(GenTime, QString, int, Fun &, Fun &)` | `add_markers` gom vào một bước undo |

## Biết trước, chưa vá

| Hiện tượng | Ảnh hưởng | Khi nào xử lý |
| --- | --- | --- |
| File khoá `%TEMP%\kdenlivelock` dùng chung với Kdenlive gốc | Nếu Kdenlive gốc crash lúc khởi động, lần mở ContextCut kế tiếp có thể hỏi khôi phục/reset (và ngược lại). Chỉ tồn tại trong lúc khởi động | Khi cần (4 chỗ trong `core.cpp`, `projectmanager.cpp`) |
| KNewStuff (`data/knewstuff/*.knsrc`: `TargetDir=kdenlive/...`) | Hiệu ứng/preset tải từ store.kde.org vào thư mục của Kdenlive gốc, ContextCut không thấy | P6 (thư viện asset) |
| `AbstractPythonInterface::deleteVenv` chỉ xoá khi đường dẫn chứa `kdenlive` | Nút xoá venv Python (Whisper/SAM2 của Kdenlive) không làm gì | Nếu dùng tính năng đó |
| Icon exe và cửa sổ vẫn là logo Kdenlive | Thương hiệu | P5, khi có logo ContextCut |
| Nhiều chuỗi giao diện còn chữ "Kdenlive" (hộp thoại, wizard, splash) | Thương hiệu | P5 (giao diện Dễ) |
| `desktopFileName` vẫn `org.kde.kdenlive`, `organizationDomain` vẫn `kde.org` | Không thấy trên Windows | Khi đóng gói (P5) |
| Hiệu ứng dựa trên LADSPA biến mất khỏi danh sách | Hệ quả của chặn module `ladspa` | Chấp nhận |
| Clip bin đang nạp (`StatusWaiting`) bị khoá ghi `m_producerLock` trên luồng giao diện, từ hàm dựng `ClipController` tới `setProducer`/`setInvalid` (cũng chạy ở luồng giao diện) | Luồng giao diện gọi getter có `QReadLocker` (`frameDuration`, `getFrameSize`, `originalFps`, `getProducerIntProperty`…) trên clip đó thì tự treo vĩnh viễn (Qt không cho khoá đọc khi chính luồng đó giữ khoá ghi). Kdenlive tự né bằng kiểm `StatusWaiting`; cầu nối né trong `EditorReader` (`stillLoading`), op kiểm `statusReady()` trước | Không vá mã gốc; code ContextCut mới đọc clip bin phải kiểm như vậy |
| Các job khác cùng kiểu với lỗi proxy: `CutTask`, `SpeedTask`, `StabilizeTask`, `FilterTask`, `SceneSplitTask`, `MeltTask`, `MaskTask`, `CustomJobTask`, `TranscodeTask` (nhánh MLT) nối `readyReadStandard*` vào task ở luồng giao diện | Có thể treo/crash như proxy khi tiến trình con ghi nhiều log; ít gặp vì chỉ chạy khi người dùng tự gọi | Khi ContextCut dùng tới job đó: thêm `Qt::DirectConnection` như `proxytask.cpp` |
