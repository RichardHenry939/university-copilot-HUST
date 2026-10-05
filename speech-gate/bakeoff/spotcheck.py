import sys
from faster_whisper import WhisperModel
from audio_io import load
a = load(sys.argv[1])
print("duration min", round(len(a)/16000/60,1))
m = WhisperModel(r"D:\AI\models\phowhisper-large-ct2", device="cpu", compute_type="int8", cpu_threads=8)
for start_min in (30, 90, 150):
    seg = a[start_min*60*16000:(start_min*60+60)*16000]
    segs, _ = m.transcribe(seg, language="vi", beam_size=5, vad_filter=True, vad_parameters={"threshold":0.3})
    txt = " ".join(s.text.strip() for s in segs)
    print(f"--- phút {start_min}-{start_min+1}: {txt[:600] or '(không có tiếng nói)'}", flush=True)
