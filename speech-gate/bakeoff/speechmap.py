import sys   # đối số 1: đường dẫn một bản ghi bài giảng (mp3/wav)
import numpy as np, json
from datetime import datetime, timedelta
from audio_io import load
from faster_whisper.vad import get_speech_timestamps, VadOptions
SRC = sys.argv[1]
T0 = datetime(2026, 9, 24, 8, 24, 29)   # = captureId 1790213069440 (giờ máy, UTC+7)
a = load(SRC); sr = 16000
ts = get_speech_timestamps(a, VadOptions(threshold=0.3, min_silence_duration_ms=800))
mins = len(a) // sr // 60 + 1
sp = np.zeros(mins)
for t in ts:
    s, e = t["start"] / sr, t["end"] / sr
    m = int(s // 60)
    while s < e:
        nxt = min(e, (m + 1) * 60); sp[m] += nxt - s; s = nxt; m += 1
rms = [float(np.sqrt(np.mean(a[i*60*sr:(i+1)*60*sr]**2)) + 1e-9) for i in range(mins)]
rows = [{"min": i, "clock": (T0 + timedelta(minutes=i)).strftime("%H:%M"), "speech_s": round(float(sp[i]), 1), "rms_db": round(20*np.log10(rms[i]), 1)} for i in range(mins)]
json.dump(rows, open("speechmap_0924.json", "w"), indent=0)
line = "".join("█" if r["speech_s"] > 30 else "▓" if r["speech_s"] > 15 else "░" if r["speech_s"] > 3 else "·" for r in rows)
for i in range(0, mins, 30):
    print(rows[i]["clock"], line[i:i+30])
print("tổng tiếng nói:", round(sum(sp)/60, 1), "phút /", mins, "phút")
