# ContextCut — Thiết kế v3.1

21/10/2026 · trạng thái: **Nhan đã duyệt (21/10/2026)** · bổ sung cho `ContextCut MCP — Kiến trúc v3.md`

## 0. Cách đọc tài liệu này

Bản **Kiến trúc v3** vẫn là nền: fork Kdenlive, MLT cho preview và xuất, Claude chỉnh timeline đang mở qua MCP và cầu nối, giao diện Dễ/Pro, ops có validator, mỗi đợt sửa là một bước undo. Tài liệu này ghi những gì được chốt thêm trong buổi trao đổi ngày 21/10/2026 và kết quả spike build. **Chỗ nào hai tài liệu mâu thuẫn, tài liệu này thắng.**

Ký hiệu nguồn gốc của từng quyết định:

- **[Nhan chốt]** — Nhan nói rõ trong buổi trao đổi.
- **[Đề xuất]** — lựa chọn của người viết (Claude); Nhan chưa xác nhận riêng từng điểm, người build có thể đổi nếu có lý do.
- **[Đã kiểm chứng]** — đã chạy hoặc đo thật trên máy của Nhan.

## 1. Mục đích và lý do

Nhan muốn bắt đầu làm video gaming cho YouTube nhưng chưa từng dựng video. Khâu Nhan ngại nhất là **kịch bản và bố cục**, sau đó là **cắt** và **phụ đề**. ContextCut để Nhan quay buổi chơi bằng OBS, kéo vào app, rồi nhờ một AI agent (Claude, Codex, Antigravity…) đề xuất bố cục và dựng trực tiếp trên timeline. Nhan duyệt và chỉnh tay khi cần, như với một người dựng phụ.

Có hai dạng video gaming nhắm tới, xem mục 7 **[Nhan chốt]**:

1. **Funny moments nhiều người chơi**, từ một buổi quay ≤ khoảng 2 giờ, theo phong cách nhóm CKG: HK15 ("Bắt Nạt Hải Sản") và Sangtraan ("AI MỚI LÀ KẺ XẤU XA?", "ÔNG SANG CÂU CON CÁ").
2. **Series dài kiểu "Tôi đã chơi 100 ngày trong Minecraft modpack riêng"**: tổng hợp quá trình chơi qua nhiều buổi quay thành một video dài. Mẫu: "100 ngày mất ngủ trong Green Hell!" của kênh Cá Khô.

**Game:** trước mắt là **Minecraft** (thường là modpack). Game khác như How to Fish hay Among Us được thêm khi Nhan cần, mỗi lần là một nâng cấp riêng.

Vlog, montage và các loại video khác đến sau.

## 2. Người dùng và cách phân phối

- Công cụ cá nhân của Nhan, chia cho 2–3 người bạn dùng chung. Không bán, không phát hành công khai **[Nhan chốt]**.
- Mã nguồn ở repo GitHub private `ShiroTrang/ContextCut`; bạn bè được thêm làm collaborator **[Nhan chốt]**. Repo hiện đang trống.
- Bạn bè nhận **một bản build chạy được ngay**: tải zip từ GitHub Releases của repo private, hoặc Nhan gửi qua Google Drive với người không quen GitHub. Giải nén, chạy, và lần đầu mở app tự setup **[Nhan chốt]**. Không ai phải cài MSYS2 hay build, trừ người muốn sửa code.
- Mỗi người dùng AI client của riêng mình: Claude Desktop hoặc Claude Code (gói Pro), Codex, Antigravity **[Nhan chốt]**.
- GPL: đưa bản build cho bạn bè vẫn tính là phát hành, và repo private có collaborator đã cho họ quyền xem mã nguồn. Không cần làm thêm gì (không phải ý kiến pháp lý).

## 3. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu của bản dùng được đầu tiên** (theo thứ tự Nhan ưu tiên):

1. **Phụ đề chuẩn timing.** Câu hiện đúng lúc bắt đầu nói và tắt đúng lúc nói xong. Có hai kiểu: phụ đề đầy đủ, và "câu đắt" chọn lọc như video mẫu.
2. **Montage khớp beat nhạc.** Chuỗi khoảnh khắc được cắt sao cho mỗi cú cắt rơi đúng phách mạnh của bản nhạc Nhan đưa vào.
3. **Cú cắt mỉa (irony cut).** Ví dụ của Nhan:
   - nhạc Can Can, thẻ chữ "Chúng tôi đã thử chơi modded SMP này:";
   - đoạn Nhan và bạn nói "modpack này chưa gì thấy ok rồi đó";
   - ngay sau đó là chuỗi cảnh chết liên tiếp khớp theo nhạc.
4. **Dàn ý trước khi cắt.** AI đọc toàn bộ buổi quay, đề xuất bố cục (mở đầu, các đoạn, lý do chọn), Nhan duyệt rồi AI mới dựng.
5. AI sửa trực tiếp timeline đang mở, hiện ngay, undo được. Dùng được với nhiều AI client qua MCP.

**Không làm (ít nhất ở bản này):**

- Bán, phát hành rộng, installer đóng gói chuyên nghiệp, hỗ trợ macOS/Linux.
- Facecam: Nhan không quay facecam.
- Phụ đề karaoke tô màu từng từ: phong cách mục tiêu không dùng.
- Khung chat trong app, tự đăng YouTube, tự tải nhạc hay meme từ web.

**Phản mục tiêu** — những thứ làm sản phẩm "hỏng" dù kỹ thuật vẫn chạy đúng:

