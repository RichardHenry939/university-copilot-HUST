# Add-on "máy yếu": ưu tiên cho việc học (University Copilot)

> **Chỉ cài khi máy bạn yếu hoặc tầm trung** — kiểu một laptop vừa học online, vừa ghi bài giảng, vừa chạy UC + model AI trên cùng máy.
> Máy mạnh / homelab thật: **đừng cài**. Việc hạ ưu tiên qua lại trên máy mạnh chỉ làm UC chạy chậm đi vô ích.

## Vì sao có add-on này

Ngày 12/10/2026, trên một laptop tầm trung (Core Ultra 7, GPU tích hợp, 32 GB RAM chung), đang học online qua Teams và ghi bài bằng
máy ghi của UC (Teams → cáp ảo VB-CABLE → máy ghi), máy bận cùng lúc với việc nén bản chép lời bằng model AI chạy trên máy.
Đo được: tiếng Teams vào cáp ảo **liên tục**, nhưng máy ghi chỉ lấy được **khoảng một nửa** (nghe trên laptop bị đứt từng 1–2 giây).
Nguyên nhân: trên máy yếu, tiến trình máy ghi bị giành CPU nên lỡ nhịp đọc âm thanh.

Bản sửa lỗi máy ghi (đọc theo sự kiện, bộ đệm lớn hơn, tự đặt ưu tiên cao) **đã nằm trong phần lõi** từ v1.00.18 — máy nào cũng có.
Add-on này thêm một lớp "nhường đường" nữa, dành riêng cho máy yếu.

## Add-on làm gì

**1. Bốn bậc ưu tiên CPU, áp mọi lúc** (UC kiểm mỗi 5 giây; tiến trình mới mở cũng được xếp ngay):

| Bậc | Ưu tiên | Mặc định gồm |
|---|---|---|
| Học | Cao nhất | máy ghi bài giảng |
| Học trên trình duyệt / học online | Bình thường | Chrome (MOOC, FAMI…), Edge, Teams |
| Homelab | Dưới bình thường | Docker / WSL |
| AI | Thấp nhất | model chạy trên máy (LM Studio `llama-server`) |

Thêm / bớt tên tiến trình (`.exe`) trong `school/audio_priority.json` — không cần sửa code.

**2. Việc AI nặng nhường khi đang ghi bài:** cổng chép lời (speech gate) không bắt đầu chép lời / nén bằng model trong lúc máy ghi đang ghi;
bấm Stop thì chạy tiếp. Ghi chú bài giảng vì vậy có muộn hơn một chút.

Không tắt, không tạm dừng tiến trình nào — chỉ đổi mức ưu tiên (đổi lại được bất cứ lúc nào).

## Cài

1. Giải nén `low-end-priority.zip`.
2. Chép `audio_priority.py` vào thư mục UC (cạnh `copilot_app.py`).
3. Chép `audio_priority.example.json` thành `school/audio_priority.json` trong thư mục UC (sửa danh sách tiến trình nếu muốn).
4. Tạo file rỗng tên `low_end.flag` trong thư mục `speech-gate/` (cạnh `speech_gate.py`).
5. Khởi động lại UC và cổng chép lời.

Kiểm tra: trong Task Manager → Details, cột "Base priority": máy ghi = High, `llama-server` = Low.

## Gỡ

Xoá `audio_priority.py` (thư mục UC) và `low_end.flag` (thư mục speech-gate), khởi động lại UC + cổng chép lời.
Các tiến trình sẽ về ưu tiên mặc định khi chúng khởi động lại.

## Giới hạn (nói thật)

- Chỉ hạ được ưu tiên **CPU**. Windows **không** cho hạ ưu tiên **GPU** theo cách này: model AI đã chạy trên GPU thì vẫn chạy hết sức
  (quạt vẫn kêu). Thứ add-on bảo vệ là **tiếng bài giảng không bị rơi**, không phải làm máy yên lặng.
- Một số tiến trình được Windows bảo vệ (vd máy ảo WSL `vmmemWSL`) từ chối đổi ưu tiên — add-on bỏ qua, không báo lỗi.
- Đo kiểm của tác giả: bíp liên tục vào cáp ảo + ép mọi lõi CPU: máy ghi cũ rơi 28 lỗ (~9–13 s / 36 s); bản lõi v1.00.18 rơi 0,0 s.
  Add-on là lớp an toàn thêm cho máy yếu khi tải thật nặng hơn bài thử.
