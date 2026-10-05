"""Nen trong so OpenVINO IR cua PhoWhisper sang INT8 doi xung (NPU chay tot nhat) - Claude 2026-10-03.
Chay: .venv-ov\Scripts\python.exe quantize_ov.py <thu_muc_fp32> <thu_muc_int8>"""
import shutil, sys, os
from pathlib import Path
import openvino as ov, nncf
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
core = ov.Core()
for f in src.iterdir():
    if f.suffix == ".xml" and f.stem.endswith("_model") and "tokenizer" not in f.stem:
        m = core.read_model(f)
        m = nncf.compress_weights(m, mode=nncf.CompressWeightsMode.INT8_SYM)
        ov.save_model(m, dst / f.name, compress_to_fp16=True)
        print("quantized", f.name)
    elif f.suffix != ".bin" or "tokenizer" in f.stem:
        shutil.copy2(f, dst / f.name)
if not (dst / "preprocessor_config.json").exists():
    from transformers import WhisperFeatureExtractor
    WhisperFeatureExtractor(feature_size=80).save_pretrained(dst)
    print("preprocessor_config.json created (80 mel)")
print("DONE", dst)