- **Video thiếu tự nhiên** **[Nhan chốt]**. Chuyển cảnh hoặc chuyển POV liên tục không có lý do. Cắt giữa câu, giữa tràng cười, giữa pha hành động. Quy tắc cụ thể ở mục 8.6.
- **Phụ đề lệch timing**, hoặc AI bịa lời thoại hay sự kiện mà nó chưa thực sự nghe hoặc xem.
- **"Lố":** meme, hiệu ứng, SFX dày đặc mà không phục vụ nhịp hay câu chuyện.
- **Phá project:** sửa không undo được, đụng vào file gốc, project không mở được bằng Kdenlive gốc.
- **Setup lằng nhằng** với bạn bè.
- **Đốt hạn mức gói Pro** vì AI xem ảnh tràn lan.

## 4. Ràng buộc

- Windows 10/11. Máy chính: laptop RTX 3060 6 GB VRAM, 8 nhân. Ổ D còn khoảng 400 GB trống, ổ C khoảng 90 GB.
- Mỗi buổi quay tối đa khoảng 2 tiếng, 1080p60, quay bằng OBS, không facecam **[Nhan chốt]**. Dạng "100 ngày" gồm nhiều buổi như vậy.
- Máy bạn bè chưa biết cấu hình. Phải chạy được khi không có GPU NVIDIA: xuất bằng `libx264`, nhận dạng giọng nói chạy CPU (chậm hơn).
- Thư mục `D:\ContextCut` đang được loại trừ khỏi Windows Defender. Nhan sẽ gỡ loại trừ khi xong dự án, nên chỉ tải về từ nguồn chính thức có chữ ký.
- MSYS2 riêng của dự án nằm ở `D:\ContextCut\env\msys64`. **Không đụng `C:\msys64`** của Nhan (Python trên PATH của Nhan lấy từ đó).

## 5. Kết quả spike build (21/10/2026) **[Đã kiểm chứng]**

