# ContextCut — Kiến trúc v3

Oct 21, 2026 · @Nhan

## Tổng quan

ContextCut là phần mềm dựng video desktop cho Windows, fork từ mã nguồn mở Kdenlive. Nó thêm hai thứ Kdenlive không có: **giao diện Dễ** cho người không chuyên, và **cầu nối AI** để Claude chỉnh trực tiếp timeline đang mở, nhìn được khung hình kết quả và tự sửa.

Cách dùng: bạn mở app, kéo video gameplay vào, rồi chat với Claude trong Claude Desktop hoặc Claude Code. Mọi thay đổi AI làm hiện ngay trên timeline và undo được như thao tác tay.

**Nguyên tắc cốt lõi:**

- **Một timeline, hai người sửa.** Bạn và AI đi qua cùng mô hình timeline và cùng undo stack của Kdenlive.
- **Một engine.** MLT dựng cả preview lẫn file xuất, nên thứ bạn xem chính là thứ được xuất.
- **Chỉ thao tác đã đăng ký.** AI không chạy lệnh tùy ý, không sửa file gốc.
- **Nhìn rồi mới tin.** Sau mỗi đợt sửa, AI render khung hình kết quả để tự kiểm tra.
- **Fork mỏng.** Code mới tách riêng, sửa file gốc Kdenlive ít nhất có thể để cập nhật theo bản chính thức.
- **Dễ trước, mạnh sau.** Mặc định là giao diện Dễ; công tắc Pro mở lại toàn bộ Kdenlive.

**Thay đổi so với v2:**

| Hạng mục | v2 | v3 |
| --- | --- | --- |
| Sản phẩm | MCP server + engine, không có giao diện | App dựng video đầy đủ, fork Kdenlive |
| Chỉnh tay | Mở project bằng Kdenlive cài riêng | Ngay trong ContextCut |
| Engine | FFmpeg render; MLT chỉ khi xuất project | MLT cho preview và xuất (NVENC qua MLT) |
| Nguồn sự thật | `project.json` riêng | Timeline của app (`.kdenlive`) + thư mục metadata đi kèm |
| Cách AI sửa | Ghi JSON rồi render lại | Sửa timeline đang mở, hiện ngay, undo được |
| Vision | Keyframe từ video gốc | Thêm khung hình của timeline đã dựng và contact sheet |
| Ngôn ngữ | Python | C++/Qt (app) + Python (AI, phân tích) |
| Khung chat AI | Không | Vẫn không; thêm dock **Hoạt động AI** để xem và duyệt |
| Exporter Kdenlive | Giai đoạn P4 | Bỏ, vì `.kdenlive` đã là định dạng gốc |

## Kiến trúc

&#91;embedded content: kiến trúc v3 · app, dịch vụ AI, engine\]

Bạn thao tác qua giao diện, Claude thao tác qua MCP và cầu nối; cả hai đổ vào cùng mô hình timeline của Kdenlive, nên undo, lưu và preview hoạt động giống hệt nhau. Dịch vụ Python lo phân tích nặng và nói chuyện với Claude; app C++ lo mọi thứ thuộc về timeline và hình ảnh.

## Fork Kdenlive

Kdenlive đã có sẵn phần khó nhất của một editor; ContextCut chỉ thêm phần còn thiếu và giữ phần thêm tách khỏi code gốc.

**Dùng lại từ Kdenlive:** timeline đa track và nhiều sequence, undo/redo, keyframe, proxy clip tự động, monitor preview, render bằng MLT (có profile NVENC), track phụ đề, nhận dạng giọng nói và chỉnh theo transcript, marker/guide có màu, import/export OpenTimelineIO, tách nền bằng SAM2.

**ContextCut thêm:**

| Module | Việc | Mức sửa code gốc |
| --- | --- | --- |
| AI Bridge | Server WebSocket local trong app, nhận lệnh từ MCP, chạy trên luồng giao diện | Thêm mới; một hook lúc khởi động |
| Ops adapter | Dịch ContextCut ops sang lệnh của mô hình timeline (ví dụ `requestClipMove`, `requestClipInsertion`, `requestItemResize`); gói mỗi đợt thành một bước undo có nhãn "AI: …" | Thêm mới; gọi API nội bộ |
| Vision | Render khung hình và contact sheet từ timeline bằng MLT | Thêm mới |
| Giao diện Dễ | Layout, thanh công cụ rút gọn, wizard lần đầu, preset | Chủ yếu file `.rc`/layout, ít C++ |
| Dock Hoạt động AI | Danh sách đợt sửa, nhảy tới vị trí, Giữ/Hoàn tác | Thêm mới |
| Thương hiệu | Tên, icon, thư mục cấu hình riêng | Sửa nhỏ |

