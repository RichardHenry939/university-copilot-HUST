import sys   # đối số 1: đường dẫn một bản ghi bài giảng (mp3/wav)
import numpy as np, wave, json
from audio_io import load as decode_audio
from faster_whisper.vad import get_speech_timestamps, VadOptions
SRC = sys.argv[1]
sr = 16000
a = decode_audio(SRC, sr)
print("duration min:", round(len(a) / sr / 60, 1))
ts = get_speech_timestamps(a, VadOptions(min_silence_duration_ms=500))
speech = np.zeros(len(a) // sr + 1)
for t in ts:
    speech[t["start"] // sr: t["end"] // sr + 1] = 1
print("speech ratio total:", round(speech.mean(), 2))
win = 600
best = max(range(0, len(speech) - win, 30), key=lambda s: speech[s:s + win].sum())
print("best window start min:", round(best / 60, 1), "speech ratio:", round(speech[best:best + win].mean(), 2))
seg = a[best * sr:(best + win) * sr]
with wave.open(r"sample.wav", "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes())
json.dump({"source": SRC, "start_sec": best, "len_sec": win}, open(r"sample.json", "w"))