Bản thử nằm trong `D:\ContextCut\spike\` và có thể xoá.

- Kdenlive **26.08.2** build từ mã nguồn bằng **MSYS2 UCRT64** với thư viện dựng sẵn (Qt 6.11.2, KF 6.31, MLT 7.40.0, FFmpeg 9.0.2, GCC 16.2). Không cần KDE Craft.
- Thời gian, máy 8 nhân:

  | Bước | Thời gian |
  | --- | --- |
  | Cài thư viện (462 MB tải, 3,1 GB cài, lúc Defender còn quét) | 13 phút |
  | CMake configure | 17 giây |
  | Build đầy đủ (550 bước) | 22 phút |
  | Rebuild sau khi chạm `core.cpp` (ccache) | khoảng 15 giây |

- `kdenlive.exe` tự build chạy được: cửa sổ Quick Setup hiện sau 1,3 giây. Kdenlive đã có sẵn wizard lần đầu (profile, fps, số track), wizard của ContextCut nên mở rộng từ đó.
- **API timeline khớp bản kiến trúc.** `src/timeline2/model/timelinemodel.hpp` có `requestClipMove`, `requestClipInsertion`, `requestItemResize`, `requestItemDeletion`, `requestClipTimeWarp`, `requestCompositionInsertion`, `requestTrackInsertion`. `timelinefunctions.hpp` có `requestClipCut`. Mỗi hàm có bản nhận `Fun &undo, Fun &redo`. Kdenlive gom các thao tác rồi gọi `pCore->pushUndo(undo, redo, i18n("…"))`, nên một đợt sửa của AI thành **một** bước undo có nhãn được.
- **Điểm gắn cầu nối:** `Core::initGUI` trong `src/core.cpp`, ngay sau `m_mainWindow = new MainWindow();`. Chỉ cần sửa một chỗ trong file gốc. `src/render/renderserver.cpp` đã có tiền lệ dùng `QLocalServer` và JSON trong app.
- **Lấy frame cho AI:** `MonitorProxy::extractFrame(path, width, height, useSourceProfile)` trả `QImage`.
- **MLT xuất NVENC được.** `h264_nvenc`, `hevc_nvenc`, `av1_nvenc` đều có; xuất 1080p60 ra file hợp lệ. Chưa so tốc độ với x264: clip thử toàn một màu nên không đo được.
- **MLT của MSYS2 thiếu gói phụ:** `fftw`, `libebur128`, `libsamplerate`, `rtaudio` (phát âm thanh preview trên Windows), `rnnoise`, `rubberband`, `sox`. Đã cài bổ sung; phải có trong danh sách phụ thuộc chính thức.
- **Plugin Waves SoundGrid trên máy Nhan bị MLT nạp** qua module `jackrack`/`ladspa`. Hậu quả: mỗi lần khởi động chậm thêm khoảng 3,5 giây, và crash lúc thoát khi xuất clip dài (2/2 lần có Waves đều crash, 0/4 lần không có thì ổn). Đặt `MLT_REPOSITORY_DENY=libmltjackrack:libmltladspa` là hết. Mới thử với `melt`, chưa thử trong giao diện Kdenlive.
- **Bẫy đã gặp:**
  - Đưa đường dẫn kiểu `/d/...` cho công cụ Windows (cmake, melt) sẽ bị hiểu thành `D:\d\...`. Luôn dùng `cygpath -m`.
  - PowerShell 5.1 làm hỏng dấu ngoặc kép khi truyền lệnh inline cho bash. Chạy MSYS2 qua file script.
  - Không chạy `du -sh /` trong MSYS2: nó quét cả ổ C và D.

## 6. Thay đổi so với Kiến trúc v3

| Hạng mục | Kiến trúc v3 | v3.1 |
| --- | --- | --- |
| Build Windows | KDE Craft, MinGW | MSYS2 UCRT64 riêng, thư viện dựng sẵn **[Đề xuất, đã kiểm chứng khả thi]** |
| Repo | Hai repo: `contextcut` và `contextcut-ai` | Một repo `ShiroTrang/ContextCut`: fork Kdenlive + thư mục `contextcut-ai/` **[Đề xuất]** |
| AI client | Claude Desktop/Code | Bất kỳ client MCP nào: Claude, Codex, Antigravity **[Nhan chốt]** |
| Hướng dẫn cho AI | `SKILL.md` (riêng Claude) | Một nguồn hướng dẫn, phát qua MCP cho mọi client, sinh `SKILL.md` cho Claude (mục 10) **[Đề xuất]** |
| Bố cục | Ngầm trong workflow của skill | Bước **dàn ý** riêng, lưu thành file, Nhan duyệt trước khi cắt (mục 8.2) **[Đề xuất từ ưu tiên của Nhan]** |
| Phụ đề | Phụ đề đầy đủ + karaoke | Đầy đủ + câu đắt chọn lọc có người nói; bỏ karaoke **[Nhan chốt]** |
| `detect_beats` | P4 | Bản đầu tiên (P3 mới) **[Nhan chốt ưu tiên]** |
| Multi-POV | Không có | Có, theo yêu cầu, kèm placeholder (mục 8.5) **[Nhan chốt]** |
| Facecam | Gợi ý trong layout | Không có. Phản ứng thể hiện bằng zoom gameplay, phụ đề to, SFX, meme **[Nhan đồng ý]** |
| Đóng gói | Installer của Craft | Zip portable + tự setup lần đầu **[Nhan chốt]** |
| VOD nhiều giờ | Chunk, tiếp tục khi bị ngắt | Mỗi buổi ≤ khoảng 2 giờ, nhưng một project có nhiều bản ghi; series "100 ngày" có thể vài chục giờ, nên giữ cache theo hash và job tiếp tục được |
| Dạng video | Gaming (meme), các phong cách khác viết sau | Funny moments nhiều người chơi + series "100 ngày" (mục 8.8) **[Nhan chốt]** |
| Game | Preset vùng cấm cho mỗi game | Minecraft trước; preset game chứa cả bộ nhận diện sự kiện; game khác thêm theo yêu cầu **[Nhan chốt]** |
| Lộ trình | P0–P6 theo tính năng v3 | Sắp lại theo ưu tiên mới (mục 12) |

## 7. Phong cách dựng mục tiêu

Rút ra từ lưới thumbnail trải đều cả 3 video mẫu. Chỉ xem hình, không nghe tiếng, nên nhạc và SFX là suy đoán.

- **Multi-POV:** cắt qua lại giữa màn hình từng người chơi. Mỗi người có viền màu riêng và nhãn "POV <tên>" ở góc trên.
- **Phụ đề chọn lọc:** chỉ câu đắt, chữ in hoa đậm có viền ở giữa dưới. Sangtraan gắn thêm avatar tròn của người nói cạnh câu.
- **Chèn meme:** clip hoặc ảnh ngoài đời, poster "WANTED" dán mặt bạn, đóng băng hình kèm phủ màu đỏ hoặc đen trắng, chớp kiểu máy ảnh, glitch, chữ to nhấn mạnh.
- **Bố cục:**
  - Mở bằng thẻ cảnh báo hoặc khoảnh khắc gây tò mò, rồi giới thiệu bối cảnh.
  - Thân video là các đoạn chơi theo thứ tự thời gian, đã cắt đoạn chết.
  - Kết bằng cao trào, thẻ "CÒN TIẾP (mai đăng)" và outro subscribe.
- **Độ dài:** video dựng 14–55 phút, từ các buổi stream dài.
- **Thay cho facecam** (vì Nhan không có): khoảnh khắc phản ứng dùng zoom vào gameplay, phụ đề to, SFX hoặc meme.

**Dạng "100 ngày"** (mẫu: Cá Khô, "100 ngày mất ngủ trong Green Hell!", 1 giờ 33 phút):

- **Bộ đếm ngày** "DAY N" luôn nằm giữa phía trên khung hình và đổi theo tiến trình trong game.
- **Bố cục theo cột mốc**, không chỉ theo từng ngày. Hơn 40 chương có tên, ví dụ "Intro", "Hướng dẫn", "Cách băng bó", "Tạch liên hoàn", "Nguồn nước sạch", "Mở khóa khu mới", "Đảo trăn". Danh sách chương nằm trong mô tả YouTube.
- **Trong từng đoạn:**
  - phụ đề lời bình ở dưới;
  - mũi tên hoặc khung chú thích chỉ vào giao diện game ở đoạn kiểu hướng dẫn;
  - thỉnh thoảng chèn meme;
  - gom các lần chết thành chuỗi (chương "Tạch liên hoàn").
- **Kết:** thẻ cảm ơn, lịch stream, kêu gọi subscribe.
- **Nguồn:** nhiều buổi quay, có thể vài chục giờ, dựng thành khoảng 1–1,5 giờ.

## 8. Quy trình dựng

### 8.1 Nguồn quay: cài đặt OBS khuyến nghị

Nhan đã cài theo khuyến nghị này.

- Output Mode **Advanced**, định dạng **MKV**, ghi **track 1–5**:

  | Track | Nội dung |
  | --- | --- |
  | 1 | Trộn chung: Discord + Game + Mic, để nghe bình thường |
  | 2 | Mic của Nhan |
  | 3 | Discord: giọng bạn bè, bắt bằng Application Audio Capture |
  | 4 | Âm thanh game |
  | 5 | Desktop Audio, chỉ để dự phòng, không trộn vào track 1 |

- Video: NVENC HEVC, **CQP 20**, preset P5. Nên đặt keyframe interval 2 giây và lưu file vào ổ D.

ContextCut **mặc định hiểu sơ đồ track này**:
- nhận dạng lời Nhan và phát hiện phản ứng → track 2;
- lời bạn bè → track 3;
- tìm sự kiện bằng âm thanh game → track 4.

Sơ đồ phải chỉnh được theo từng project. Nếu file chỉ có một track trộn chung, tách giọng bằng Demucs như bản kiến trúc. Mỗi stream audio trong MKV nên vào timeline thành một track riêng, đặt tên sẵn: Mic, Discord, Game.

Tài liệu cho bạn bè cần có phần "cài OBS như Nhan", vì nó quyết định chất lượng phân tích.

### 8.2 Dàn ý (bước mới)

- Sau khi phân tích, AI viết **dàn ý** trước khi cắt. Dàn ý gồm danh sách đoạn, mỗi đoạn có:
  - vai trò: hook, bối cảnh, thân, cao trào, "trong lúc đó", kết;
  - khoảng thời gian trên bản ghi gốc;
  - POV dùng;
  - lý do chọn, một câu;
  - kiểu dựng: thường, montage theo beat, cú cắt mỉa…;
  - trạng thái: đề xuất, đã duyệt, đã dựng.
- Dàn ý lưu ở `MyVideo.contextcut/outline.json` và hiện trong app (một tab của dock Hoạt động AI) để Nhan đọc, sửa, duyệt.
- Ở chế độ Duyệt, AI chỉ dựng những đoạn đã duyệt. Mỗi đoạn dựng xong là một đợt sửa có nhãn, ví dụ "AI: đoạn 3 — montage chết Can Can".

### 8.3 Phụ đề chuẩn timing

- Lời thoại lấy theo từng từ, có timestamp, từ track Mic và track Discord riêng. Người nói xác định theo track: Mic là Nhan, Discord là "bạn bè". Khi có POV của từng người bạn, mic trong bản ghi của họ giúp gán đúng tên. **[Đề xuất]**
- Hai kiểu hiển thị:
  - **Đầy đủ:** đưa vào track phụ đề của Kdenlive, ngắt dòng khoảng 32–42 ký tự.
  - **Câu đắt:** title clip trên track Chữ, style theo người nói (màu hoặc avatar), chữ in hoa đậm có viền.
- Mục tiêu đo: lệch đầu và cuối từ, **trung vị dưới 100 ms** so với mốc gõ tay (giữ từ bản kiến trúc).
- Tham khảo được: `D:\SongMV\tools\audiotool\lyrics.py` đã dùng PhoWhisper-large (VinAI) phiên âm tiếng Việt, và Demucs để tách giọng. Có thể dùng lại cách cài và chạy. Chọn faster-whisper `large-v3` hay PhoWhisper, có cần forced alignment thêm hay không, là việc của người build sau khi đo WER và độ lệch trên fixtures.

### 8.4 Montage theo beat và cú cắt mỉa

- Nhạc do Nhan cung cấp, nằm trong thư viện asset có `manifest.json` ghi nguồn và giấy phép. Nhạc cổ điển như Can Can đã hết bản quyền sáng tác, nhưng **bản thu âm** cụ thể vẫn có thể dính Content ID, nên ưu tiên bản thu public domain.
- `detect_beats` trả danh sách phách kèm độ mạnh. Op `beat_montage` nhận danh sách khoảnh khắc và bản nhạc, đặt mỗi cú cắt **trùng phách, sai số ±1 frame**. Mỗi clip có điểm vào hợp lý: khoảnh khắc chính (ví dụ màn hình chết) rơi gần đầu phách, không bị cắt cụt. **[Đề xuất]**
- Cú cắt mỉa là một **mẫu dựng** trong hướng dẫn cho AI (mục 10):
  1. thẻ chữ dẫn chuyện;
  2. câu thoại tự tin, lấy nguyên câu, không cắt giữa từ;
  3. cắt gọn sang montage phản bác câu đó;
  4. nhạc vào đúng điểm cắt.

### 8.5 Multi-POV và placeholder **[Nhan chốt; cách lưu là Đề xuất]**

- Mặc định chỉ dùng POV của Nhan. POV bạn bè chỉ thêm khi Nhan yêu cầu AI, kèm thông tin: số POV, tên từng người, và thư mục chứa source nếu đã có.
- Mỗi POV có tên, màu viền và nhãn "POV <tên>" giống video mẫu.
- **Chưa có source:**
  - AI vẫn quyết định chỗ chuyển sang POV nào.
  - AI đặt **placeholder** lên track POV: khung màu của người đó, ghi "POV <tên> — chờ source".
- **Có source** (Nhan bỏ vào thư mục riêng, ví dụ `pov/<tên>/`):
  - ContextCut tìm độ lệch thời gian giữa bản ghi của bạn bè và bản ghi của Nhan bằng âm thanh. Hai bên cùng nghe một cuộc gọi Discord. Kdenlive cũng có sẵn căn chỉnh theo âm thanh.
  - Sau đó thay placeholder bằng đúng đoạn hình tương ứng, **không xê dịch clip nào khác**.
- Quyết định "lúc nào chuyển sang POV ai" lưu theo **thời gian trên timeline của Nhan** (`pov.json`), không theo thời gian trong file của bạn bè. Nhờ vậy source đến muộn hay bắt đầu quay lệch giờ đều không phải dựng lại.
- Nếu không khớp được bằng âm thanh (ví dụ bản ghi của bạn bè không có tiếng Discord), app báo rõ và cho Nhan chọn một mốc chung bằng tay.

### 8.6 Quy tắc chuyển cảnh và chuyển POV **[Nhan chốt bằng ví dụ]**

- **Chỉ chuyển khi có lý do.** Mỗi lần chuyển POV, AI ghi một câu lý do vào đợt sửa.
- **Để khoảnh khắc diễn ra trọn vẹn rồi mới chuyển.** Hành động xong, phản ứng xong (cười, la, câu thoại nói hết) mới cắt.
- **Nhân trước, quả sau.** Ví dụ Among Us, khi Nhan là imposter:
  1. POV của Nhan lúc "sực" bạn B, chờ "sực" xong và tràng cười xong;
  2. rồi mới sang POV bạn B bị "sực".

  Đảo vai thì đảo thứ tự.
- **Song song thì kể trọn từng mạch.** Ví dụ Minecraft:
  1. Kể trọn đoạn Nhan và bạn A sống chết giữ nhà ban đêm, có thể kèm meme hợp cảnh.
  2. Sau đó sang POV bạn B kèm thẻ chữ **"Trong lúc đó:"**: B đang thong thả đào tài nguyên dưới hang.

  Giá trị nằm ở sự tương phản.
- **Validator trong app** chặn các điểm cắt hoặc chuyển POV:
  - rơi vào giữa một từ (theo transcript);
  - rơi vào giữa một sự kiện phản ứng (tiếng cười, la hét);
  - tạo ra shot ngắn hơn ngưỡng tối thiểu (mặc định khoảng 1,5 giây, chỉnh được).

  AI được vượt qua bằng cờ có ghi lý do. Ngưỡng là điểm khởi đầu, chỉnh sau khi Nhan chấm.

### 8.7 Tìm khoảnh khắc theo hai lớp **[Đề xuất]**

Mục tiêu là không để AI xem ảnh suốt 2 tiếng, vì xem ảnh tốn hạn mức gói Pro nhanh nhất.

1. **Lớp máy (local, rẻ):** sinh danh sách ứng viên có timestamp:
   - phản ứng trên track Mic: đỉnh âm lượng đột ngột, tiếng cười, đoạn nói dày;
   - khoảng lặng;
   - điểm cắt cảnh;
   - **sự kiện theo game**, khai báo trong preset của game: từ khoá chữ trên màn hình như "You Died!" (OCR), hiện tượng màu như màn hình đỏ hay đen trắng, mẫu âm thanh đặc trưng trên track Game.
2. **Lớp AI:** agent đọc transcript và danh sách ứng viên, rồi chỉ xem contact sheet hoặc frame quanh những ứng viên đáng chú ý để xác nhận và hiểu chuyện gì xảy ra. Với cảnh POV song song, AI xem frame của **cả hai** POV quanh mốc chuyển.

**Preset theo game:**
- Mỗi game là một preset dạng dữ liệu (`game_preset.json`): vùng cấm, từ khoá OCR, hiện tượng màu, mẫu âm thanh, cách đọc bộ đếm ngày nếu có.
- Bộ nhận diện riêng của game chỉ là plugin khi dữ liệu không đủ.
- **Minecraft làm trước** **[Nhan chốt]**: màn hình chết ("You Died!"), chữ đỏ, tiếng chết, thanh máu về 0. Modpack thường đổi giao diện, nên preset phải chỉnh được theo từng modpack.
- Thêm game mới là một nâng cấp riêng, nhỏ và độc lập. Guide cho người phát triển phải có mục "cách thêm một game".

### 8.8 Dự án nhiều buổi quay và dạng "100 ngày" **[Nhan chốt dạng video và việc để sau; cách làm là Đề xuất]**

**Chưa ưu tiên. Làm ở P7, sau mọi giai đoạn khác.** Riêng mô hình dữ liệu nhiều bản ghi phải có từ P1.

Nội dung theo lời Nhan: video tóm tắt **hành trình chơi theo từng ngày**: ngày 1 đã làm gì, có gì đặc sắc, những sự kiện đặc biệt nào xảy ra, cứ thế đến ngày 100.

- **Mô hình dữ liệu phải hỗ trợ nhiều bản ghi trong một project ngay từ P1,** không chỉ cho series: OBS có thể chia file, một video có thể ghép nhiều buổi.
  - Mỗi bản ghi được phân tích riêng, cache theo hash file.
  - Transcript, sự kiện và khoảnh khắc mang theo định danh bản ghi.
  - Cơ chế job tiếp tục được khi bị ngắt của v3 cần giữ lại, vì series có thể có vài chục giờ quay.
- **Bộ đếm ngày:**
  - Mỗi bản ghi và mỗi khoảnh khắc được gắn "ngày trong game".
  - Cách làm khuyến nghị: thêm một mod HUD hiển thị số ngày vào modpack để OCR đọc chắc chắn.
  - Dự phòng: Nhan khai báo ngày bắt đầu của mỗi buổi, AI suy ra phần còn lại và hỏi lại khi không chắc.
  - Trên video, lớp chữ "DAY N" tự cập nhật theo ngày của đoạn đang chiếu.
- **Dàn ý theo ngày, có chương cho sự kiện đặc biệt** (dùng chung cơ chế mục 8.2):
  - Xương sống là trình tự ngày 1 → ngày 100. Ngày nào bình thường thì lướt nhanh, ngày nào có chuyện thì kể kỹ.
  - Sự kiện đặc biệt có chương riêng, như "Tạch liên hoàn" hay "Mở khóa khu mới", gom từ nhiều buổi. Khi xuất, sinh luôn **danh sách chương YouTube** (`00:00 Intro …`) để dán vào mô tả.
- **Đoạn kiểu hướng dẫn:** op chú thích (mũi tên, khung highlight) chỉ vào giao diện game. Bản kiến trúc v3 đã nhắc "highlight vùng màn hình" ở phong cách Tutorial.
- **Dung lượng:** với CQP 20, mỗi giờ quay khoảng 15–25 GB (ước lượng). Series 30–50 giờ có thể chiếm 0,5–1 TB, vượt chỗ trống ổ D hiện có. Cần chọn: chất lượng ghi thấp hơn cho series, hoặc chỉ giữ file proxy và đoạn đã chọn sau khi phân tích. Đây là việc của Nhan.

## 9. Bổ sung MCP tools và operations

Giữ toàn bộ danh mục của Kiến trúc v3. Thêm hoặc đổi như dưới đây. Tên và tham số là gợi ý; schema chi tiết do người build chốt.

**Tools mới hoặc thay đổi:**

| Tool | Việc | Giai đoạn |
| --- | --- | --- |
| `get_transcript(start?, end?, track?)` | Lời thoại theo từ, có người nói, phân trang | P2 |
| `find_moments(kinds[], start?, end?)` | Ứng viên từ lớp máy: reaction, laugh, death/sự kiện game, silence, scene_cut | P3 |
| `detect_beats(asset)` | Job → phách + độ mạnh (chuyển từ P4 lên) | P3 |
| `get_outline()`, `save_outline(outline)` | Đọc và ghi dàn ý; hiện trong app | P3 |
| `list_assets(kind, tags?)` | Nhạc, SFX, meme trong thư viện (có manifest) | P3 |
| `register_pov(name, color, folder?)`, `sync_pov(name)` | Khai báo POV; job tìm độ lệch bằng âm thanh | P4 |
| `get_guide(topic?)` | Trả nội dung hướng dẫn, dự phòng cho client không đọc được resource hay prompt | P1 |
| `list_recordings()`, `import_media(path)` mở rộng | Project có nhiều bản ghi; mỗi bản ghi có id, hash, sơ đồ track, ngày trong game | P1 (mô hình dữ liệu), P7 (series) |
| `set_recording_day(recording, day_start)`, `get_days()` | Khai báo hoặc đọc ngày trong game theo bản ghi và khoảnh khắc | P7 |
| `export_chapters()` | Danh sách chương YouTube từ dàn ý và timeline | P7 |

**Operations mới:**

| Op | Tham số chính | Ghi chú |
| --- | --- | --- |
| `insert_clip` | `source`, `in_f`, `out_f`, `track`, `at_f` | Thiếu trong v3; cần cho montage và dựng theo dàn ý |
| `add_music` | `asset`, `at_f`, `in_f?`, `out_f?`, `gain_db` | Track Nhạc/SFX |
| `title_card` | `text`, `style`, `start_f`, `end_f` | Thẻ chữ toàn màn hình: "Trong lúc đó:", "CÒN TIẾP", dẫn chuyện |
| `caption` | `text`, `speaker`, `style`, `start_f`, `end_f` | Câu đắt trên track Chữ |
| `beat_montage` | `moments[]`, `music`, `start_f`, `align` | Gói nhiều `insert_clip` khớp phách thành một op |
| `pov_placeholder` | `pov`, `start_f`, `end_f` | Khung chờ source |
| `pov_switch` | `pov`, `start_f`, `end_f`, `reason` | Hiện POV đã sync, có viền và nhãn; thay placeholder nếu có |
| `day_counter` | `style`, `start_f?`, `end_f?` | Lớp "DAY N" tự cập nhật theo ngày của đoạn đang chiếu |
| `callout` | `kind` (mũi tên, khung), `rect`, `text?`, `start_f`, `end_f` | Chú thích giao diện game ở đoạn hướng dẫn; tôn trọng vùng cấm |

Hiệu ứng như freeze kèm phủ màu, flash, glitch, rung, zoom phản ứng là preset một cú bấm (`zoom` đã có trong v3), thuộc P6, trừ `zoom` vì phải có ngay từ đầu để thay facecam.

**Quy ước chung:**
- Mọi thời gian đều là frame trên timeline đang mở, như v3.
- Mỗi op chuyển POV hoặc cắt đều có trường `reason`; trường này hiện trong dock Hoạt động AI.

## 10. Hướng dẫn cho AI agent (guide / skill)

Nhan muốn agent "biết cách edit và dùng phần mềm" **[Nhan chốt]**. Vì phải phục vụ nhiều client **[Đề xuất]**:

- **Một nguồn duy nhất** trong `contextcut-ai/guide/`, viết bằng markdown tiếng Việt, gồm:
  - `workflow.md`: các bước từ phân tích → dàn ý → duyệt → dựng → tự kiểm tra bằng `render_frames` → xuất, kèm khi nào phải hỏi Nhan;
  - `editing-rules.md`: quy tắc mục 8.6, nguyên tắc biên tập của v3, chống "lố", tiết kiệm hạn mức khi xem ảnh;
  - `patterns/`: mỗi mẫu dựng một file, ví dụ cú cắt mỉa, "trong lúc đó", montage theo beat, zoom phản ứng thay facecam, mở đầu bằng hook, kết "CÒN TIẾP";
  - `styles/`: `gaming.md` trước; vlog, montage và các loại khác sau;
  - `software.md`: cách đọc timeline, đơn vị frame, tên track mặc định, ý nghĩa marker màu, chế độ Duyệt/Tự động.
- **Phát cho mọi client qua MCP:**
  - `instructions` của server: tóm tắt ngắn, kèm chỉ dẫn đọc thêm;
  - MCP **prompts**: mở phiên dựng, chọn phong cách;
  - MCP **resources** (`contextcut://guide/...`);
  - tool `get_guide` làm dự phòng.
