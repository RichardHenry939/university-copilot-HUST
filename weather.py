# -*- coding: utf-8 -*-
"""(v1.00.45 tiếp, 01/11 tối) Thời tiết + chất lượng không khí quanh trường cho tab "10000 bước chạy". CHỈ ĐỌC, không cần khoá.

Nguồn: Open-Meteo (api.open-meteo.com, air-quality-api.open-meteo.com) — số liệu MÔ HÌNH, cập nhật 15 phút / lần,
không phải trạm đo tại trường. AQI là US AQI (không phải VN_AQI; ngưỡng "kém" của đặc tả VN_AQI > 150 dùng gần đúng là US AQI > 150).
Chỉ gửi đi toạ độ khu trường, không gửi gì của chủ. Đệm school/weather.json 15 phút.
"Phù hợp để ra ngoài" là điểm UC tự tính (công thức ở score()), không phải chỉ số chính thức.
"""
import datetime as dt, json, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'weather.json'
TZ = dt.timezone(dt.timedelta(hours=7))
LAT, LON = 21.0052, 105.8431   # Đại học Bách khoa Hà Nội
CACHE_S = 15 * 60
WMO = {0: 'Trời quang', 1: 'Ít mây', 2: 'Có mây', 3: 'Nhiều mây', 45: 'Sương mù', 48: 'Sương mù', 51: 'Mưa phùn nhẹ', 53: 'Mưa phùn',
       55: 'Mưa phùn dày', 61: 'Mưa nhỏ', 63: 'Mưa vừa', 65: 'Mưa to', 80: 'Mưa rào nhẹ', 81: 'Mưa rào', 82: 'Mưa rào mạnh',
       95: 'Dông', 96: 'Dông kèm mưa đá', 99: 'Dông kèm mưa đá'}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'UniversityCopilot/1.0'}), timeout=15) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch():
    w = _get(f'https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,apparent_temperature,'
             'relative_humidity_2m,precipitation,weather_code,wind_speed_10m,uv_index,is_day&hourly=precipitation_probability'
             '&forecast_hours=2&timezone=Asia%2FBangkok')
    a = _get(f'https://air-quality-api.open-meteo.com/v1/air-quality?latitude={LAT}&longitude={LON}&current=us_aqi,pm2_5&timezone=Asia%2FBangkok')
    c, q = w.get('current') or {}, a.get('current') or {}
    pp = ((w.get('hourly') or {}).get('precipitation_probability') or [None])
    return {'at': dt.datetime.now(TZ).isoformat(timespec='seconds'), 'time': c.get('time'), 'temp': c.get('temperature_2m'),
            'feels': c.get('apparent_temperature'), 'humidity': c.get('relative_humidity_2m'), 'rain': c.get('precipitation'),
            'rainProb': max([x for x in pp if x is not None], default=None), 'code': c.get('weather_code'),
            'sky': WMO.get(c.get('weather_code'), 'Không rõ'), 'wind': c.get('wind_speed_10m'), 'uv': c.get('uv_index'),
            'day': bool(c.get('is_day')), 'aqi': q.get('us_aqi'), 'pm25': q.get('pm2_5')}


def score(w, now):
    """Điểm 0–100 'phù hợp để ra ngoài đi bộ' + lý do trừ điểm. Ngưỡng theo đặc tả đi bộ (luật B nắng nóng, D không khí)."""
    s, why = 100, []
    def cut(n, t):
        nonlocal s
        if n: s -= n; why.append(t)
    h = now.astimezone(TZ).hour
    f = w.get('feels') if w.get('feels') is not None else w.get('temp')
    if f is not None:
        if f > 30: cut(round((f - 30) * 6), f'cảm giác {f:.0f}°C, nóng')
        elif f < 18: cut(round((18 - f) * 3), f'cảm giác {f:.0f}°C, lạnh')
    if (w.get('rain') or 0) > 0.1: cut(40, 'đang mưa')
    elif (w.get('rainProb') or 0) >= 60: cut(25, f'khả năng mưa {w["rainProb"]}%')
    elif (w.get('rainProb') or 0) >= 30: cut(10, f'khả năng mưa {w["rainProb"]}%')
    if (w.get('code') or 0) >= 95: cut(50, 'có dông')
    uv = w.get('uv') or 0
    if uv >= 8: cut(25, f'UV {uv:.0f}, rất cao')
    elif uv >= 6: cut(10, f'UV {uv:.0f}, cao')
    aqi = w.get('aqi')
    if aqi is not None:
        if aqi > 200: cut(80, f'không khí rất xấu (AQI {aqi})')
        elif aqi > 150: cut(60, f'không khí xấu (AQI {aqi})')
        elif aqi > 100: cut(30, f'không khí kém cho người nhạy cảm (AQI {aqi})')
        elif aqi > 50: cut(10, f'không khí trung bình (AQI {aqi})')
    if (w.get('wind') or 0) > 40: cut(20, f'gió mạnh {w["wind"]:.0f} km/h')
    if not w.get('day'): cut(10, 'trời tối')
    if h in (7, 18): cut(10, 'giờ cao điểm giao thông')
    s = max(0, min(100, s))
    if h >= 22 or h < 6: s, why = 0, ['giờ ngủ (22:00–06:00)']
    return s, why


def view(now=None):
    now = now or dt.datetime.now(TZ)
    try: w = json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: w = None
    if not w or (now - dt.datetime.fromisoformat(w['at'])).total_seconds() > CACHE_S:
        try:
            w = fetch(); OUT.write_text(json.dumps(w, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            if not w: return {'ok': False, 'error': f'{type(e).__name__}: {e}'[:200]}
            w = dict(w, stale=True)
    s, why = score(w, now)
    return {'ok': True, **w, 'score': s, 'why': why, 'source': 'Open-Meteo (mô hình, 15 phút/lần)'}