Tên hàm trong bảng là ví dụ từ mô hình timeline của Kdenlive; cần đối chiếu lại với mã nguồn lúc fork.

**Quy tắc fork mỏng:**

- Code mới nằm trong `src/contextcut/`; mỗi chỗ buộc phải sửa file gốc được ghi vào `patches.md`.
- Cập nhật theo mỗi bản phát hành KDE Gear (tháng 4, 8, 12), không bám nhánh master hằng ngày.
- Không đổi định dạng `.kdenlive`: project vẫn mở được bằng Kdenlive gốc; dữ liệu AI nằm ở thư mục đi kèm.
- Đổi tên app và thư mục cấu hình để cài song song với Kdenlive mà không xung đột; không dùng tên hay logo Kdenlive cho sản phẩm.

**Giấy phép:** Kdenlive dùng GPL (phiên bản 2 hoặc 3, theo quy ước của KDE). Dùng cá nhân thì không vướng gì. Nếu phát hành hay bán, bản fork phải giữ GPL và công bố mã nguồn, kể cả phần bạn viết thêm trong app. Phần Python chạy thành tiến trình riêng nên có thể cấp phép tách, nhưng cần hỏi người có chuyên môn trước khi dựa vào điểm này.

**Build trên Windows:** dùng KDE Craft, hiện hướng dẫn dùng trình biên dịch MinGW; nhóm Kdenlive đang chuyển MLT sang build được bằng MSVC. Lần build đầu Craft tải và biên dịch cả Qt, KDE Frameworks, MLT và FFmpeg, nên dự kiến mất nhiều giờ và nhiều dung lượng ổ đĩa; đặt thư mục Craft trên ổ dữ liệu lớn và bật ccache để các lần sau nhanh hơn.

## Giao diện Dễ

App mở mặc định ở chế độ Dễ: năm vùng, chữ tiếng Việt, nút lớn cho việc hay làm. Chế độ Pro là Kdenlive đầy đủ, bật bằng một công tắc.

&#91;embedded content: mô phỏng chế độ Dễ · năm vùng\]

Khi bạn chọn một clip, cột bên phải chuyển sang tab Thuộc tính; marker vàng là phản ứng, marker xám là beat, đều do AI đánh dấu.

| Vùng | Có gì | Ẩn so với Kdenlive (còn trong Pro) |
| --- | --- | --- |
| Thanh công cụ | Nhập video · Phụ đề tự động · Trạng thái kết nối AI · Xuất YouTube · công tắc Dễ/Pro | Menu dài, thanh nhiều icon |
| Media | Kéo thả, tự tạo proxy, tự tách track mic/game nếu file có nhiều track audio | Thư mục, tag, thuộc tính clip chi tiết |
| Viewer | Một màn hình preview, khung an toàn, lớp hiển thị vùng cấm | Monitor clip/project tách đôi |
| Timeline | Track đặt tên sẵn (Phụ đề, Chữ, Video, Mic, Game, Nhạc/SFX), marker AI theo màu | Chế độ chỉnh nâng cao, công cụ trim chuyên sâu |
| Hoạt động AI | Các đợt sửa của AI, lý do, nút nhảy tới, Giữ/Hoàn tác | — |
| Thuộc tính | Vài tham số hay dùng của clip đang chọn; hiệu ứng dạng preset | Effect stack đầy đủ |

**Vùng cấm:** mỗi game có một preset ghi vị trí facecam, minimap, killfeed. Bạn kéo khung trên một frame mẫu một lần; sau đó validator từ chối mọi chữ, sticker hay phụ đề đặt đè lên các vùng này, kể cả khi do AI đặt.

**Lần đầu mở app (wizard):**

1. Chọn ngôn ngữ giao diện (mặc định tiếng Việt).
2. Kiểm tra GPU và NVENC, chọn preset dự án "YouTube 1080p60".
3. Tải model nhận dạng giọng nói, có thanh tiến độ.
4. Tạo preset game đầu tiên và vẽ vùng cấm.
5. Thêm ContextCut vào cấu hình MCP của Claude Desktop (hỏi trước khi ghi file).

**Preset sẵn có:** xuất "YouTube 1080p60 NVENC"; 3–4 kiểu phụ đề (karaoke, viền đậm, gaming); hiệu ứng zoom, rung, chữ pop dạng một cú bấm; bộ SFX có giấy phép rõ ràng.

**Thói quen người dùng:** tuỳ chọn bộ phím tắt kiểu CapCut, snap bật sẵn, tự lưu định kỳ. KDE có sẵn hệ thống dịch; cần kiểm tra độ phủ bản tiếng Việt của Kdenlive và dịch nốt các chuỗi trong chế độ Dễ trước.

## AI chỉnh trực tiếp và nhìn video