- **Sinh thêm cho từng client:** `SKILL.md` cho Claude Code và Claude Desktop, một đoạn `AGENTS.md` cho Codex và Antigravity. Sinh bằng script từ cùng nguồn để không lệch nhau.
- **Kiểm tra hướng dẫn:** chạy cùng một buổi quay mẫu với từng client, Nhan chấm 1–5 về độ tự nhiên, độ hợp ngữ cảnh và độ "lố". Ghi điểm theo phiên bản guide, như v3 đề xuất cho skill.

## 11. Repo, build, đóng gói, tự setup

**Repo [Đề xuất]:**
- `ShiroTrang/ContextCut` chứa **lịch sử Kdenlive gốc** (từ `invent.kde.org/multimedia/kdenlive`, tag `v26.08.2`), remote `upstream`. Cập nhật bằng cách merge tag phát hành KDE Gear mới.
- Thêm vào repo:
  - `src/contextcut/`: code C++ mới, như v3;
  - `contextcut-ai/`: dịch vụ Python;
  - `docs/`: Kiến trúc v3 và tài liệu này;
  - `patches.md`;
  - `packaging/`: script build và đóng gói.
- Thư mục `env/` (MSYS2) **không** đưa vào repo.

**Build:**
- Script một lệnh `packaging/build.sh`. Script cài phụ thuộc vào MSYS2 UCRT64, rồi configure và build bằng các flag của PKGBUILD MSYS2 (`-DUSE_DBUS=OFF -DFETCH_OTIO=OFF -DBUILD_TESTING=OFF …`), kèm ccache.
- Phụ thuộc = phụ thuộc của gói `mingw-w64-ucrt-x86_64-kdenlive`, cộng các optdeps MLT ở mục 5, cộng `qt6-websockets` cho cầu nối.

