# -*- coding: utf-8 -*-
"""(chủ 06/11) Ngủ bù một đêm: school/sleep_override.json, tự hết tác dụng khi qua giờ, không đổi lịch các ngày khác.
lock_from..lock_until: khoá sớm hơn khoá đêm (máy tính qua tín hiệu tập trung, điện thoại ở chế độ đêm).
quiet_from..quiet_until: UC im, không toast / ntfy.
Đi tắt: đồng hồ ở ui/index.html + ui/widget.html ghi cứng ngày; muốn dùng lại thường xuyên thì làm mục đặt giờ ngủ trong UI và đọc từ một nguồn.
Không đụng khoá đêm 22–06h. File thiếu / hỏng -> như không có.
"""
import datetime as dt, json
from pathlib import Path

FILE = Path(__file__).resolve().parent / 'school' / 'sleep_override.json'
TZ = dt.timezone(dt.timedelta(hours=7))


def _load():
    try: return json.loads(FILE.read_text(encoding='utf-8'))
    except Exception: return {}


def _in(a, b, t):
    try: return dt.datetime.fromisoformat(a) <= t < dt.datetime.fromisoformat(b)
    except Exception: return False


def lock_until(now=None):
    """Đang trong khung khoá sớm -> chuỗi ISO giờ hết; không thì None."""
    d = _load(); now = now or dt.datetime.now(TZ)
    return d['lock_until'] if _in(d.get('lock_from'), d.get('lock_until'), now) else None


def quiet(at=None):
    d = _load()
    return _in(d.get('quiet_from'), d.get('quiet_until'), at or dt.datetime.now(TZ))
