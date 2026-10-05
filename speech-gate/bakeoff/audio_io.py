"""Giải mã audio -> float32 mono 16 kHz (PyAV 19 bỏ tham số metadata_errors mà faster-whisper 1.2.1 còn dùng)."""
import av, numpy as np
def load(path, sr=16000):
    out = []
    with av.open(path, mode="r") as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in c.decode(audio=0):
            for f in rs.resample(frame):
                out.append(f.to_ndarray().reshape(-1))
        for f in rs.resample(None):
            out.append(f.to_ndarray().reshape(-1))
    return np.concatenate(out).astype(np.float32) / 32768.0
