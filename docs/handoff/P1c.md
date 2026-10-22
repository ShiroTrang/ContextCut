# Bàn giao P1c — Sửa timeline theo đợt, cổng P1

22/10/2026 · kế hoạch: `docs/plans/P1.md` (phần "P1c — chi tiết") · giao thức: `docs/protocol.md` §8.4b–8.8 · session P1c (Claude Opus 5.5). P1c là session cuối của P1; tóm tắt cả P1 ở cuối file.

## Đã xong

| Việc | Ở đâu |
| --- | --- |
| Method cầu nối `list_operations`, `validate_operations`, `apply_operations`, `add_markers`, `undo_batch`, `import_media`, `list_sources`; `get_editor_state` thêm `undo` (`index`, `count`, `next_undo`, `next_redo`) | `src/contextcut/ops/batchapplier.*`, `src/contextcut/model/editorreader.*` |
| Một đợt = **một** bước undo nhãn `AI: …`: kiểm `base_revision` trước mọi thứ (`conflict`), kiểm tham số (`validation_failed`, chưa đổi gì), chạy op theo thứ tự với một bộ gom `Fun undo/redo`, op lỗi → `undo()` cả đợt một lần (`apply_failed` + `op_index`, `field`, `reason`), xong → `pCore->pushUndo(FunctionalUndoCommand)` đúng một lần | `batchapplier.cpp` |
| `TimelineOps::step()`: mỗi lời gọi Kdenlive có bộ gom riêng, lambda gốc bật cờ để biết hàm Kdenlive đã tự `undo()` chưa (`requestClipCut`, `removeSpace` tự chạy undo khi lỗi, hàm khác thì không) → không bao giờ hoàn tác hai lần | `timelineops.cpp` |
| 8 op: `cut_range` (mọi track không khoá: `breakAffectedGroups` → `liftZone` → `removeSpace(useTargets=false)`, dời guide như Extract Zone), `split` (`requestClipCut`), `trim` (`requestItemResize` cho clip + clip cùng nhóm cùng mép), `move` (`requestGroupMove`/`requestClipMove`), `insert_clip` (tự dựng cặp V+A bằng `requestClipCreation` + `requestClipMove` + `requestClipsGroup(AVSplit)`: không hộp thoại tạo track, đúng một stream audio), `add_music` (+ hiệu ứng `volume`), `title_card`, `caption` (title clip `kdenlivetitle` dựng đồng bộ rồi `requestAddBinClip(producer)`) | `timelineops.cpp`, `titleclip.*` |
| Schema op (`list_operations`) và kiểm tĩnh (kiểu, khoảng, bắt buộc, `start_f < end_f`, trường lạ → cảnh báo); kiểm theo trạng thái (track có/khoá/đúng loại, clip có, không có mix khi `trim`/`move`, nguồn có/đã nạp/có hình-tiếng, frame trong nguồn, chỗ đích trống); track nhận id, tag hoặc tên; track chữ/nhạc mặc định theo tên | `opregistry.*`, `opvalidator.*` |
| Truy cập vài thành viên `protected` của Kdenlive **không sửa mã gốc**: lớp dẫn xuất lấy con trỏ-tới-thành-viên | `timelineaccess.h`, `patches.md` (mục "Phụ thuộc API nội bộ") |
| Thanh trạng thái: "AI đang sửa: <nhãn>…" rồi "<nhãn> — xong. Ctrl+Z để hoàn tác." | `batchapplier.cpp` |
| `import_media(path)`: chỉ đường dẫn tuyệt đối, file có thật, đuôi media; đường đã resolve phải trùng (chặn symlink/shortcut/junction); một bước undo "AI: nhập <file>"; chờ nạp ≤ 20 s | `batchapplier.cpp`, protocol §8.8 |
| MCP: tool `list_sources`, `list_operations`, `validate_operations` (chỉ đọc), `apply_operations`, `undo_batch` (destructive), `add_markers`, `import_media`; lệnh ghi không gửi lại khi kết nối rớt sau lúc gửi (báo "có thể đã được áp dụng"), ping kết nối cũ trước khi ghi; câu lỗi tiếng Việt cho `conflict`/`validation_failed`/`apply_failed` | `contextcut-ai/src/contextcut_ai/*.py` |
| Guide: `instructions` (vòng sửa), `software` (mục "Sửa timeline", bảng op, lỗi mới, bảng tool), `workflow` ("Một lần sửa"); `SKILL.md`/đoạn `AGENTS.md` sinh lại; prompt `mo-phien-dung` cho dựng phần đã duyệt | `contextcut-ai/guide/`, `skills/` |
| Fixture cổng `p1-gate` + 31 test sống của op | `contextcut-ai/tools/p1_fixture.py`, `tests/test_live_ops.py` |

