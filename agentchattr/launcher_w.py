"""pythonw entry — redirect stdout/stderr ra file rồi chạy run.py.

Chạy bằng pythonw.exe thì sys.stdout/sys.stderr = None -> mọi print() crash
im lặng. Script này thay 2 stream bằng file log TRƯỚC khi import run.py.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.stdout = open(ROOT / "ac-stdout.log", "a", encoding="utf-8", buffering=1)
sys.stderr = open(ROOT / "ac-stderr.log", "a", encoding="utf-8", buffering=1)
sys.argv = ["run.py"]

src = (ROOT / "run.py").read_text(encoding="utf-8")
g = {"__name__": "__main__", "__file__": str(ROOT / "run.py")}
exec(compile(src, str(ROOT / "run.py"), "exec"), g)