Claude không sửa file; nó gửi thao tác vào app đang mở qua cầu nối. Mỗi đợt thao tác là một bước undo có nhãn và hiện ngay trên timeline.

**Một yêu cầu đi như sau:**

1. Bạn chat: "zoom vào chỗ mình la lên ở phút 12".
2. Claude gọi `get_editor_state` (playhead, vùng chọn, preset game) và `get_context` quanh phút 12.
3. Claude xem hình gốc bằng `get_contact_sheet`, rồi `get_source_frames` ở mốc chính xác.
4. Claude gửi `apply_operations` với nhãn "AI: zoom phản ứng 12:03". Timeline cập nhật ngay.
5. Claude gọi `render_frames` tại các điểm vừa sửa để tự kiểm tra: zoom có đúng người, chữ có che vùng cấm không. Sai thì sửa tiếp.
6. Đợt sửa hiện trong dock Hoạt động AI; bạn bấm Giữ, Hoàn tác, hoặc Ctrl+Z như bình thường.

**Cầu nối (AI Bridge):**

- WebSocket chỉ nghe `127.0.0.1`; token ngẫu nhiên lưu trong thư mục cấu hình người dùng, MCP server đọc token để kết nối.
- Giao thức JSON-RPC. Mỗi lệnh sửa kèm `base_revision`; nếu bạn vừa sửa đúng vùng đó, app từ chối và AI đọc lại timeline.
- Lệnh chạy tuần tự trên luồng giao diện. Khi AI đang sửa, thanh trạng thái hiện "AI đang sửa…" kèm nút Dừng.
- App chưa mở thì MCP trả lỗi rõ ràng: "Mở ContextCut trước".

**Hai chế độ:**

- **Duyệt (mặc định):** mỗi đợt sửa chờ bạn Giữ hoặc Hoàn tác; marker của đợt chưa duyệt có màu riêng. Với thay đổi lớn như cắt bỏ nhiều phút, AI dựng trên một sequence bản sao để bạn so sánh trước.
- **Tự động:** AI giữ luôn các đợt sửa, chỉ dừng hỏi khi cắt bỏ vượt ngưỡng hoặc trước khi xuất file.

**AI nhìn được gì:**

| Tool | Ảnh trả về | Dùng khi | Token ước tính |
| --- | --- | --- | --- |
| `get_contact_sheet` | Lưới 4×3 thumbnail của một đoạn | Lướt nhanh đoạn dài | \~600 mỗi lưới 1024×432 |
| `get_source_frames` | Khung hình video gốc tại các mốc | Hiểu chuyện gì xảy ra trong game | \~200 mỗi ảnh 512×288 |
| `render_frames` | Khung hình của timeline đã dựng, cùng engine với file xuất | Tự kiểm tra sau khi sửa | \~200 mỗi ảnh |
| `get_viewer_frame` | Khung hình bạn đang xem ở playhead | Bàn về "chỗ này" với bạn | \~200 |

Token ước theo công thức ảnh ≈ rộng × cao / 750. App tự thu nhỏ ảnh và giới hạn 8–12 ảnh mỗi lần gọi. Dùng qua Claude Desktop thì ảnh trừ vào hạn mức gói Pro, không tốn tiền API.

## Cấu trúc repository

Hai repo: app C++ (fork Kdenlive) và dịch vụ AI bằng Python. Hai bên nói chuyện qua WebSocket, nên có thể build và test riêng.

```text
contextcut/                    # fork của invent.kde.org/multimedia/kdenlive
├── src/                       # mã Kdenlive gốc, sửa ít nhất có thể
│   └── contextcut/            # toàn bộ code mới, tách riêng để dễ cập nhật upstream
│       ├── bridge/            # AiBridgeServer (QWebSocketServer), JSON-RPC, token
│       ├── ops/               # ops → lệnh mô hình timeline, gói undo có nhãn
│       ├── vision/            # render frame, contact sheet bằng MLT
│       ├── easymode/          # layout Dễ, thanh công cụ, wizard, vùng cấm
│       └── activity/          # dock Hoạt động AI
├── data/contextcut/           # layout, file .rc rút gọn, preset xuất, style phụ đề
├── patches.md                 # danh sách mọi chỗ sửa vào file gốc
└── craft/                     # blueprint Craft để build bản fork

contextcut-ai/                 # Python
├── pyproject.toml             # pin phiên bản mcp SDK
├── src/contextcut_ai/
│   ├── mcp_server.py          # stdio; Claude kết nối vào đây
│   ├── bridge_client.py       # WebSocket tới app đang mở
│   ├── schemas/               # ops, context, job (Pydantic)
│   ├── analysis/              # speech, scenes, silence, reactions, beats, context_map
│   └── jobs.py                # job nền + trạng thái
├── skills/
│   ├── contextcut-editor/SKILL.md
│   └── styles/                # gaming.md, commentary.md, shorts.md…
└── tests/
```

