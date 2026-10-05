"""Chạy 1 model trên sample.wav, ghi kết quả + thời gian. Dùng chung cho cả 2 model để so công bằng."""
import json, sys, time
from faster_whisper import WhisperModel
from audio_io import load
name, path = sys.argv[1], sys.argv[2]
audio = load("sample.wav")
t0 = time.time()
model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=8)
t1 = time.time()
segs, info = model.transcribe(audio, language="vi", beam_size=5, vad_filter=True,
                              vad_parameters={"threshold": 0.3, "min_silence_duration_ms": 1000},
                              condition_on_previous_text=False)
out = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segs]
t2 = time.time()
json.dump({"model": name, "load_s": round(t1 - t0, 1), "transcribe_s": round(t2 - t1, 1), "audio_s": len(audio) / 16000,
           "segments": out}, open(f"result_{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(name, "load", round(t1 - t0, 1), "s; transcribe", round(t2 - t1, 1), "s for", len(audio) / 16000, "s audio;",
      len(out), "segments;", sum(len(s["text"]) for s in out), "chars")
