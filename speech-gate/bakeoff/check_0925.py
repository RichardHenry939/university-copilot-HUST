import sys   # đối số 1: đường dẫn một bản ghi bài giảng (mp3/wav)
from datetime import datetime, timedelta
import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps, VadOptions
from audio_io import load
T0 = datetime(2026, 9, 25, 7, 44, 19); sr = 16000
a = load(sys.argv[1])
ts = get_speech_timestamps(a, VadOptions(threshold=0.3, min_silence_duration_ms=800))
print("tổng tiếng nói:", round(sum(t['end']-t['start'] for t in ts)/sr/60, 1), "phút /", round(len(a)/sr/60, 1), "phút", flush=True)
m = WhisperModel(r"D:\AI\models\phowhisper-large-ct2", device="cpu", compute_type="int8", cpu_threads=8)
for hh, mm in ((8, 0), (8, 45), (9, 30)):
    off = int((datetime(2025 + 1, 9, 25, hh, mm) - T0).total_seconds())
    segs, _ = m.transcribe(a[off*sr:(off+180)*sr], language="vi", beam_size=5, vad_filter=True,
                           vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 800}, condition_on_previous_text=False)
    print(f"===== {hh:02d}:{mm:02d}–{(datetime(2026,9,25,hh,mm)+timedelta(minutes=3)):%H:%M} (25/9)", flush=True)
    for s in segs: print(f"[{(datetime(2026,9,25,hh,mm)+timedelta(seconds=s.start)):%H:%M:%S}] {s.text.strip()}", flush=True)