**Đổi tên tối thiểu:**
- Tên app và thư mục cấu hình riêng, ví dụ `contextcutrc` thay vì `kdenliverc`, để chạy song song với Kdenlive gốc.
- Không dùng tên hay logo Kdenlive làm thương hiệu; About ghi "dựa trên Kdenlive".
- Đặt `MLT_REPOSITORY_DENY=libmltjackrack:libmltladspa` trước khi khởi tạo MLT. Ghi chỗ sửa này vào `patches.md`.

**Đóng gói [Nhan chốt hướng; chi tiết là Đề xuất]:**
- Zip portable gồm: exe, DLL lấy theo cây phụ thuộc từ `/ucrt64/bin`, plugin Qt và KF, module và dữ liệu MLT, frei0r, ffmpeg, mediainfo, `uv.exe` và `contextcut-ai/`.
- Ước tính 0,5–1 GB. Phát qua GitHub Releases của repo private hoặc Google Drive.

**Tự setup lần đầu:**
1. App chạy `uv sync`, tự tải Python 3.11 và thư viện.
2. Kiểm tra GPU và NVENC. Chọn CUDA nếu có, không thì CPU int8.
3. Tìm các AI client có trên máy (Claude Desktop, Claude Code, Codex, Antigravity) và **hỏi trước** khi ghi cấu hình MCP cho từng cái.
4. Model nhận dạng giọng nói chỉ tải khi dùng lần đầu, có thanh tiến độ.

