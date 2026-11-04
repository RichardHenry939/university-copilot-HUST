# -*- coding: utf-8 -*-
"""(chủ 04/11) Đặt split DNS của Tailscale cho PhoneDNS: mọi tên miền trong phone_dns.ZONES -> DNS của laptop.

Chủ tự chạy:  python phone_dns_tailscale.py          (đặt / cập nhật)
              python phone_dns_tailscale.py --undo   (gỡ các tên miền này khỏi split DNS)
              python phone_dns_tailscale.py --dry    (chỉ in ra, không gọi API)
API key: tạo ở trang quản trị Tailscale > Settings > Keys > Generate access token (nên đặt hạn ngắn, vd 1 ngày).
Key gõ vào lúc chạy, không hiện chữ, không lưu ra đâu. Chỉ đụng tới đúng các tên miền trong danh sách, các split DNS khác giữ nguyên.
"""
import getpass, json, sys, urllib.error, urllib.request
import phone_dns

API = 'https://api.tailscale.com/api/v2/tailnet/-/dns/split-dns'


def call(method, key, body=None):
    req = urllib.request.Request(API, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read() or b'{}')


def main():
    undo, dry = '--undo' in sys.argv, '--dry' in sys.argv
    ip = phone_dns.tailscale_ip()
    if not ip and not undo: sys.exit('Không thấy IP Tailscale của laptop (Tailscale đang tắt?).')
    body = {z: (None if undo else [ip]) for z in phone_dns.ZONES}   # PATCH: null = gỡ, danh sách = đặt
    print(f"{'Gỡ' if undo else 'Đặt'} {len(body)} tên miền -> {ip or '-'}:")
    print('  ' + ', '.join(body))
    if dry: return
    key = getpass.getpass('Dán API key Tailscale (không hiện chữ): ').strip()
    if not key: sys.exit('Chưa nhập key.')
    try:
        after = call('PATCH', key, body)
    except urllib.error.HTTPError as e:
        sys.exit(f'Lỗi API {e.code}: {e.read().decode("utf-8", "replace")[:300]}')
    ok = [z for z in body if (z not in after if undo else after.get(z) == [ip])]
    print(f'Xong: {len(ok)}/{len(body)} tên miền đúng.' + ('' if len(ok) == len(body) else ' Thiếu: ' + ', '.join(sorted(set(body) - set(ok)))))


if __name__ == '__main__':
    main()
    try: input('Nhấn Enter để đóng')   # chạy bằng bấm đúp thì cửa sổ không tắt ngay
    except EOFError: pass
