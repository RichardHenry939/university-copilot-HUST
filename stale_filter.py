# -*- coding: utf-8 -*-
"""Lọc thông báo cũ (Claude 2026-10-05, luật của người dùng):
  Có ghi ngày cụ thể -> chỉ giữ khi còn ít nhất một ngày chưa qua. Không ghi ngày -> năm n chỉ hiện thông báo của năm n
  (thông báo năm n-1, n-2… bị ẩn).
  vd năm 2026: ẩn thông báo 2025, 2024; năm 2027: ẩn thông báo 2026 trừ khi có hạn sang 2027.
Không gọi AI: chỉ đọc năm gửi + các ngày ghi rõ trong tiêu đề / nội dung."""
import datetime as dt, re

DATES = [
    re.compile(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b'),          # 14/10/2026, 14-10-2026
    re.compile(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b'),                    # 2026-10-14
    re.compile(r'\bth[áa]ng\s*(\d{1,2})\s*[/,]?\s*(?:n[ăa]m\s*)?(20\d{2})\b', re.I),   # tháng 10/2026, tháng 10 năm 2026
]


def _years(text):
    ys = set()
    for rx in DATES:
        for m in rx.finditer(text or ''):
            g = m.groups()
            y = int(g[0]) if len(g[0]) == 4 else int(g[-1])
            if 2000 <= y <= 2100: ys.add(y)
    return ys


def _year_of(at):
    try: return dt.datetime.fromisoformat(str(at).replace(' ', 'T').replace('Z', '+00:00')).year
    except Exception:
        m = re.search(r'(20\d{2})', str(at or ''))
        return int(m.group(1)) if m else None


def _dates(text):
    """Các ngày ghi rõ trong chữ -> date (tháng X/YYYY -> ngày cuối tháng)."""
    out = []
    for i, rx in enumerate(DATES):
        for m in rx.finditer(text or ''):
            g = [int(x) for x in m.groups()]
            try:
                if i == 0: out.append(dt.date(g[2], g[1], g[0]))
                elif i == 1: out.append(dt.date(g[0], g[1], g[2]))
                else:
                    nxt = dt.date(g[1] + (g[0] == 12), g[0] % 12 + 1, 1)
                    out.append(nxt - dt.timedelta(days=1))
            except ValueError:
                pass
    return out


DM = re.compile(r'(?<![\d/.\-])(\d{1,2})[/.](\d{1,2})(?![\d/.\-]|\.\d)')   # "24/02" không ghi năm -> năm của thông báo


def keep(at, *texts, now=None):
    """True nếu thông báo còn hợp lệ (người dùng 5/10):
    • có ghi ngày cụ thể -> giữ khi CÒN ít nhất một ngày chưa qua;
    • không ghi ngày nào -> ẩn nếu cũ hơn 90 ngày; năm n chỉ giữ thông báo gửi trong năm n."""
    now = now or dt.datetime.now()
    txt = ' '.join(t or '' for t in texts)
    ds = _dates(txt)
    y = _year_of(at)
    if y:
        for m in DM.finditer(re.sub(r'\d{1,2}[/.\-]\d{1,2}[/.\-]20\d{2}', ' ', txt)):
            try: ds.append(dt.date(y, int(m.group(2)), int(m.group(1))))
            except ValueError: pass
    if ds: return any(d >= now.date() for d in ds)
    try:   # không ghi ngày nào + cũ hơn 90 ngày -> coi như đã hết hạn
        if (now - dt.datetime.fromisoformat(str(at).replace(' ', 'T').replace('Z', '+00:00')).replace(tzinfo=None)).days > 90: return False
    except Exception: pass
    return y is None or y >= now.year


def split(items, at_key, text_keys, now=None):
    """-> (giữ, số bị ẩn)."""
    kept = [i for i in items if keep(i.get(at_key), *(str(i.get(k) or '') for k in text_keys), now=now)]
    return kept, len(items) - len(kept)
