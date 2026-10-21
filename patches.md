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
