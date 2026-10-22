# ContextCut — ghi chú cho AI agent

ContextCut = bản fork mỏng của Kdenlive 26.08.2 (C++/Qt 6, MLT) + dịch vụ Python MCP (`contextcut-ai/`) để AI agent (Claude, Codex, Antigravity) sửa timeline đang mở, mỗi đợt sửa là một bước undo có nhãn. Công cụ cá nhân của Nhan, chia cho 2–3 bạn qua repo private `ShiroTrang/ContextCut`. Nói chuyện với Nhan bằng tiếng Việt.

`AGENTS.md` và `CLAUDE.md` có cùng nội dung; sửa file này thì chép sang file kia.

## Đọc trước

1. `docs/handoff/` — ghi chú bàn giao của giai đoạn trước (đọc file mới nhất).
2. `docs/specs/2026-10-21-contextcut-design.md` — thiết kế v3.1 (thắng khi mâu thuẫn).
3. `docs/specs/kien-truc-v3.md` — kiến trúc v3 (bản gốc: `D:\ContextCut\ContextCut MCP — Kiến trúc v3.md`).
4. `patches.md` — mọi chỗ đã sửa vào mã gốc Kdenlive.
5. `docs/plans/P1.md` (P1 chia P1a/P1b/P1c) và `docs/protocol.md` — hợp đồng cầu nối app ↔ `contextcut-ai`.

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
- Chưa có test C++ trong CMake (`BUILD_TESTING=OFF`). Op sửa timeline (P1c) kiểm qua cầu nối: `uv run contextcut-ai/tools/p1_fixture.py --out <dir>` dựng project `p1-gate` và in lệnh mở app, rồi `uv run --directory contextcut-ai pytest -m live` (`test_live_ops.py`: mỗi op apply → `undo_batch` → so toàn bộ timeline; chỉ chạy khi project tên `p1-gate`).
- Cầu nối AI (P1a): app ghi `%LOCALAPPDATA%\contextcut\bridge.json` (cổng + token mỗi lần chạy). Khi app đang chạy: `uv run contextcut-ai/tools/bridge_probe.py check` (20 kiểm tra), `… call get_timeline limit=5`, `… watch`.
- MCP server (P1b–P1c, `contextcut-ai/README.md`): `uv run --directory contextcut-ai pytest` (test sống `-m live` tự bỏ qua khi app không chạy); đăng ký cho client: `uv run --directory contextcut-ai python scripts/register_clients.py [--dry-run]` (hỏi y/N từng thay đổi). Sửa `contextcut-ai/guide/` thì chạy `scripts/gen_agent_docs.py`.
- Op sửa timeline (P1c): `src/contextcut/ops/` — thêm op = `OpSpec` (`opregistry.cpp`) + `checkState` (`opvalidator.cpp`) + hàm trong `timelineops.cpp`, mọi lời gọi Kdenlive qua `TimelineOps::step()`. Thành viên `protected` của Kdenlive lấy qua `timelineaccess.h` (không sửa mã gốc).

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
- Thêm thư viện Qt vào link `PUBLIC` của `kdenliveLib` đổi cờ biên dịch của mọi file: lần build sau biên dịch lại cả thư viện (~10 phút); code của `src/contextcut/` nên dùng thư viện đã có.
- Tự động hoá UI ContextCut: computer-use không thấy `contextcut.exe`. Dùng UI Automation của PowerShell: bấm được nút thanh công cụ, nút hộp thoại, tab sequence; **menu Qt thì không**. Chạy lệnh theo tên bằng SendKeys `^%i` (Find Action) + tên + Enter. Hộp "Project Settings" không có trong cây UIA: chụp cửa sổ để xem. Nút Forward/Rewind thứ hai mới là của Project Monitor.
- Giết app thì lần sau hộp "File Recovery" chặn việc nạp project (cầu nối trả `no_project` tới khi bấm "Do not recover").
- Ở màn hình chào (cửa sổ `Splash`, khi mở app không kèm project và không `--no-welcome`) cửa sổ chính chưa dựng nên **cầu nối chưa mở**, chưa có `bridge.json`.
- Thử agent bằng `claude -p` từ trong phiên Claude Code của app desktop: bỏ các biến `CLAUDE*`, `ANTHROPIC_*` thừa hưởng từ app trước khi chạy; CLI báo 401 "token revoked" thì Nhan chạy `claude auth login`. Trong Git Bash, đối số `/mcp__…` bị đổi thành `C:/Program Files/Git/mcp__…`: đặt `MSYS_NO_PATHCONV=1`.
- Đóng app khi project đã sửa: `WindowPattern.Close` của UIA treo vì hộp "save changes?" là modal, và UIA không thấy nút trong hộp đó. Gửi `WM_CLOSE` cho cửa sổ chính, rồi `PostMessage` nhấp chuột vào "Do Not Save" bằng **toạ độ client** ≈ 394,63 (hộp `Warning - ContextCut` 549×125, client 533×86).
- `-i` của app nhận **một** danh sách file phân cách dấu phẩy; lặp `-i` thì chỉ cái cuối có tác dụng.
- Phím tắt (Ctrl+Z, Ctrl+Shift+Z, Ctrl+S) gửi bằng `SendKeys` sau `SetForegroundWindow` cửa sổ chính thì ăn; Home thì không (focus ở bin). Lưu lần đầu project tạo bằng Kdenlive cũ hiện hộp "modified by Kdenlive… backup" (Enter).
- Kdenlive thêm "hh:mm " trước mọi nhãn undo; tham số keyframe của hiệu ứng (vd. `level` của Volume) phải là chuỗi animation MLT (`0=-6`), số trần bị đọc thành rỗng.
- Thông báo "đang xử lý" trên thanh trạng thái của Kdenlive giữ tối thiểu 4 s trước khi thông báo khác thay.
- Dựng một khung hình từ `.kdenlive` để tự kiểm: trong bash UCRT64 `MLT_REPOSITORY_DENY=libmltjackrack:libmltladspa melt -quiet x.kdenlive in=N out=N -consumer avformat:f.png vcodec=png an=1`.
- `codex exec` không duyệt được tool MCP sửa (chính sách `never`): thử sửa bằng Codex thì chạy tương tác.
- `uv sync` cài lại project khi `pyproject.toml` đổi: đóng mọi AI client đang chạy server `contextcut-ai` trước (Windows khoá `contextcut-ai.exe`), giữ đúng các `--extra`; test chạy `uv run --no-sync`. Server đăng ký bằng `uv run --no-sync` (không tự cài; trước đây `--frozen` tự cài nên client mới báo "Connection closed" khi client khác còn giữ khoá). Client còn đăng ký `--frozen`: chạy lại `register_clients.py`.
- Kdenlive treo khi tạo proxy (bản ghi OBS HEVC; luồng giao diện kẹt trong `ProxyTask::processLogInfo`): `QProcess` bị đọc chéo luồng. **Đã vá** (`proxytask.cpp`, `patches.md`); cách tái hiện chắc chắn (`-loglevel debug` trong `proxyparams`) ở cuối `docs/handoff/P2a.md`. Các job Kdenlive khác cùng kiểu kết nối chưa vá.
- `-i` với một mục rỗng (`",a.mkv"`) nhập **cả thư mục hiện tại, đệ quy**. PowerShell 5.1 đọc `.ps1` UTF-8 không BOM như ANSI: đừng để tên có dấu trong script.
- Chạy bản sao `stage` ở thư mục khác thì nó ghi `mltpath` của nó vào `contextcutrc`; sửa lại về `…/contextcut/stage/share/mlt/profiles`.
- Clip bin đang nạp (`StatusWaiting`, tốt hay hỏng đều vậy) bị Kdenlive khoá ghi producer trên luồng giao diện tới khi nạp xong: cầu nối gọi `frameDuration()`, `getFrameSize()`, `getOriginalFps()`, `getProducerIntProperty()`… trên clip đó là app treo vĩnh viễn. Kiểm `clipStatus() != StatusWaiting` hoặc `statusReady()` trước (`stillLoading` trong `editorreader.cpp`; `patches.md`, `docs/handoff/P2a.md`).
- `D:\ContextCut` đang được loại khỏi Windows Defender: chỉ tải từ nguồn chính thức. Nhắc Nhan gỡ loại trừ khi xong dự án.

