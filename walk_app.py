# -*- coding: utf-8 -*-
"""(v1.00.49) Số bước THẬT từ app iCTSV (mục "10.000 bước" -> Tổng quan tháng), đọc qua giao diện máy ảo.

CTSV web chỉ trả quãng đường giải tính (bỏ lượt chậm, vd 01/11: web 0,42 km, app 1,47 km / 2.036 bước).
App có đủ từng lượt: km, số bước, giờ bắt đầu, thời lượng, tốc độ. UC đọc kèm lượt kiểm phiên iCTSV mỗi giờ
(ictsv_login.probe), lưu school/walk_app.json. CHỈ ĐỌC.

Giới hạn (đi tắt): app chỉ hiện tháng hiện tại -> ngày tháng trước giữ theo lần đọc cuối trong tháng đó
(đầu tháng mới thì vài lượt cuối tháng trước có thể chưa kịp đọc). Đọc theo nhãn giao diện; app đổi chữ thì sửa regex.
"""
import datetime as dt, json, re, time
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'school' / 'walk_app.json'
DAY = re.compile(r'^Ngày (\d+) Tháng (\d+) (\d{4})\n([\d.]+) km - Tổng thời gian: ([\d:]+)')
RUN = re.compile(r'^([\d.]+) km\n([\d,.]+) bước\n(\d\d:\d\d)\nT\.gian: ([\d:]+)\nTốc độ: ([\d:]+) /km')
MONTH = re.compile(r'^Tổng quan (\d\d)-(\d{4})$')


def _int(s): return int(re.sub(r'[^\d]', '', s) or 0)


def parse(screens):
    """screens: danh sách màn (mỗi màn = danh sách nhãn theo thứ tự). -> {'month', 'total_steps', 'days': {...}}"""
    days, cur, month, total = {}, None, None, None
    for labels in screens:
        for i, l in enumerate(labels):
            if MONTH.match(l): month = '%s-%s' % MONTH.match(l).group(2, 1)
            m = DAY.match(l)
            if m:
                cur = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
                days.setdefault(cur, {'km': float(m.group(4)), 'time': m.group(5), 'runs': []})
                continue
            r = RUN.match(l)
            if r and cur:
                run = {'at': r.group(3), 'km': float(r.group(1)), 'steps': _int(r.group(2)), 'dur': r.group(4), 'pace': r.group(5)}
                if run not in days[cur]['runs']: days[cur]['runs'].append(run)
        # tổng tháng: số ngay sau nhãn "Tổng bước chân" + "Tốc độ TB (/km)"
        if 'Tổng bước chân' in labels:
            k = labels.index('Tổng bước chân')
            nums = [x for x in labels[k + 1:k + 4] if re.fullmatch(r'[\d,.]+', x)]
            if nums: total = _int(nums[0])
    for d in days.values():
        d['runs'].sort(key=lambda r: r['at'])
        d['steps'] = sum(r['steps'] for r in d['runs'])
    return {'month': month, 'total_steps': total, 'days': days}


def read_page(nodes, adb, max_scroll=8):
    """Đang đứng ở màn Tổng quan 10.000 bước: cuộn hết danh sách, gom nhãn từng màn."""
    screens, last = [], None
    for _ in range(max_scroll):
        labels = [n['label'] for n in nodes() if n['label']]
        if labels == last: break
        screens.append(labels); last = labels
        adb('shell', 'input', 'swipe', '540', '1900', '540', '900', '500'); time.sleep(1.2)
    return parse(screens)


def save(res):
    """Gộp vào file cũ: ngày trong tháng vừa đọc thay hẳn; ngày tháng khác giữ nguyên."""
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: old = {}
    days = {k: v for k, v in (old.get('days') or {}).items() if not (res.get('month') and k.startswith(res['month']))}
    days.update(res.get('days') or {})
    out = {'at': dt.datetime.now().isoformat(timespec='seconds'), 'month': res.get('month'),
           'month_total_steps': res.get('total_steps'), 'days': dict(sorted(days.items()))}
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    return out


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {}