Mỗi dự án video là một file `.kdenlive` bình thường cộng một thư mục đi kèm:

```text
MyVideo.kdenlive              # timeline, mở được cả bằng Kdenlive gốc
MyVideo.contextcut/
├── transcript.json           # lời nói theo từng từ
├── context.json              # cảnh, phản ứng, beat, khoảng lặng
├── ai_log.jsonl              # mọi đợt sửa của AI, lý do, trạng thái duyệt
├── game_preset.json          # vùng cấm
└── cache/                    # audio tách, keyframe, contact sheet
```

## MCP tools

Khoảng 20 tool chia năm nhóm. Tool phân tích và xuất chạy nền, trả `job_id` ngay; Claude gọi `get_job` để theo dõi.

| Nhóm | Tool | Việc | Giai đoạn |
| --- | --- | --- | --- |
| Editor | `get_editor_state()` | Project đang mở, fps, playhead, vùng chọn, preset game, revision | P1 |
| Editor | `get_timeline(start?, end?)` | Track, clip, hiệu ứng, marker; có phân trang | P1 |
| Editor | `open_project(path)`, `import_media(path)` | Mở dự án, nhập video vào Media | P1 |
| Phân tích | `transcribe(language)` | Job → transcript theo từng từ | P2 |
| Phân tích | `detect_scenes`, `detect_silence`, `detect_reactions`, `detect_beats` | Job → sự kiện, hiện thành marker trên timeline | P4 |
| Phân tích | `get_context(start?, end?)`, `get_job(job_id)` | Đọc context map; theo dõi job | P2 |
| Vision | `get_contact_sheet`, `get_source_frames`, `render_frames`, `get_viewer_frame` | Ảnh trả về dạng image content | P2 |
| Chỉnh sửa | `list_operations()` | Danh mục thao tác + schema tham số | P1 |
| Chỉnh sửa | `validate_operations(ops)` | Báo lỗi/cảnh báo, không đổi gì | P1 |
| Chỉnh sửa | `apply_operations(ops, base_revision, label)` | Một đợt sửa = một bước undo; trả `batch_id` | P1 |
| Chỉnh sửa | `undo_batch(batch_id)`, `get_batch_status(batch_id)` | Hoàn tác; xem bạn đã Giữ hay Hoàn tác | P5 |
| Chỉnh sửa | `add_markers(markers[])` | Đánh dấu điểm cần bạn xem | P1 |
| Đầu ra | `add_subtitles(style)` | Đưa transcript vào track phụ đề | P2 |
| Đầu ra | `export(preset, range?)` | Job → file MP4, kiểm tra bằng ffprobe sau khi xuất | P2 |

**Quy ước chung:**

- Kết quả lớn (timeline, transcript, context) luôn lấy theo đoạn `start`/`end` để không tràn context của Claude.
- `apply_operations` bắt buộc `base_revision` và `label`; nhãn hiện trong lịch sử undo và dock Hoạt động AI.
- Kết quả phân tích vừa được lưu vào `MyVideo.contextcut/`, vừa đẩy vào app thành marker để bạn cũng thấy.
- Xuất file và cắt bỏ vượt ngưỡng cần bạn xác nhận; quy tắc này nằm cả trong skill lẫn trong app.

**Workflow điển hình:** `get_editor_state` → `transcribe` + `detect_reactions` + `detect_beats` → `get_context` → `get_contact_sheet` ở đoạn đáng chú ý → `apply_operations` → `render_frames` tự kiểm tra → bạn duyệt trong app → `export`.

## Pipeline phân tích

Phân tích chạy trong dịch vụ Python, biến video thô thành một context map có timestamp; các model chạy tuần tự và giải phóng VRAM sau mỗi bước. Kdenlive đã có nhận dạng giọng nói riêng, nhưng ContextCut dùng bản của mình để chọn được model tiếng Việt và lấy timestamp theo từng từ.

### Audio

1. FFmpeg trích audio mono 16 kHz WAV vào `cache/audio.wav`.
2. ASR bằng faster-whisper với `word_timestamps=True` và `vad_filter=True`.
   - Tiếng Việt: `large-v3` ở `int8_float16`, hoặc bản PhoWhisper đã chuyển sang CTranslate2. Đo WER trên fixtures trước khi chọn mặc định.
   - Tiếng Anh/Nhật: `large-v3` hoặc `large-v3-turbo`.
   - Truyền `initial_prompt` chứa tên riêng, thuật ngữ do người dùng cung cấp để giảm lỗi chính tả.
