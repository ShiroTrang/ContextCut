# Bàn giao P2b — Xem hình và `zoom`

22/10/2026 · kế hoạch: `docs/plans/P2.md` (P2b = Task 12–19, Review Focus (P2b)) · giao thức: `docs/protocol.md` §8.5 (`zoom`), §8.10 `get_scene`, §8.11 `get_viewer_frame` · session P2b (Claude Opus 5.5). **Code xong, cổng đạt trên dữ liệu thật**; review toàn nhánh là tự review (không chạy agent review riêng).

## Đã xong (commit trên `main` từ `2d55bde96b`, chưa push)

| Việc | Ở đâu |
| --- | --- |
| Ảnh bản ghi gốc bằng ffmpeg, đúng frame MLT hiện kể cả khi fps nguồn khác project (`floor(f·fps_nguồn/fps_project + 0,5)`, seek nửa frame trước), song song ≤ 4, cache theo hash file; contact sheet `xstack` + nhãn `drawtext` | `contextcut-ai/src/contextcut_ai/vision.py`, `media.probe().video` |
| Tool `get_source_frames(recording, frames ≤ 12, on, width)`, `get_contact_sheet(recording, start_f, end_f, on, cols, rows)`: phần chữ JSON + ảnh JPEG, mỗi ảnh cũng là file (đường dẫn trong phần chữ); `on: "timeline"` đổi frame qua clip của bản ghi | `mcp_server.py` |
| Cầu nối `get_scene` (XML MLT của sequence như khi xuất, `projectSceneList`, proxy → file gốc) và `get_viewer_frame` (khung monitor như Extract Frame, JPEG base64, `at_f` dời playhead) | `src/contextcut/model/scenereader.{h,cpp}` |
| `render_frames(frames ≤ 12, width, originals)`: job melt (không khoá GPU), mọi frame trong **một** tiến trình (XML bọc: producer `xml` + playlist mỗi frame một mục), dựng ở cỡ profile rồi ffmpeg thu nhỏ, cache theo sha1 của scene; chờ ≤ 45 s, quá thì trả `job_id` và `get_job` trả ảnh khi xong. Tool `get_viewer_frame` | `render.py`, `analysis/worker.py`, `mcp_server.py` |
| Op `zoom{start_f, end_f, scale, focus_x, focus_y, ramp_in_f, ramp_out_f, ease, track?}`: cắt clip hình ở hai mốc (clip tiếng cắt theo), thêm Transform (`qtblend`) có keyframe `rect` vào mảnh giữa; keyframe do MLT viết (`anim_set`, `cubic_out`…), theo frame producer; một bước undo | `src/contextcut/ops/{opregistry,opvalidator,timelineops}.cpp` |
| `transcript.placements` gộp mảnh liền nhau cả trên timeline lẫn trong nguồn (zoom/split không làm mất từ ở chỗ cắt) | `transcript.py` |
| Guide: bốn tool xem hình, giới hạn ảnh, op `zoom`, mẫu `reaction-zoom` dùng được (xem hình → zoom → tự kiểm), bảng client hiện ảnh; SKILL/AGENTS sinh lại | `contextcut-ai/guide/`, `skills/` |

Test: `uv run --directory contextcut-ai --no-sync pytest` → 220 xanh khi app mở `p1-gate` (sống gồm `test_live_vision.py` 6, `test_live_zoom.py` 6, toàn bộ P1/P2a); không có app thì test sống tự bỏ qua.

## Bằng chứng cổng

Dữ liệu thật: `p1-gate` (720p 25 fps) + `C:\Users\VuNhan\Videos\Gaming.mkv` (HEVC 1080p60, 20,5 phút, 5 track) nhập vào bin, 2 phút đặt lên V1/A1.

| Kiểm | Kết quả |
| --- | --- |
| Ảnh đúng mốc (video mã số frame, 16 ô bit đọc lại từ ảnh) | ffmpeg 60 fps: 8/8 frame đúng; contact sheet đúng ô; `get_scene` → melt, `render_frames`, `get_viewer_frame(at_f)` trong app: đúng số frame (test sống) |
| `get_source_frames` trên Gaming so với `melt` dựng tay | so với melt ở profile 60 fps tại frame nguồn s−1, s, s+1: frame s luôn giống nhất (4/4, vd. 28,4 dB so với 24,2/22,5 dB; nền ~28 dB do hai đường thu nhỏ khác nhau). 5 frame 4,0 s, lần sau 0,00 s (cache) |
| `get_contact_sheet` cả 20 phút | 7,2 s, 12 ô có nhãn giờ đọc được |
| `render_frames` trên timeline có phụ đề (phụ đề thêm bằng `add_subtitles` từ transcript PhoWhisper của P2a) | 3 frame file gốc 8,3 s, lần sau 0,0 s; phụ đề hiện trong ảnh |
| `get_viewer_frame` | 0,08 s, cùng khoảnh khắc với `render_frames` (ảnh proxy) |
| `zoom` → undo trên Gaming | V1 + A1 cắt ở 791/841, Transform ở mảnh giữa; `undo_batch` → timeline, số đếm, chỉ số undo y hệt |
| Claude Code phiên mới (`claude -p`, sonnet): "zoom phản ứng ở 00:18–00:21 (con rồng): xem hình, zoom, tự kiểm" | guide `patterns/reaction-zoom` → `get_source_frames` 7 ảnh → `validate_operations` → `apply_operations` **một đợt** "AI: zoom phản ứng rồng 00:18–00:21" (×1,25, focus 0,38/0,40, vào 5 frame) → `render_frames` 3 frame tự kiểm → báo nhãn + Ctrl+Z (14 lượt, 104 s, 0,34 USD). Ảnh render thấy zoom, phụ đề không bị phóng |

