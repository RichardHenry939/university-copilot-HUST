"""Tạo audio kiểm thử (KHÔNG phải ghi âm thật): bài giảng giả do TTS đọc + file gần như im lặng/ồn."""
import asyncio, wave, numpy as np, sys
sys.path.insert(0, "..")
import edge_tts
from audio_io import load
TEXT = """Chào các em, hôm nay chúng ta học bài mới của môn Nhập môn lập trình: mã giả và thuật toán.
Thuật toán là một dãy hữu hạn các bước rõ ràng để giải một bài toán. Một thuật toán tốt phải có tính đúng đắn, tính dừng và tính hiệu quả.
Mã giả, hay pseudocode, là cách viết thuật toán bằng ngôn ngữ gần với ngôn ngữ tự nhiên, không phụ thuộc ngôn ngữ lập trình cụ thể.
Ví dụ, thuật toán tìm số lớn nhất trong dãy a gồm n phần tử. Bước một, gán max bằng a một. Bước hai, với i chạy từ hai đến n, nếu a i lớn hơn max thì gán max bằng a i. Bước ba, trả về max.
Độ phức tạp của thuật toán này là O của n, vì ta duyệt qua mỗi phần tử đúng một lần.
Các em chú ý, phần độ phức tạp O lớn này sẽ có trong bài kiểm tra giữa kỳ.
Tiếp theo là thuật toán tìm kiếm nhị phân. Điều kiện là dãy đã được sắp xếp tăng dần. Ta so sánh phần tử ở giữa với giá trị cần tìm, rồi loại bỏ một nửa dãy sau mỗi bước. Độ phức tạp là O của log n.
Bài tập về nhà: viết mã giả cho thuật toán sắp xếp nổi bọt, và tính số phép so sánh trong trường hợp xấu nhất. Hạn nộp là thứ Năm tuần sau, nộp trên hệ thống học trực tuyến.
Buổi sau chúng ta sẽ học về vòng lặp và mảng trong ngôn ngữ C, các em đọc trước chương ba trong giáo trình."""
async def main():
    await edge_tts.Communicate(TEXT, "vi-VN-NamMinhNeural", rate="-5%").save("tts_raw.mp3")
asyncio.run(main())
sr = 16000
speech = load("tts_raw.mp3")
rng = np.random.default_rng(1)
# bài giảng giả: chèn khoảng lặng giữa các câu cho giống giảng thật + tiếng ồn phòng nhẹ
pad = np.zeros(sr * 20, dtype=np.float32)
lecture = np.concatenate([pad, speech, pad, speech, pad, speech, pad])
lecture = lecture + rng.normal(0, 0.004, len(lecture)).astype(np.float32)
def save(name, x):
    with wave.open(name, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
save("test_lecture.wav", lecture)
# file "ồn": 10 phút tiếng ồn + 20 giây tiếng nói rất nhỏ (mô phỏng máy trong balo, ngồi xa)
noise = rng.normal(0, 0.01, sr * 600).astype(np.float32)
noise[sr*300: sr*300 + sr*20] += speech[: sr*20] * 0.05
save("test_noisy.wav", noise)
print("tts", round(len(speech)/sr/60, 1), "phút; lecture", round(len(lecture)/sr/60, 1), "phút; noisy 10 phút")