Commit: `a5490e845b` (ops C++), `cb5721b076` (gain giữ được khi lưu), `4a21bfa115` (MCP + guide), `823beeb33f` (`import_media`), và commit tài liệu này.

## Bằng chứng cổng P1

Đo 22/10/2026 trên máy Nhan, bản build cuối (`build.ps1 -SkipDeps`, exit 0, ~30–40 s mỗi lần sửa). Project: fixture `p1-gate` (bản sao `tests/dataset/clip-ids.kdenlive`, 25 fps, V2/V1/A1/A2, 16 clip, dài 36 frame; thêm bản OBS giả 3 stream audio và `stereo.flac`) dựng bằng `p1_fixture.py` trong scratchpad. Không file nào trong repo bị sửa khi thử.

| Kiểm | Kết quả |
| --- | --- |
| `uv run --directory contextcut-ai pytest` (app mở fixture) | **93 passed**: 61 unit + 32 sống (31 op + 1 stdio của P1b); chạy lại 3 lượt liền trên cùng phiên app đều qua. App tắt: unit qua, sống tự bỏ qua |
| Mỗi op apply rồi `undo_batch` → so **toàn bộ** `get_timeline` + `get_editor_state` (bỏ revision/playhead/chọn) | **y hệt** với cả 8 op (`test_roundtrip_*`), kể cả id clip; cặp V+A vẫn `linked` sau `split`/`trim`/`move`; `cut_range` dời đúng mọi item phía sau |
| Một đợt 3 op | `undo.index` +1, `next_undo` = nhãn (`test_batch_is_one_undo_step`) |
| Op thứ 2 lỗi (dời vào chỗ có clip) sau `split` | `apply_failed`, `op_index: 1`, `field: at_f`; timeline và undo stack như cũ |
| `base_revision` cũ / sửa khác chen giữa đọc và gửi | `conflict` kèm `current_revision`, item không đổi |
| Bản ghi OBS 3 stream vào V2 + A2, `audio_stream` chọn | không hộp thoại, 2 clip `linked` |
| `bridge_probe.py check --quick` | OK (cầu nối P1a không đổi) |
| **Claude Code** (`claude -p`, sonnet `claude-sonnet-4-6`, server đã đăng ký, `--allowedTools mcp__contextcut`): "thêm thẻ chữ 'Trong lúc đó:' trên V2 frame 0–11 và cắt bỏ frame 26–31, một đợt" | Agent tự gọi `get_editor_state` → `list_operations` → `validate_operations` → `apply_operations` **một đợt** nhãn "AI: thêm thẻ chữ V2 + cắt frame 26–31", báo lại và nhắc Ctrl+Z (7 lượt, 0,26 USD). Timeline đổi (thẻ chữ đầu V2, dài 36 → 30), thấy trên app (ảnh chụp) |
| **Ctrl+Z thật** (SendKeys vào cửa sổ app) | timeline **y hệt** snapshot trước khi agent sửa; `next_redo` = nhãn AI |
| **Sửa tay đúng lúc**: đọc R (…581) → Ctrl+Shift+Z bằng tay (revision …591) → gửi đợt với R | `conflict` (`current_revision` …591); timeline y hệt trạng thái sau thao tác tay; Ctrl+Z → y hệt ban đầu |
| Codex (`codex exec -m gpt-5.6-terra`, sandbox read-only) | Gọi `get_editor_state`, `list_operations`, `validate_operations` (ok) đúng; `apply_operations` bị **Codex** chặn: "MCP tool call requires approval, but approval policy is never" (`codex exec` không có ai duyệt tool sửa). Timeline không đổi. 203k token vào (162k cache) |
| Lưu rồi mở lại (`.kdenlive` của Kdenlive gốc) | Title lưu là producer `kdenlivetitle` + `xmldata`, `kdenlive:clip_type 2`; nhạc có filter `volume` `level=0=-6`; mở lại thấy đủ thẻ chữ, câu đắt, nhạc + `Volume`, `modified: false` |
| Dựng khung hình từ file đã lưu bằng `melt` | frame 3: "Trong lúc đó:" trắng giữa nền đen; frame 13: "Sang: Ủa alo???" vàng viền đen trên clip xanh; dấu tiếng Việt đúng |
| Thanh trạng thái | chụp ngay sau một đợt: "AI đang sửa: thẻ chữ CÒN TIẾP…" |

## Lệch so với thiết kế / kế hoạch