**Client hiện ảnh từ tool MCP** (video in số frame to; agent phải đọc đúng số mà không được nói trước, đáp án 24):

| Client | Kết quả |
| --- | --- |
| Claude Code CLI (`claude -p`, sonnet) | **Có**: `SỐ=24` (3 lượt, 0,11 USD) |
| Codex CLI (`codex exec`, gpt-5.6-terra, gói free) | **Có**: `SỐ=24`; tool chỉ đọc chạy được ở `exec` |
| Claude Desktop | Chưa thử: máy chưa có `claude_desktop_config.json` (chưa đăng ký server) |
| Antigravity | Chưa thử: đã đăng ký server (`~/.gemini/config/mcp_config.json`), chỉ thử được qua giao diện |

## Lệch thiết kế / kế hoạch

1. Tool xem hình **không đòi lưu project**: project chưa lưu thì ảnh vào `%LOCALAPPDATA%\contextcut\frames\` (transcript vẫn đòi lưu).
2. Tool xem hình không ghi `recordings.json` (tool chỉ đọc): ffprobe + hash nhanh một lần mỗi file trong tiến trình server.
3. `render_frames` dựng ở cỡ profile rồi thu nhỏ bằng ffmpeg (không dùng `width/height` của consumer melt, xem Bẫy). File ảnh `%04d` thay `%03d`.
4. Test sống chạy trên `p1-gate` (nhập video mã số frame bằng `import_media` rồi hoàn tác), không làm project `p2-gate` riêng.
5. Mảnh zoom: `created` = `[id clip mang zoom]` (không liệt kê các mảnh cắt ra).

## Bẫy mới

- **melt + scene Kdenlive + consumer có `width`/`height`**: thiếu `progressive=1` thì melt crash (0xC0000005, ổn định); có `progressive=1` vẫn chừa viền đen 16 px mỗi bên khi nguồn lớn hơn profile (transition `qtblend` Kdenlive dùng để ghép track; tái hiện tối thiểu trong `tests/test_render.py`). Dựng ở cỡ profile rồi thu nhỏ.
- argv của melt trên Windows không giữ chữ có dấu: chạy melt với `cwd` = thư mục làm việc, đối số chỉ ASCII; đường dẫn có dấu nằm trong file XML (UTF-8).
- Keyframe trong XML scene có thể ghi theo đồng hồ (`00:00:00.400h=…`) thay số frame: consumer xml của Kdenlive đặt `time_format=clock` khi Kdenlive đã đọc lại animation. MLT đọc được cả hai.
- `p1-gate` bật proxy (`generateproxy` = 1): nhập file ≥ 1000 px vào đó làm Kdenlive tự thêm bước undo "Add proxy clip" sau đợt `import_media`, nên `undo_batch` đợt nhập bị `conflict`. Test sống chỉ nhập file nhỏ (640×360).
- Nhãn `drawtext`: chạy ffmpeg với `cwd` = `%WINDIR%\Fonts`, `fontfile=arial.ttf` (khỏi thoát dấu `:` của ổ đĩa).
- `MonitorProxy::extractFrame` lấy frame từ producer của monitor trên luồng giao diện; đang phát thì có thể làm nhảy một frame phát lại.

## Việc tiếp / dở

1. Nhan: thử Claude Desktop và Antigravity hỏi "Gọi get_source_frames … đọc con số trong ảnh" rồi điền bảng (guide `software.md`, mục Xem hình).
2. Nhỏ, để sau: `get_viewer_frame` có thể báo `position_f = at_f` dù Kdenlive bỏ qua lệnh seek (đang đổi monitor); `zoom` chưa từ chối clip đổi tốc độ (keyframe tính theo tốc độ 1); XML bọc của `render_frames` giả định pixel vuông.
3. Nhắc Nhan: chạy lại `uv run --directory contextcut-ai python scripts/register_clients.py` (skill đã cài còn bản cũ); gỡ `D:\ContextCut` khỏi loại trừ Defender khi xong dự án.
4. P2c: `export` (job, NVENC → x264, ffprobe) dùng lại `get_scene` (thêm consumer như `RenderRequest`), `open_project`.