3. Hậu xử lý: gộp từ thành câu, sửa dấu câu, đánh dấu từ có xác suất thấp để AI hoặc người dùng kiểm tra.
4. Phát hiện khoảng lặng bằng Silero VAD hoặc `silencedetect` của FFmpeg.
5. Tùy chọn sau này: WhisperX cho diarization (cần model wav2vec2 tiếng Việt cho alignment), detector tiếng cười.

### Video

1. `ffprobe` lấy FPS dạng hữu tỉ (`30000/1001`), độ phân giải, thời lượng, stream.
2. PySceneDetect (`AdaptiveDetector`) tìm điểm cắt cảnh, lưu theo số frame.
3. Proxy cho preview do Kdenlive tạo và quản lý; phân tích đọc thẳng file gốc hoặc audio đã tách.
4. Keyframe chỉ trích khi được yêu cầu: giữa mỗi cảnh, tại điểm cắt, và tại các mốc lời thoại AI muốn xem.

### Tín hiệu riêng cho gaming

- **Track riêng:** nếu file OBS có nhiều track audio, dùng track mic cho ASR và phản ứng, track game cho sự kiện. Nếu chỉ có track trộn, tách giọng bằng Demucs theo từng đoạn trước khi ASR.
- **Phản ứng (`detect_reactions`):** đỉnh âm lượng đột ngột trên track mic (la hét, cười) cộng đoạn nói dày; mỗi phản ứng thành một marker vàng.
- **Beat (`detect_beats`):** librosa tìm nhịp trên track nhạc để cắt montage đúng nhịp; mỗi beat mạnh thành một marker xám.
- **VOD dài:** mọi bước chạy theo chunk, có cache theo hash file và tiếp tục được khi bị ngắt.

### Context map

`context.json` là danh sách sự kiện thống nhất, sắp theo thời gian:

```json
{
  "schema_version": "1",
  "timebase": {"num": 30000, "den": 1001},
  "events": [
    {"type": "speech", "start_f": 63, "end_f": 141,
     "text": "...", "words": [{"w": "...", "start_f": 63, "end_f": 72, "p": 0.93}],
     "speaker": null},
    {"type": "scene_cut", "at_f": 144},
    {"type": "silence", "start_f": 141, "end_f": 210}
  ]
}
```

`p` là xác suất do ASR trả về; trường nào không có nguồn đáng tin thì để `null`. Sự kiện `reaction` và `beat` có cùng dạng `at_f`/`strength`. Mô tả hình ảnh không nằm ở đây: Claude tự xem ảnh qua các tool vision.

## Timeline và thao tác

Nguồn sự thật là timeline đang mở trong app; AI không giữ bản sao riêng. ContextCut ops là "ngôn ngữ" Claude dùng, Ops adapter dịch sang lệnh Kdenlive. Mọi thời gian là số frame nguyên theo fps của project.

Ví dụ một đợt sửa (project 60 fps, phút 12:03 = frame 43380):

```json
{"method": "apply_operations",
 "params": {
  "base_revision": 42,
  "label": "AI: zoom phản ứng 12:03",
  "ops": [
   {"type": "zoom", "track": "Video", "start_f": 43380, "end_f": 43410,
    "from": 1.0, "to": 1.2, "ease": "out", "focus": {"x": 0.62, "y": 0.40}},
   {"type": "add_sfx", "asset": "sfx/boom_01.wav", "at_f": 43380, "gain_db": -6},
   {"type": "overlay_text", "text": "CÁI GÌ VẬY?!", "style": "gaming_pop",
    "start_f": 43380, "end_f": 43500, "position": "center_top"}
  ]}}
```

| Operation | Tham số chính | Thực hiện trong Kdenlive |
| --- | --- | --- |
| `cut_range` | `start_f`, `end_f` | Cắt và xóa ripple trên mọi track |
| `split` | `clip_id`, `at_f` | Cắt clip tại frame |
| `trim` | `clip_id`, `in_f`, `out_f` | Đổi độ dài clip |
| `move` | `clip_id`, `track`, `at_f` | Di chuyển clip |
| `zoom` | `start_f`, `end_f`, `from`, `to`, `ease`, `focus` | Hiệu ứng Transform có keyframe |
| `overlay_text` | `text`, `style`, `start_f`, `end_f`, `position` | Title clip trên track Chữ |
| `overlay_media` | `asset`, `start_f`, `end_f`, `position`, `scale` | Clip trên track Chữ + Transform |
| `add_transition` | `between`, `type`, `duration_f` | Mix hoặc composition giữa hai clip |
| `add_sfx` | `asset`, `at_f`, `gain_db` | Clip audio trên track Nhạc/SFX |
| `duck_music` | `start_f`, `end_f`, `depth_db` | Keyframe âm lượng track nhạc |
| `set_speed` | `clip_id`, `factor` | Đổi tốc độ clip |
| `reframe` | `aspect`, `focus` | Sequence mới đổi tỉ lệ + Transform |

