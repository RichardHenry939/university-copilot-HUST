import sys   # đối số 1: đường dẫn một bản ghi bài giảng (mp3/wav)
from datetime import datetime, timedelta
from faster_whisper import WhisperModel
from audio_io import load
T0 = datetime(2026, 9, 24, 8, 24, 29); sr = 16000
a = load(sys.argv[1])
m = WhisperModel(r"D:\AI\models\phowhisper-large-ct2", device="cpu", compute_type="int8", cpu_threads=8)
for hh, mm in ((9, 20), (10, 20), (10, 52), (11, 4)):
    off = int((datetime(2026, 9, 24, hh, mm) - T0).total_seconds())
    segs, _ = m.transcribe(a[off*sr:(off+300)*sr], language="vi", beam_size=5, vad_filter=True,
                           vad_parameters={"threshold": 0.15, "min_silence_duration_ms": 800}, condition_on_previous_text=False)
    print(f"\n===== {hh:02d}:{mm:02d}–{(datetime(2026,9,24,hh,mm)+timedelta(minutes=5)):%H:%M} (24/9)", flush=True)
    for s in segs:
        print(f"[{(datetime(2026,9,24,hh,mm)+timedelta(seconds=s.start)):%H:%M:%S}] {s.text.strip()}", flush=True)
