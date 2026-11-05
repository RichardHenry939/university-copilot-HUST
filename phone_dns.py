# -*- coding: utf-8 -*-
"""(chủ 04/11) PhoneDNS: chặn web MXH trên điện thoại ở PhoneDefaultLock mà KHÔNG chặn trên laptop.

Cách chạy: Tailscale split DNS (trang quản trị, chủ tự đặt) giao riêng các tên miền trong ZONES cho máy chủ DNS này
(địa chỉ Tailscale của laptop, cổng 53). Điện thoại hỏi DNS cho các tên miền đó -> laptop trả "không có" với phần web
(BLOCK), còn lại (API của app Messenger...) hỏi tiếp lên mạng thật. Dữ liệu vẫn đi thẳng, không qua exit node.
  - Laptop tắt / UC tắt: không ai trả lời các tên miền này -> điện thoại vẫn không vào được (đóng mặc định).
    Cái giá: app Messenger cũng mất mạng khi laptop tắt (dùng chung tên miền facebook.com).
  - Laptop KHÔNG nhận DNS của Tailscale ("Use Tailscale DNS" tắt) -> laptop không bị chặn (đó là "BlockDefault").
Giới hạn: tắt Tailscale trên điện thoại là thoát. Đây là rào cho lúc lười, không phải két sắt.
"""
import socket, subprocess, threading, time

# MXH lấy theo danh sách dùng chung của khoá đêm, bỏ những gì Default chừa: Messenger (messenger.com), game.
# facebook.com / fb.com chỉ chặn phần web (BLOCK), vì app Messenger dùng chung tên miền. Còn lại chặn cả miền (BLOCK_ALL).
BLOCK = ('facebook.com', 'www.facebook.com', 'm.facebook.com', 'web.facebook.com', 'mbasic.facebook.com',
         'touch.facebook.com', 'mobile.facebook.com', 'free.facebook.com', 'd.facebook.com', 'x.facebook.com',
         'h.facebook.com', 'fb.com', 'www.fb.com', 'm.fb.com',
         # (chủ 04/11) YouTube web chặn, xem bằng app ReVanced (app gọi youtubei.googleapis.com / googlevideo.com, không qua các tên này)
         # youtube.com (gốc) + youtu.be KHÔNG chặn: ReVanced cần để mở link chia sẻ (thử 04/11); trên web cả hai chỉ chuyển sang www (đã chặn)
         'www.youtube.com', 'm.youtube.com', 'music.youtube.com')
BLOCK_ALL = ('fb.watch', 'instagram.com', 'threads.net', 'threads.com',           # Meta
             'tiktok.com', 'douyin.com', 'lemon8-app.com',                          # ByteDance
             'twitter.com', 'x.com', 'bsky.app', 'mastodon.social',                  # dạng X
             'reddit.com', 'redd.it', '9gag.com', 'imgur.com', 'quora.com', 'voz.vn',  # diễn đàn / ảnh chế
             'snapchat.com', 'bereal.com', 'discord.com', 'discord.gg', 'discordapp.com',
             'pinterest.com', 'pin.it', 'tumblr.com', 'vk.com', 'gapo.vn',
             'weibo.com', 'xiaohongshu.com', 'bilibili.com', 'b23.tv',            # Trung Quốc
             'twitch.tv', 'kick.com')                                               # livestream
# (chủ 05/11) Khoá trưa / đêm không chờ adb nữa (đêm 04/11 điện thoại mất adb từ 21:21 -> ReVanced không bị khoá):
# chặn luôn đường của app qua DNS. Trưa + đêm: app YouTube / ReVanced. Đêm: thêm Messenger (cả facebook.com).
NAP_ALL = ('googlevideo.com', 'youtubei.googleapis.com', 'youtube.com', 'youtu.be')
NIGHT_ALL = NAP_ALL + ('facebook.com', 'fb.com', 'messenger.com')
ZONES = ('facebook.com', 'fb.com', 'youtube.com', 'youtu.be', 'googlevideo.com', 'youtubei.googleapis.com',
         'messenger.com') + BLOCK_ALL   # đúng các tên miền phải đặt trong split DNS của Tailscale