## Giai đoạn

Mỗi giai đoạn chạy trong **một session mới**: đọc ghi chú bàn giao trước, viết kế hoạch `docs/plans/Pn.md`, làm, kiểm cổng, commit, viết `docs/handoff/Pn.md` (đã xong, lệch thiết kế, lệnh, việc dở). Giai đoạn lớn chia nhiều session, mỗi session kết thúc bằng thứ chạy được và một commit. Hỏi Nhan trước khi push.

| GĐ | Nội dung | Trạng thái |
| --- | --- | --- |
| P0 | Nền: repo, build một lệnh, đổi tên tối thiểu, fix Waves | Xong 21/10/2026 (`docs/handoff/P0.md`) |
| P1 | Cầu nối: AiBridgeServer, JSON-RPC, ops cơ bản, MCP server Python | **Xong** 22/10/2026: P1a cầu nối C++ (`docs/handoff/P1a.md`), P1b MCP server + guide (`docs/handoff/P1b.md`), P1c op sửa timeline, một bước undo mỗi đợt, cổng P1 qua với Claude Code (`docs/handoff/P1c.md`, có tóm tắt P1) |
| P2 | Phụ đề chuẩn timing, vision, xuất, `zoom` | **Đang làm**: P2a phiên âm + phụ đề xong (agent chạy trọn transcribe → phụ đề, lưu/mở lại được), cổng đo timing chờ bản ghi OBS + mốc tay của Nhan (`docs/handoff/P2a.md`, `docs/plans/P2.md`); P2b vision, P2c xuất chưa |
| P3 | Dàn ý, `find_moments`, `detect_beats`, `beat_montage` | Chưa |
| P4 | Multi-POV, placeholder, sync | Chưa |
| P5 | Giao diện Dễ, dock Hoạt động AI, zip portable, logo | Chưa |
| P6 | Hiệu ứng, thư viện meme/SFX | Chưa |
| P7 | Series "100 ngày" | Chưa |
