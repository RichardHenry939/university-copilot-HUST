"""Chuyen PhoWhisper-large -> OpenVINO IR (INT8) de chay tren NPU (Claude 2026-10-03).
Chay bang .venv-ov:  .venv-ov\Scripts\python.exe export_ov.py
Va loi Python 3.14: functools.partial gan lam class attribute nay bi bind nhu method -> optimum goi sai
(NormalizedConfig.__init__() got multiple values for 'allow_new'). Boc partial trong staticmethod."""
import functools, os, sys
os.environ.setdefault("HF_HOME", r"D:\AI\Cache\huggingface"); os.environ.setdefault("HF_HUB_OFFLINE", "1")
from optimum.utils import normalized_config as nc

@classmethod
def _with_args(cls, allow_new=False, **kwargs):
    return staticmethod(functools.partial(cls, allow_new=allow_new, **kwargs))
nc.NormalizedConfig.with_args = _with_args

from optimum.exporters.openvino.__main__ import main_export
from optimum.intel import OVConfig, OVWeightQuantizationConfig

out = sys.argv[1] if len(sys.argv) > 1 else r"D:\AI\models\phowhisper-large-ov-int8"
main_export("vinai/PhoWhisper-large", output=out, task="automatic-speech-recognition-with-past",
            ov_config=OVConfig(quantization_config=OVWeightQuantizationConfig(bits=8)), convert_tokenizer=True)
print("EXPORTED", out)