Cần mạng ở lần chạy đầu.

## 12. Lộ trình

Mỗi giai đoạn có một cổng phải qua. Ước lượng tuần của v3 không còn đúng; người build tự ước lượng lại.

| GĐ | Nội dung | Cổng |
| --- | --- | --- |
| **P0** Nền | Import lịch sử Kdenlive vào repo, push lên private; `packaging/build.sh`; đổi tên tối thiểu; fix Waves; `CLAUDE.md` + `AGENTS.md` | Clone sạch → một lệnh build → ContextCut chạy song song với Kdenlive gốc, cấu hình tách riêng |
| **P1** Cầu nối | AiBridgeServer (WebSocket `127.0.0.1` + token), JSON-RPC, `base_revision`, gom undo có nhãn; `get_editor_state`, `get_timeline`, `list/validate/apply_operations`, `add_markers`; ops `cut_range`, `split`, `trim`, `move`, `insert_clip`, `add_music`, `title_card`, `caption` (bản đơn giản); MCP server Python + bridge client; script đăng ký nhiều client; guide v0 | Từ **Claude Code và Codex**: apply một đợt → hiện trên timeline → Ctrl+Z về y hệt; sửa tay đúng lúc → đợt bị từ chối, timeline không hỏng |
| **P2** Phụ đề, nhìn, xuất | `transcribe` theo track; phụ đề đầy đủ + câu đắt; 4 tool vision; `export` NVENC/x264 + ffprobe; `zoom` | Phụ đề lệch trung vị < 100 ms trên fixtures; ghi lại client nào hiển thị được ảnh từ tool |
| **P3** Dàn ý, khoảnh khắc, beat | `find_moments` (mic + preset game), `detect_beats`, `beat_montage`, `get/save_outline` + tab dàn ý; mẫu cú cắt mỉa trong guide | Từ một buổi quay thật khoảng 2 giờ, agent ra dàn ý + đoạn montage chết theo Can Can, Nhan chấm ≥ 4/5 về độ tự nhiên |
| **P4** Multi-POV | `register_pov`, `sync_pov`, placeholder, `pov_switch` (viền + nhãn), validator chuyển cảnh, thẻ "Trong lúc đó:" | Bản ghi bạn bè lệch giờ không biết trước → sync sai ≤ 1 frame; thay placeholder không xê dịch clip khác |
| **P5** Dễ dùng + phân phối | Giao diện Dễ, dock Hoạt động AI (Giữ/Hoàn tác), wizard tự setup, zip portable | Một người bạn cài từ zip trên máy khác, tự làm một video có phụ đề trong < 15 phút, không cần hỏi |
| **P6** Hiệu ứng, thư viện | Preset freeze kèm màu, flash, glitch, rung; thư viện meme/SFX có tag và manifest; phong cách vlog, montage | Nhan chấm điểm cao hơn bản P3 trên cùng buổi quay |
| **P7** Series "100 ngày" (để sau) | Ngày trong game theo bản ghi, `day_counter`, dàn ý theo ngày + chương sự kiện, `callout`, `export_chapters`, chiến lược dung lượng | Từ nhiều buổi quay Minecraft, agent ra bản dựng tóm tắt theo ngày có bộ đếm đúng và danh sách chương dán được lên YouTube |