**Validator kiểm tra trước khi áp dụng:** frame nằm trong nguồn; không chồng clip trên cùng track; thao tác có trong registry và tham số trong khoảng cho phép; không đặt chữ/sticker vào vùng cấm; `cut_range` không xóa quá ngưỡng lời thoại khi chưa xác nhận; asset ngoài có thông tin giấy phép.

**Một đợt là một khối:** nếu một op lỗi giữa chừng, cả đợt được hoàn tác và trả lỗi kèm vị trí op. Đợt thành công tăng `revision`, ghi vào `ai_log.jsonl` (nhãn, lý do, danh sách op, trạng thái duyệt) và hiện trong dock Hoạt động AI.

## Preview và xuất bằng MLT

Một engine cho mọi thứ: MLT phát preview trong app, render file xuất và render khung hình cho AI tự kiểm tra. Vì vậy không còn rủi ro preview lệch file xuất như phương án FFmpeg ở v2.

- **Preview:** Kdenlive tự tạo proxy khi video nặng; bạn chỉnh trên proxy, lúc xuất dùng file gốc.
- **Xuất:** preset "YouTube 1080p60 NVENC" (`h264_nvenc` qua consumer avformat của MLT), tự rơi về `libx264` nếu GPU lỗi. Sau khi xuất, dịch vụ AI kiểm tra thời lượng, số stream và độ lệch audio/video bằng ffprobe.
- **Khung hình cho AI:** `render_frames` dùng chính timeline đang mở, render từng frame qua MLT ra ảnh nhỏ, cùng engine và cùng hiệu ứng với file xuất.
- **Phụ đề:** transcript được đưa vào track phụ đề của Kdenlive. Font có đủ dấu tiếng Việt (Be Vietnam Pro, Inter, Noto Sans) đóng gói cùng app. Ngắt dòng khoảng 32–42 ký tự với 16:9 và theo khoảng nghỉ trong lời nói.
- **Rủi ro karaoke:** tô màu từng từ cần tag ASS (như `\k`). Phải thử xem track phụ đề của Kdenlive có giữ các tag này khi chỉnh tay không; nhóm Kdenlive cũng đang có kế hoạch làm lại hệ thống phụ đề. Nếu không giữ được, phương án dự phòng là sinh file ASS riêng, gắn bằng filter phụ đề của MLT trên một track riêng và chỉ chỉnh qua AI.

## Skills và phong cách dựng

Phong cách là văn bản hướng dẫn cho AI, không phải code. Một skill chung quy định workflow; mỗi phong cách là một file quy tắc ngắn mà skill chung tham chiếu.

**`skills/contextcut-editor/SKILL.md` gồm:**

1. Workflow: phân tích → đọc context → xem contact sheet ở điểm đáng chú ý → chọn phong cách → viết ops → validate → apply → render\_frames tự kiểm tra → chờ bạn duyệt → xuất.
2. Cách chọn phong cách: dựa trên yêu cầu người dùng trước, nội dung video sau; luôn nói rõ phong cách đã chọn và lý do trong một câu.
3. Nguyên tắc biên tập: giữ nguyên ý người nói; không bịa lời thoại hay sự kiện chưa xem; hiệu ứng chỉ khi làm rõ, tạo nhịp hoặc nhấn mạnh; ít hiệu ứng khi không chắc.
4. An toàn: chỉ dùng operation trong `list_operations`; xác nhận trước khi cắt đoạn dài, dùng asset ngoài hoặc render final.

**Phong cách khởi đầu** (mỗi cái một file trong `skills/styles/`):

| Phong cách | Dấu hiệu | Mặc định |
| --- | --- | --- |
| Commentary / talking-head | Một người nói trước camera | Cắt khoảng lặng > 0,6 s, phụ đề karaoke, punch-in ở câu nhấn |
| Gaming / meme | Gameplay + phản ứng | Nhấn phản ứng bằng zoom + SFX, cắt đoạn chết, text pop |
| Tutorial | Giải thích, màn hình | Phụ đề rõ, chậm; highlight vùng màn hình; không meme |
| Shorts 9:16 | Nguồn ngắn hoặc yêu cầu dọc | Reframe, hook 3 giây đầu, phụ đề lớn giữa màn hình |
| Cinematic / vlog | Ít lời, nhiều cảnh | Giữ nhịp, chuyển cảnh mềm, nhạc nền + duck |

Ngưỡng trong bảng là điểm bắt đầu để tinh chỉnh, không phải hằng số. Người dùng luôn ghi đè được ("gameplay nhưng đừng dùng meme").

