# -*- coding: utf-8 -*-
"""(v1.00.60, chủ 04/11) Dựng dữ liệu bản đồ khuôn viên HUST tự vẽ: ui/assets/hust-plan.json.

Lấy HÌNH DẠNG thật từ OpenStreetMap (Overpass): toà nhà (có tên / số hiệu), đường, sân, cây xanh, mặt nước trong khung quanh trường,
quy đổi kinh / vĩ độ -> toạ độ bản vẽ 0..W (giữ đúng tỉ lệ), làm gọn số điểm. Giao diện UC tự vẽ SVG từ file này (không cần nền ảnh,
không cần khoá API, chạy cả khi mất mạng). Dữ liệu © OpenStreetMap contributors (ODbL) — giao diện phải ghi nguồn.
Chạy lại khi muốn cập nhật:  python build_campus_map.py
"""
import json, math, re, sys, urllib.parse, urllib.request
from pathlib import Path

S, N, W_, E = 21.0012, 21.0082, 105.8395, 105.8500   # khung: khuôn viên chính + các phố bao quanh
OUT = Path(__file__).resolve().parent / 'ui' / 'assets' / 'hust-plan.json'
WIDTH = 1000

Q = f"""[out:json][timeout:90];
(way["building"]({S},{W_},{N},{E});
 way["highway"~"^(primary|secondary|tertiary|residential|unclassified|service|pedestrian|footway|living_street)$"]({S},{W_},{N},{E});
 way["leisure"~"^(stadium|pitch|park|garden)$"]({S},{W_},{N},{E});
 way["landuse"~"^(grass|recreation_ground)$"]({S},{W_},{N},{E});
 way["natural"="water"]({S},{W_},{N},{E}););
out geom tags;
relation(16092230);
out geom;"""
# (04/11, chủ: "đừng vơ Bạch Mai, nhà dân, Xây dựng... vào"; "lấy bản đồ Hội Sinh viên làm chuẩn") relation 16092230 = vùng
# "Đại học Bách khoa Hà Nội" trên OSM, khớp phạm vi tranh Hội Sinh viên (Đại Cồ Việt – Giải Phóng – Trần Đại Nghĩa – Lê Thanh Nghị).
# Toà / sân có tâm nằm trong vùng này được gắn 'h': 1 -> giao diện sơn khối màu; phần còn lại vẽ như bản đồ thường.
HUST_REL = 16092230

k = math.cos(math.radians((S + N) / 2))
HEIGHT = WIDTH * (N - S) / ((E - W_) * k)


def xy(p):
    return round((p['lon'] - W_) / (E - W_) * WIDTH, 1), round((N - p['lat']) / (N - S) * HEIGHT, 1)


def simplify(pts, eps=1.2):
    """Bỏ điểm gần như thẳng hàng (Douglas–Peucker đơn giản) cho file nhẹ.
    (04/11) Vòng khép kín (toà nhà: điểm đầu = điểm cuối) phải tách làm 2 nửa trước, nếu không cả toà bị rút còn 2 điểm -> không hiện."""
    if len(pts) < 3: return pts
    if pts[0] == pts[-1] and len(pts) > 4:
        far = max(range(1, len(pts) - 1), key=lambda j: math.hypot(pts[j][0] - pts[0][0], pts[j][1] - pts[0][1]))
        return simplify(pts[:far + 1], eps)[:-1] + simplify(pts[far:], eps)
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy) or 1e-9
    i, dmax = 0, 0
    for j in range(1, len(pts) - 1):
        d = abs(dy * pts[j][0] - dx * pts[j][1] + x2 * y1 - y2 * x1) / L
        if d > dmax: i, dmax = j, d
    if dmax <= eps: return [pts[0], pts[-1]]
    return simplify(pts[:i + 1], eps)[:-1] + simplify(pts[i:], eps)


def key_of(t):
    name = (t.get('ref') or t.get('name') or '').strip()
    return re.sub(r'^(Nhà|Toà|Tòa|Ký túc xá)\s+', '', name).replace(' ', ''), name


def main():
    req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=urllib.parse.urlencode({'data': Q}).encode(),
                                 headers={'User-Agent': 'UC-campus-map/1.0 (personal project)'})
    d = json.load(urllib.request.urlopen(req, timeout=120))
    out = {'nguon': '© OpenStreetMap contributors (ODbL)', 'w': WIDTH, 'h': round(HEIGHT), 'toa': [], 'duong': [], 'xanh': [], 'san': [], 'nuoc': []}
    rel = next(e for e in d['elements'] if e['type'] == 'relation' and e['id'] == HUST_REL)
    rings = [[xy(p) for p in m['geometry']] for m in rel['members'] if m.get('role') == 'outer' and m.get('geometry')]
    segs = [(r[i], r[i + 1]) for r in rings for i in range(len(r) - 1)]

    def inside(c):   # tia ngang, đếm số lần cắt (chẵn/lẻ) — không cần nối các đoạn ranh giới theo thứ tự
        x, y = c; n = 0
        for (x1, y1), (x2, y2) in segs:
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1): n += 1
        return n % 2 == 1
    out['bien'] = [simplify(r) for r in rings]
    for e in d['elements']:
        if e['type'] == 'relation': continue
        g, t = e.get('geometry'), e.get('tags', {})
        if not g: continue
        pts = simplify([xy(p) for p in g])
        if 'building' in t:
            key, name = key_of(t)
            cx = round(sum(p[0] for p in pts) / len(pts), 1); cy = round(sum(p[1] for p in pts) / len(pts), 1)
            out['toa'].append({'p': pts, 'k': key, 'n': name, 'c': [cx, cy], **({'h': 1} if inside((cx, cy)) else {})})
        elif 'highway' in t:
            out['duong'].append({'p': pts, 'l': t['highway'], 'n': t.get('name', '')})
        elif t.get('leisure') in ('stadium', 'pitch'):
            cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
            out['san'].append({'p': pts, 'n': t.get('name', ''), **({'h': 1} if inside((cx, cy)) else {})})
        elif t.get('natural') == 'water':
            out['nuoc'].append({'p': pts})
        else:
            out['xanh'].append({'p': pts})
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    hk = sorted({t['k'] for t in out['toa'] if t.get('h') and re.fullmatch(r'[A-ZĐ]{1,2}\d{0,2}[A-Za-z]*', t['k'])})
    print(f"{sum(1 for t in out['toa'] if t.get('h'))} toà trong khuôn viên: {' '.join(hk)}")
    print(f"{len(out['toa'])} toà,{len(out['duong'])} đường, {len(out['san'])} sân, {len(out['xanh'])} xanh, {len(out['nuoc'])} nước -> {OUT} "
          f"({OUT.stat().st_size // 1024} KB, {out['w']}x{out['h']})")


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
