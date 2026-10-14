# AgentChattr trong University Copilot — phòng họp 4 ghế AI

UC dùng [**agentchattr**](https://github.com/bcurts/agentchattr) (MIT, © Ben Curtis) làm **phòng chat chung cho 4 ghế AI**:
Claude, Codex, Gemini và **Local AI** (model chạy trên máy qua LM Studio, ghế phản biện). Bạn tag `@claude @codex @gemini @local`
là cả hội đồng cùng bàn; relay của UC (`council_relay.py`, cổng 8310) điều phối vòng nói và gửi kết luận sang n8n.

Thư mục này **không chép lại mã của agentchattr** — chỉ có:

| File | Là gì |
|---|---|
| `UPSTREAM` | commit gốc mà bản vá áp lên (`bcurts/agentchattr @ d775776`) |
| `uc-agentchattr.patch` | sửa 12 file gốc: ghế Local AI qua API (ngân sách token), cửa sổ ghế ẩn, khởi động an toàn trên Windows… (đã kiểm `git apply --check` sạch) |
| `seat_keeper.py` | **bộ giữ ghế**: 4 ghế luôn có mặt (ghế rớt -> bật lại, giãn dần 2→10 phút; đọc chữ trên cửa sổ ghế để báo "hết quota / cần đăng nhập") |
| `peek_console.py` | đọc N dòng cuối cửa sổ console của một ghế (chỉ đọc) — `seat_keeper` dùng |
| `council_relay.py` | relay hội đồng (cổng 8310): điều phối lượt nói, ghế phản biện không mở đầu / tổng hợp, gửi kết luận sang n8n |
| `launcher_w.py` | chạy máy chủ bằng `pythonw` mà vẫn có log (`ac-stdout.log` / `ac-stderr.log`) |
| `AgentChattr.ps1`, `launch.ps1` | bật máy chủ + bộ giữ ghế (+ mở Chrome App) — đặt trong thư mục agentchattr |
| `windows/start_local.bat` | khởi động ghế Local AI |
| `config.local.example.toml` | cấu hình ghế Local AI (LM Studio, model, ngân sách token, lời nhắc ghế phản biện) |

## Cài

```powershell
git clone https://github.com/bcurts/agentchattr
cd agentchattr
git checkout d775776
git apply ..\university-copilot-HUST\agentchattr\uc-agentchattr.patch
copy ..\university-copilot-HUST\agentchattr\*.py .
copy ..\university-copilot-HUST\agentchattr\*.ps1 .
copy ..\university-copilot-HUST\agentchattr\windows\start_local.bat windows\
copy ..\university-copilot-HUST\agentchattr\config.local.example.toml config.local.toml
```

Rồi làm theo README của agentchattr (venv, cài Claude Code / Codex / Gemini CLI). Biến môi trường tuỳ chọn:
`UC_DIR` (thư mục UC — lấy khoá chung `.copilot-secret` cho relay), `AC_PYTHONW` (pythonw dùng cho máy chủ), `AC_CHROME_APP_ID`
(id Chrome App của phòng chat). Chạy: `powershell -File AgentChattr.ps1` (thêm `-AtLogon` cho Task Scheduler lúc đăng nhập).

## Độ bền (v1.00.28)

Sự cố thật 14/10/2026 và cách UC tự hồi phục:

- **Bộ giữ ghế chết im lặng** (chạy `pythonw` nên không có chỗ ghi lỗi) -> nay lỗi ghi vào `seat-keeper.log` kèm traceback, vòng lặp tự chạy lại sau 10 s.
- **Máy chủ phòng chat treo** (vẫn giữ cổng 8300 nên kiểm "cổng mở" tưởng còn sống; bản bật lại thoát vì khoá `server.lock`)
  -> `/api/status` không trả lời 3 vòng liền (~1 phút) thì bộ giữ ghế tắt hẳn bản treo rồi bật lại.
  Đã thử: đóng băng máy chủ -> tự hồi phục sau 105 s.
- **Ai giữ bộ giữ ghế?** Add-on `network-guard` (chạy mỗi phút) bật lại `seat_keeper.py --kick` nếu không thấy nó.
- Tin nhắn đang xếp hàng trong bản treo bị mất khi bật lại — gửi lại.