**Chế độ Duyệt/Tự động** được mô tả ở phần AI chỉnh trực tiếp. Skill gaming mặc định dùng Duyệt, luôn đọc vùng cấm từ `get_editor_state` trước khi đặt chữ, và nhắc bạn rằng nhạc trong game có thể dính Content ID.

## Môi trường build và cài đặt

Hai môi trường tách biệt: KDE Craft để build app C++, `uv` cho dịch vụ AI Python. Máy đích: Windows 10/11, RTX 3060 Mobile 6 GB.

| Phần | Công cụ | Ghi chú |
| --- | --- | --- |
| App | KDE Craft kéo Qt, KDE Frameworks, MLT, FFmpeg | Các bản Kdenlive gần đây dùng Qt6; đọc `dev-docs/` của repo khi clone vì yêu cầu phiên bản đổi theo từng bản phát hành |
| Trình biên dịch | MinGW theo hướng dẫn Craft hiện tại | Theo dõi việc chuyển sang MSVC của nhóm Kdenlive |
| Tăng tốc build | ccache, Ninja |  |
| IDE | Qt Creator hoặc VS Code + CMake Tools | Qt Creator debug Qt/QML dễ hơn |
| Dịch vụ AI | Python 3.11, `uv`, `mcp[cli]` (pin phiên bản), `pydantic`, `websockets` |  |
| Phân tích | `faster-whisper`, `scenedetect`, `librosa`, `demucs` (tùy chọn) | CUDA 12 + cuDNN cho GPU |

**Thứ tự dựng môi trường:**

1. Cài Craft, đặt thư mục gốc ở ổ dữ liệu lớn.
2. Build Kdenlive gốc trước và chạy thử, để chắc môi trường ổn định.
3. Trỏ blueprint trong `craft/` sang repo fork, build lại, đổi tên app.
4. Dựng dịch vụ AI:

```powershell
uv init contextcut-ai --python 3.11
cd contextcut-ai
uv add "mcp[cli]" pydantic websockets
uv add --optional analysis faster-whisper scenedetect librosa
```

**Kết nối Claude Desktop** (wizard tự thêm sau khi bạn đồng ý):

```json
{"mcpServers": {"contextcut": {
  "command": "uv",
  "args": ["run", "--directory", "D:/contextcut-ai", "contextcut-mcp"]
}}}
```

App ghi cổng và token của cầu nối vào file trong thư mục dữ liệu người dùng mỗi lần khởi động; MCP server đọc file đó để kết nối.

**Ngân sách VRAM 6 GB:** mỗi lúc chỉ một job dùng GPU nặng (ASR, Demucs, SAM2, xuất NVENC); các job khác xếp hàng. `large-v3` ở int8 chiếm khoảng 3–4 GB khi chạy và được giải phóng ngay sau job.

**Đóng gói:** Craft tạo được installer Windows cho app. Dịch vụ AI đi kèm dưới dạng môi trường Python do `uv` quản lý; model tải trong wizard lần đầu, không nhét vào installer.

## Bảo mật, chi phí, giấy phép

Cầu nối AI là một cửa vào app đang chạy trên máy bạn, nên mọi giới hạn phải tự cài; MCP không có sandbox sẵn.

**Bảo mật**

- Cầu nối chỉ nghe `127.0.0.1`, bắt buộc token; token đổi mỗi lần app khởi động.
- Cầu nối chỉ nhận thao tác trong registry; không có lệnh nào chạy shell, đọc file tùy ý hay ghi đè file gốc.
- `import_media` chỉ nhận đuôi file media; đường dẫn được resolve và kiểm tra symlink.
- Giới hạn kích thước kết quả trả về và số ảnh mỗi lần gọi.
- Xuất file, cắt bỏ vượt ngưỡng và dùng asset ngoài cần bạn xác nhận trong app.

**Chi phí**

- ASR, phân tích, render đều chạy local: không tốn tiền API.
- Claude dùng qua Claude Desktop/Claude Code nên trừ vào hạn mức gói Pro. Ảnh vision tốn hạn mức nhanh nhất, vì vậy ưu tiên contact sheet trước rồi mới xem từng frame.
- Cache mọi kết quả phân tích theo hash file nguồn.

**Giấy phép và bản quyền**

- App là bản fork GPL: phát hành thì phải công bố mã nguồn (xem phần Fork Kdenlive).
- Không dùng tên, logo Kdenlive hay KDE cho sản phẩm; ghi rõ "dựa trên Kdenlive" trong hộp About.
- Thư viện asset có `manifest.json` ghi nguồn và giấy phép từng nhạc, SFX, font; validator từ chối asset thiếu thông tin.
- Không tự tải tài nguyên từ web.

## Lộ trình triển khai