1. **Thêm method/trường ngoài phác thảo:** `list_sources` (agent cần id nhạc trong bin; `list_recordings` chỉ có video), `undo_batch` (để test tự động hoàn tác như Ctrl+Z và để agent tự hoàn tác đợt vừa làm; P5 mở rộng), `get_editor_state.undo`, `import_media`. `list_operations` ghi độ dài chuỗi là `min_length`/`max_length`.
2. **`trim` nhận mép mới trên timeline** (`start_f`, `end_f`) thay vì `in_f`/`out_f` của Kiến trúc v3: cùng đơn vị với `get_timeline`, mép trái dời thì điểm vào nguồn dời theo.
3. **`validate_operations`** kiểm từng op theo timeline hiện tại; lỗi theo trạng thái của op từ thứ 2 trở đi chỉ là cảnh báo (op trước có thể đổi timeline); `apply_operations` kiểm lại đúng lúc từng op.
4. **Không sửa mã Kdenlive**: `requestClipCreation`, `getTrackById_const`, `getClipPtr`, `m_groups`, `ClipModel::getMaxDuration`, `MarkerListModel::addMarker(…, undo, redo)` là `protected`; dùng lớp dẫn xuất trong `timelineaccess.h`. Merge upstream mà đổi chữ ký thì lỗi biên dịch ở đó (ghi trong `patches.md`).
5. **`insert_clip` không dùng `requestClipInsertion`** (có thể mở hộp thoại tạo track và chèn mọi stream audio): chỉ chèn một stream (`audio_stream` hoặc stream mặc định). Muốn nhiều stream (Mic + Discord) thì chèn `audio: false` rồi thêm từng stream bằng `insert_clip` lên track audio — P2 làm khi có `track_map`.
6. **`cut_range` cắt mọi track không khoá**, không theo nút "active track" của Kdenlive (agent không thấy trạng thái đó). Guide chỉ dời khi không track nào khoá và guide không bị khoá. Phụ đề **không** dời theo (cảnh báo) — P2.
7. **Title clip dựng producer đồng bộ** (`requestAddBinClip(id, producer, …)`) thay vì `ClipCreator::createTitleClip` (nạp bất đồng bộ, phải chờ vòng lặp sự kiện giữa đợt). File lưu giống title Kdenlive tạo; font `Segoe UI` đậm (máy Windows của Nhan và bạn); tên bin = chữ, cắt 40 ký tự.
8. **Gain của `add_music`** phải ghi dạng keyframe `0=<dB>`: `level` của Volume là tham số keyframe, số trần bị Kdenlive đọc thành rỗng (bản đầu mất gain khi lưu; đã sửa ở `cb5721b076`).
9. **Thanh trạng thái**: đợt chạy vài ms; hàng đợi thông báo của Kdenlive giữ thông báo "đang xử lý" ít nhất 4 s nên "AI đang sửa…" còn hiện ~4 s rồi mới tới "— xong". Không có nút Dừng (đợt không chạy lâu).
10. `trim`/`move` từ chối clip có mix (chuyển cảnh cùng track). Clip `speed ≠ 1`, `move` đổi track của nhóm V+A (Kdenlive tự "mirror" track audio) chưa có test tự động.
11. Brief ghi lỗi `stale_revision`; giao thức (từ P1a) là `conflict` (-32003) — giữ `conflict`.
12. `reason` chỉ ghi log (`contextcut.ops`), chưa hiện ở đâu (dock Hoạt động AI là P5); chưa ghi `ai_log.jsonl`. `batch_id` mất khi app khởi động lại.
13. Nhánh "hàm Kdenlive tự `undo()` rồi trả lỗi" của `step()` chưa bị kích hoạt trong test (validator chặn trước); có lý luận + đọc mã, chưa có bằng chứng chạy.

## Chưa làm / dời

- `open_project` → P2 (Kdenlive hỏi lưu/khôi phục bằng hộp thoại modal; cần thiết kế riêng).
- **Skill đã cài** (`~/.claude/skills/contextcut-editor/SKILL.md`) vẫn là bản P1b ("chỉ đọc"): chạy `uv run --directory contextcut-ai python scripts/register_clients.py` (hỏi y/N; **cần Nhan đồng ý**). MCP `instructions` và tool đã mới vì client chạy server thẳng từ repo.
- Codex sửa được khi chạy tương tác (app/TUI, bấm duyệt tool): chưa thử. Antigravity, Claude Desktop: chưa thử (như P1b).
- Quy tắc §8.6 (giữa từ, giữa phản ứng, shot < 1,5 s) chờ transcript (P2–P4).
- Revision không đổi khi chỉ bin đổi (nhập file), nên cursor của `list_sources` có thể không báo cũ.