Trước P5, dùng tạm dock Undo History có sẵn của Kdenlive để xem các đợt sửa của AI.

**Cách triển khai [Nhan chốt]:** **mỗi giai đoạn chạy trong một session riêng, bắt đầu mới**, để AI không phải đọc lại cả cuộc trao đổi dài và tốn hạn mức.
- Vì vậy tài liệu này cùng Kiến trúc v3 phải **đủ để tự đứng**.
- Mỗi session giai đoạn tự đọc hai tài liệu, viết kế hoạch chi tiết cho riêng giai đoạn đó (lưu vào `docs/plans/`), làm, kiểm tra cổng, rồi ghi một ghi chú bàn giao ngắn (`docs/handoff/Pn.md`): đã xong gì, lệch gì so với thiết kế, việc còn dở.
- Session giai đoạn sau đọc ghi chú đó thay vì đọc lịch sử chat.
- **Chia theo phần việc kiểm tra được.** Giai đoạn lớn được tách thành nhiều session, mỗi session kết thúc bằng thứ chạy được và một commit. P1 dự kiến 2–3 session: cầu nối C++, MCP server Python, các op. Không nhồi cả giai đoạn vào một session dài.
- **`CLAUDE.md` và `AGENTS.md` ở gốc repo** (tạo ở P0), cùng một nội dung, giữ ngắn. Gồm lệnh build và test, các bẫy đã gặp (mục 5), chỗ để tài liệu, giai đoạn nào đã xong. Claude Code tự đọc `CLAUDE.md`, Codex và Antigravity đọc `AGENTS.md`, nên mọi session khởi đầu đúng mà không cần đọc lại chat.

