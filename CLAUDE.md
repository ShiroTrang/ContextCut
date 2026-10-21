# ContextCut — ghi chú cho AI agent

ContextCut = bản fork mỏng của Kdenlive 26.08.2 (C++/Qt 6, MLT) + dịch vụ Python MCP (`contextcut-ai/`) để AI agent (Claude, Codex, Antigravity) sửa timeline đang mở, mỗi đợt sửa là một bước undo có nhãn. Công cụ cá nhân của Nhan, chia cho 2–3 bạn qua repo private `ShiroTrang/ContextCut`. Nói chuyện với Nhan bằng tiếng Việt.

`AGENTS.md` và `CLAUDE.md` có cùng nội dung; sửa file này thì chép sang file kia.

## Đọc trước

1. `docs/handoff/` — ghi chú bàn giao của giai đoạn trước (đọc file mới nhất).
2. `docs/specs/2026-10-21-contextcut-design.md` — thiết kế v3.1 (thắng khi mâu thuẫn).
3. `docs/specs/kien-truc-v3.md` — kiến trúc v3 (bản gốc: `D:\ContextCut\ContextCut MCP — Kiến trúc v3.md`).
4. `patches.md` — mọi chỗ đã sửa vào mã gốc Kdenlive.

## Build và chạy (Windows, PowerShell)

```powershell
# Build một lệnh: cài phụ thuộc (pacman --needed), configure, build, cài vào stage\
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
#   -SkipDeps  bỏ pacman · -Reconfigure  chạy lại cmake · -ConfigureOnly · -Msys2Root <dir>
# Chạy bản vừa build (thêm ucrt64\bin vào PATH)
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\run.ps1
```

- MSYS2 riêng: `D:\ContextCut\env\msys64` (UCRT64; mặc định `<repo>\..\env\msys64`, đổi bằng `-Msys2Root` hoặc `CONTEXTCUT_MSYS2`). **Không đụng `C:\msys64`** (Python trên PATH của Nhan lấy từ đó).
- Thư mục: `build\` (Ninja), `stage\` (cài thử, `stage\bin\contextcut.exe`), ccache dùng chung `D:\ContextCut\env\ccache`.
- Thời gian (8 nhân): build đầy đủ 22–27 phút; không đổi gì thì ~10 giây; sửa một file `.cpp` thì vài chục giây (ccache).
- Chưa có test tự động (`BUILD_TESTING=OFF`). Kiểm bằng cách chạy app.

## Quy tắc fork mỏng

- Code mới vào `src/contextcut/` (C++) và `contextcut-ai/` (Python). Sửa file gốc Kdenlive chỉ khi buộc phải; mỗi chỗ ghi vào `patches.md` và chú thích `// ContextCut:` tại chỗ (`git grep -n "ContextCut:"`).
- Không đổi định dạng `.kdenlive`; project phải mở được bằng Kdenlive gốc. Version ghi vào file vẫn là `KDENLIVE_VERSION`.
- Tên app nội bộ là `contextcut`: config `%LOCALAPPDATA%\contextcutrc`, dữ liệu `%LOCALAPPDATA%\contextcut\`, giao diện `%LOCALAPPDATA%\kxmlgui5\contextcut\`, dữ liệu cài `stage\bin\data\contextcut\`. Miền dịch i18n vẫn `kdenlive`.
- Remote: `origin` = GitHub ContextCut, `upstream` = invent.kde.org (push bị tắt). Cập nhật upstream bằng merge tag KDE Gear (`git fetch upstream --tags; git merge v26.12.x`), không bám `master`.

## Bẫy đã gặp

- Đường dẫn `/d/...` đưa cho công cụ Windows (cmake, gcc, melt) thành `D:\d\...`: luôn `cygpath -m`.
- PowerShell 5.1 làm hỏng dấu ngoặc kép khi truyền lệnh inline cho bash: viết file `.sh` rồi chạy `bash -l file.sh` với `MSYSTEM=UCRT64`.
- Không chạy `du -sh /` trong MSYS2 (quét cả ổ C và D).
- Máy Nhan có `core.autocrlf=true`: `.gitattributes` giữ `*.sh` ở LF.
- CMake `FindPython3` lấy Python Windows qua registry: `build.sh` ghim `Python3_EXECUTABLE` về `ucrt64/bin/python3.exe`.
- MLT trên Windows **bỏ qua `MLT_REPOSITORY`**, luôn nạp module từ `<exe>\..\lib\mlt` (data `<exe>\..\share\mlt`, frei0r `<exe>\..\lib\frei0r-1`). `build.sh` chép ba thư mục này từ `ucrt64` vào `stage\` (~15 MB); thiếu chúng thì wizard báo "Missing MLT module avformat/sdl…" và không qua được.
- Plugin **Waves SoundGrid** trên máy Nhan bị MLT nạp qua `jackrack`/`ladspa`: ContextCut chặn bằng `MLT_REPOSITORY_DENY` trong `src/main.cpp`. Đặt biến này từ launcher là vô tác dụng vì `main.cpp` ghi đè.
- Gói `mingw-w64-ucrt-x86_64-kdenlive` của MSYS2 (`ucrt64\bin\kdenlive.exe`) **crash** khi dựng cửa sổ chính (`Qt6Widgets.dll` gọi từ `libkddockwidgets-qt62.dll`; nghi lệch ABI: gói kdenlive build 12/10, kddockwidgets 2.5.0 build 19/10). Đừng dùng nó làm Kdenlive gốc để so sánh; build từ nguồn thì chạy được.
- Lần chạy đầu hiện hộp Quick Setup bằng QML: phím Enter không bấm được; tự động hoá bằng UI Automation `InvokePattern` trên nút "Start Editing". Màn hình chào chặn việc khởi tạo MLT cho tới khi qua nó (`--no-welcome` để bỏ).
- App GUI không in log ra stderr khi bị chuyển hướng, trừ khi đặt `QT_FORCE_STDERR_LOGGING=1`.
- File khoá `%TEMP%\kdenlivelock` dùng chung với Kdenlive gốc (xem `patches.md`).
- `D:\ContextCut` đang được loại khỏi Windows Defender: chỉ tải từ nguồn chính thức. Nhắc Nhan gỡ loại trừ khi xong dự án.

## Giai đoạn

Mỗi giai đoạn chạy trong **một session mới**: đọc ghi chú bàn giao trước, viết kế hoạch `docs/plans/Pn.md`, làm, kiểm cổng, commit, viết `docs/handoff/Pn.md` (đã xong, lệch thiết kế, lệnh, việc dở). Giai đoạn lớn chia nhiều session, mỗi session kết thúc bằng thứ chạy được và một commit. Hỏi Nhan trước khi push.

| GĐ | Nội dung | Trạng thái |
| --- | --- | --- |
| P0 | Nền: repo, build một lệnh, đổi tên tối thiểu, fix Waves | Xong 21/10/2026 (`docs/handoff/P0.md`) |
| P1 | Cầu nối: AiBridgeServer, JSON-RPC, ops cơ bản, MCP server Python | Chưa |
| P2 | Phụ đề chuẩn timing, vision, xuất, `zoom` | Chưa |
| P3 | Dàn ý, `find_moments`, `detect_beats`, `beat_montage` | Chưa |
| P4 | Multi-POV, placeholder, sync | Chưa |
| P5 | Giao diện Dễ, dock Hoạt động AI, zip portable, logo | Chưa |
| P6 | Hiệu ứng, thư viện meme/SFX | Chưa |
| P7 | Series "100 ngày" | Chưa |