## Lệnh

```powershell
# fixture cổng + mở app (in lệnh mở; -i nhận danh sách phân cách dấu phẩy)
uv run contextcut-ai/tools/p1_fixture.py --out <thư mục trống>
# test (sống: cần app mở p1-gate; test_live_ops sửa rồi hoàn tác, không chạy trên project khác)
uv run --directory contextcut-ai pytest
uv run --directory contextcut-ai pytest -m live
# một đợt bằng tay
uv run contextcut-ai/tools/bridge_probe.py call list_operations
```

Dựng một khung hình từ file `.kdenlive` đã lưu để tự kiểm (bash MSYS2 UCRT64; chặn Waves như `main.cpp`):

```bash
export MLT_REPOSITORY_DENY=libmltjackrack:libmltladspa
melt -quiet p1-gate.kdenlive in=13 out=13 -consumer avformat:frame13.png vcodec=png an=1
```

## Bẫy mới (đã chép phần cần vào CLAUDE.md)

- `-i` của app nhận **một** danh sách phân cách dấu phẩy; lặp `-i` thì chỉ cái cuối có tác dụng.
- Hộp "save changes?": `PostMessage` nhấp chuột nhận **toạ độ client** — "Do Not Save" ở ≈ 394,63 (client 533×86 của cửa sổ 549×125); ghi chú cũ (398,94 toạ độ cửa sổ) không ăn.
- Ctrl+Z / Ctrl+Shift+Z gửi bằng `SendKeys` sau `SetForegroundWindow` cửa sổ chính thì ăn (Home thì không: focus ở bin).
- Kdenlive thêm "hh:mm " trước mọi nhãn undo (`FunctionalUndoCommand`); `undo.next_undo` đã bỏ phần giờ.
- Lưu lần đầu project tạo bằng Kdenlive cũ (fixture) hiện hộp "Your project file was modified by Kdenlive… backup" (Enter để OK).
- Tham số keyframe của hiệu ứng (vd. `level` của Volume) phải là chuỗi animation MLT (`0=-6`).
- `codex exec` không duyệt được tool MCP sửa (chính sách `never`).
- Bash heredoc trong phiên Claude Code trên máy này đôi khi vỡ với chuỗi tiếng Việt có dấu nháy: ghi script ra file rồi chạy.

## P2 cần biết

- Thêm op: `OpSpec` trong `opregistry.cpp` → `checkState` trong `opvalidator.cpp` → hàm trong `timelineops.cpp` (mọi lời gọi Kdenlive qua `step()`), rồi bảng op trong `guide/software.md` và `OPS_SUMMARY` của `mcp_server.py`. Test vòng apply → `undo_batch` → so snapshot như `test_live_ops.py`.
- Phụ đề (P2) nên dùng `SubtitleModel` của Kdenlive (track phụ đề), không phải title clip; `cut_range` lúc đó phải dời cả phụ đề.
- `render_frames` (P2) có thể làm như lệnh `melt` ở trên, hoặc trong app bằng producer của timeline.
- OBS nhiều stream: `insert_clip` mỗi lần một stream; `track_map` (P2) cho biết stream nào là Mic/Discord.

---

## Tóm tắt P1 (P1a + P1b + P1c)

| Session | Kết quả | Handoff |
| --- | --- | --- |
| P1a | Cầu nối C++ `AiBridgeServer` (WebSocket 127.0.0.1 + token mỗi lần chạy, JSON-RPC tuần tự trên GUI thread, `bridge.json`), revision, `get_editor_state`/`get_timeline`/`list_recordings`, `bridge_probe.py` | `docs/handoff/P1a.md` |
| P1b | MCP server Python `contextcut-ai` (mcp 2.3.0, stdio), guide v0 tiếng Việt, `SKILL.md`/đoạn `AGENTS.md`, đăng ký cho Claude Code/Desktop, Codex, Antigravity | `docs/handoff/P1b.md` |
| P1c | Sửa timeline theo đợt: 8 op, một bước undo nhãn `AI: …`, hoàn tác cả đợt khi lỗi, `conflict` khi sửa tay chen ngang, marker, `undo_batch`, `import_media`, tool MCP + guide | file này |

**Cổng P1 (design §12) đạt với Claude Code:** agent áp một đợt → hiện trên timeline → Ctrl+Z về y hệt; sửa tay đúng lúc → đợt bị từ chối, timeline không hỏng. Codex đọc và kiểm được, phần áp dụng cần chạy tương tác để duyệt tool (brief cho phép Codex là tuỳ chọn).