## 13. Phần để người build tự quyết

- Cách cài cụ thể cho từng op trên mô hình timeline Kdenlive. Phải đối chiếu từng hàm trong mã nguồn.
- Schema JSON-RPC và MCP chi tiết, cách phân trang.
- Thư viện cho OCR, phát hiện tiếng cười, khớp mẫu âm thanh; thuật toán sync POV.
- Model ASR và có forced alignment hay không, chọn sau khi đo trên fixtures.
- Placeholder dùng color clip hay title clip; cách thay bằng source thật.
- Layout chi tiết của giao diện Dễ, cách sinh zip, cách dò AI client trên máy.
- Khung test cho C++ và Python.

## 14. Còn mở

- Tên sản phẩm cuối cùng; tạm gọi ContextCut.
- Nguồn nhạc, SFX, meme ban đầu và giấy phép; Nhan tự chuẩn bị.
- Cấu hình máy bạn bè: có GPU NVIDIA không, dùng AI client nào.
- Codex và Antigravity có hiển thị ảnh trả về từ tool MCP không. Phải thử ở P1–P2; nếu không, ghi rõ giới hạn trong guide.
- Model ASR tiếng Việt: PhoWhisper hay `large-v3`, chốt sau khi đo.
- **Dữ liệu test:** P2 cần một buổi quay thật bằng OBS với cài đặt mục 8.1 (10–20 phút là đủ) và vài phút mốc lời đánh dấu tay. Có thể dùng lại Lyric Calibrator trong `D:\SongMV`. Session P2 hỏi Nhan khi bắt đầu.
- **AI client để thử:** cổng P1 thử với Claude Code trước. Codex và Antigravity thử khi Nhan có sẵn trên máy; nếu chưa có thì ghi vào ghi chú bàn giao.
- **Dung lượng cho series "100 ngày":** giảm chất lượng ghi hay chỉ giữ proxy (mục 8.8). Quyết định khi tới P7.
- Nhắc Nhan gỡ `D:\ContextCut` khỏi danh sách loại trừ Defender khi xong dự án.