Tổng khoảng 14–16 tuần (3,5–4 tháng) cho một người làm bán thời gian cùng AI coding agent. Sau P2 bạn đã có công cụ dùng thật: Claude tự thêm phụ đề và cắt ghép ngay trong app.

&#91;embedded content: lộ trình v3 · 7 giai đoạn, mỗi giai đoạn một cổng\]

Rủi ro lớn nhất nằm ở P0–P1: dựng được môi trường build Kdenlive trên Windows và gọi được mô hình timeline từ cầu nối. Nếu P1 qua cổng, phần còn lại chủ yếu là viết thêm thao tác và giao diện. Ước lượng thời gian để lập kế hoạch, không phải cam kết; chưa quen C++/Qt thì P0–P1 có thể kéo dài gấp đôi.

## Kiểm thử

Lỗi kỹ thuật được kiểm tự động; chất lượng biên tập được đánh giá bằng mẫu cố định và cảm nhận của bạn.

**Bộ fixtures** (`tests/fixtures/`, mỗi video 30–90 giây, có transcript chuẩn gõ tay): talking-head tiếng Việt, talking-head tiếng Anh, gameplay có phản ứng, tutorial quay màn hình, video nhiều người nói, video ít lời có nhạc.

| Hạng mục | Cách đo | Ngưỡng ban đầu |
| --- | --- | --- |
| Độ chính xác ASR | WER so với transcript chuẩn | Đo trước, đặt ngưỡng sau |
| Đồng bộ phụ đề | Lệch đầu/cuối từ so với mốc gõ tay | Trung vị dưới 100 ms |
| Giữ nội dung | So transcript trước/sau khi cắt | Không mất câu ngoài phần cố ý cắt |
| Cầu nối | Mỗi op: apply rồi undo, so timeline trước/sau | Timeline trở về y hệt |
| Xung đột | Sửa tay đúng lúc AI gửi đợt sửa | Đợt bị từ chối, timeline không hỏng |
| Vùng cấm | Thử đặt chữ đè facecam/HUD | Validator luôn từ chối |
| Đồng bộ A/V | ffprobe trên file xuất | Dưới 1 frame |
| Tương thích | Mở `.kdenlive` của ContextCut bằng Kdenlive gốc | Mở được, timeline giống |
| Cập nhật upstream | Rebase lên bản KDE Gear mới, chạy toàn bộ test | Xong trong 1–2 ngày |
| Dễ dùng | Người chưa từng dùng Kdenlive tự làm một video có phụ đề | Dưới 15 phút, không cần hỏi |
| Tài nguyên | Thời gian xử lý, VRAM đỉnh | Không tràn VRAM trên 6 GB |
| Chất lượng dựng | Bạn chấm 1–5 theo nhịp, độ hợp ngữ cảnh, độ "lố" | So giữa các phiên bản skill |

Ngưỡng là đề xuất khởi đầu, chỉnh lại sau lần đo đầu tiên. Ghi kết quả chấm điểm theo phiên bản skill để biết thay đổi quy tắc có làm video tốt hơn không.

## Quyết định

Bối cảnh: video **gaming**, đăng **YouTube**; ContextCut giờ là editor đầy đủ, AI chỉnh trực tiếp trong app.

| Quyết định | Chốt | Lý do |
| --- | --- | --- |
| Nền tảng app | Fork Kdenlive (C++/Qt) | Có sẵn editor hoàn chỉnh, mã nguồn mở |
| Engine | MLT cho preview và xuất | Preview khớp file xuất; thay quyết định FFmpeg của v2 |
| Kết nối AI | Claude Desktop/Code → MCP → cầu nối trong app | Không cần API key, dùng hạn mức gói Pro |
| Khung chat trong app | Không | Chat trực tiếp với Claude; app chỉ có dock Hoạt động AI |
| Giao diện | Chế độ Dễ mặc định, bật được Pro | Dễ dùng mà không mất tính năng |
| Tỉ lệ khung hình | 16:9 mặc định | YouTube ngang; Shorts dùng `reframe` |
| Phong cách chính | Gaming | Các phong cách khác viết sau |

**Còn mở:**

- [ ] Mục đích phát hành: dùng cá nhân, chia sẻ miễn phí hay bán? Quyết định nghĩa vụ GPL và công sức đóng gói.
- [ ] Track phụ đề của Kdenlive có giữ tag karaoke ASS không? Thử ngay đầu P2.
- [ ] Model ASR tiếng Việt: PhoWhisper hay `large-v3`; chốt sau khi đo WER.
- [ ] Video nguồn có tách track mic không, hay phải xử lý track trộn?
- [ ] Độ dài video điển hình: clip ngắn hay VOD vài giờ?
- [ ] Tên sản phẩm cuối cùng.
- [ ] Nguồn SFX/nhạc ban đầu (20–30 file, ghi giấy phép vào manifest).
