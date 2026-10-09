# -*- coding: utf-8 -*-
"""Phân biệt người nói cho chế độ Họp (Claude 2026-10-07) — pyannote/speaker-diarization-3.1 trên CPU.
Gọi từ cổng chép lời:  diarize.py <audio> <out.json> [so_nguoi]
Ra: [{"start": s, "end": s, "speaker": "SPEAKER_00"}, ...]
Cần token Hugging Face (người dùng tự đăng nhập: .venv\\Scripts\\hf.exe auth login) và đã bấm đồng ý điều khoản
pyannote/speaker-diarization-community-1 (hoặc 3.1 + segmentation-3.0). Không có token -> thoát mã 3, cổng chép lời bỏ qua bước này."""
import json, sys, time


def main():
    audio, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None
    try:
        from huggingface_hub import get_token
        if not get_token():
            print('NO_HF_TOKEN'); sys.exit(3)
        import torch
        torch.set_num_threads(6)
        from pyannote.audio import Pipeline
        pipe, err = None, ''
        for name in ('pyannote/speaker-diarization-community-1', 'pyannote/speaker-diarization-3.1'):   # pyannote 4 khuyên community-1
            try: pipe = Pipeline.from_pretrained(name); break
            except Exception as e: err += f'{name}: {type(e).__name__} {str(e)[:150]} | '
        if pipe is None: print('LOAD_FAILED', err); sys.exit(4)
    except SystemExit:
        raise
    except Exception as e:
        print('LOAD_FAILED', type(e).__name__, str(e)[:300]); sys.exit(4)
    t0 = time.time()
    import wave, numpy as np, torch
    with wave.open(audio, 'rb') as w:   # cổng chép lời ghi sẵn 16 kHz mono PCM16
        sr = w.getframerate(); data = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype('float32') / 32768.0
    wav = torch.from_numpy(data).unsqueeze(0)
    dia = pipe({'waveform': wav, 'sample_rate': sr}, **({'num_speakers': n} if n else {}))
    ann = getattr(dia, 'speaker_diarization', dia)
    segs = [{'start': round(t.start, 2), 'end': round(t.end, 2), 'speaker': spk} for t, _, spk in ann.itertracks(yield_label=True)]
    json.dump(segs, open(out, 'w', encoding='utf-8'))
    print('OK', len(segs), 'đoạn', len({s['speaker'] for s in segs}), 'người', round(time.time() - t0), 's')


if __name__ == '__main__':
    main()