UPSTREAM = ('1.1.1.1', '8.8.8.8')
_mode = ['default', 0.0]


def lock_mode():
    """Chế độ PhoneLock hiện tại (đọc lại mỗi 30 s). Lỗi -> 'default'."""
    if time.time() - _mode[1] > 30:
        try:
            import phone_lock
            _mode[0] = phone_lock.mode()
        except Exception: _mode[0] = 'default'
        _mode[1] = time.time()
    return _mode[0]


def qname(pkt):
    """Tên hỏi trong gói DNS (chữ thường, bỏ dấu chấm cuối). Lỗi -> ''."""
    i, parts = 12, []
    try:
        while pkt[i]:
            n = pkt[i]; parts.append(pkt[i + 1:i + 1 + n].decode('ascii', 'replace')); i += n + 1
    except IndexError: return ''
    return '.'.join(parts).lower()


def blocked(name, mode=None):
    m = mode or lock_mode()
    whole = BLOCK_ALL + (NIGHT_ALL if m == 'night' else NAP_ALL if m == 'nap' else ())
    return name in BLOCK or any(name == z or name.endswith('.' + z) for z in whole)


def nxdomain(pkt):
    """Trả lời 'không có tên này' (giữ id + câu hỏi, bỏ phần thêm)."""
    i = 12
    while i < len(pkt) and pkt[i]: i += pkt[i] + 1
    q = pkt[12:i + 5]
    flags = 0x8000 | (pkt[2] & 0x01) << 8 | 0x0080 | 3   # QR, giữ RD, RA, rcode 3
    return pkt[:2] + flags.to_bytes(2, 'big') + b'\x00\x01\x00\x00\x00\x00\x00\x00' + q


def forward(pkt):
    for up in UPSTREAM:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3)
        try: s.sendto(pkt, (up, 53)); return s.recvfrom(4096)[0]
        except OSError: continue
        finally: s.close()
    return None


def tailscale_ip():
    try:
        r = subprocess.run([r'C:\Program Files\Tailscale\tailscale.exe', 'ip', '-4'], capture_output=True, text=True,
                           timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.stdout.split()[0]
    except Exception: return None


def serve(host=None, port=53, log=print):
    host = host or tailscale_ip()
    if not host: log('phone_dns: không thấy IP Tailscale'); return
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((host, port))   # chỉ trên Tailscale, không mở ra LAN
    log(f'phone_dns: nghe {host}:{port}')
    seen = {}   # tên đã chặn -> lần ghi nhật ký gần nhất (mỗi tên tối đa 1 dòng / giờ), để soát app nào bị chặn nhầm
    while True:
        try: pkt, addr = s.recvfrom(4096)
        except OSError: continue
        def handle(pkt=pkt, addr=addr):
            name = qname(pkt); bad = blocked(name)
            if bad and time.time() - seen.get(name, 0) > 3600:
                seen[name] = time.time(); log(f'phone_dns chan: {name}')
            ans = nxdomain(pkt) if bad else forward(pkt)
            if ans: s.sendto(ans, addr)
        threading.Thread(target=handle, daemon=True).start()


def run():
    """Vòng trong UC: Tailscale lên muộn / cổng bận -> thử lại mỗi phút. Ghi vào nhật ký PhoneLock."""
    import time, phone_lock
    while True:
        try: serve(log=phone_lock.log)
        except Exception as e: phone_lock.log(f'phone_dns loi: {e}')
        time.sleep(60)


if __name__ == '__main__':
    import sys
    serve(sys.argv[1] if len(sys.argv) > 1 else None, int(sys.argv[2]) if len(sys.argv) > 2 else 53)
