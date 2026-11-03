# -*- coding: utf-8 -*-
"""(v1.00.49, chủ 02/11) Luật của xanh lá (chế độ tập trung) trên đồng hồ 24 giờ.

Xanh lá dừng trước mọi màu khác, trừ trắng (mục tiêu chính, không cảnh báo) và tím (vẫn chạy nhưng cảnh báo liên tục):
- xanh biển (đang có buổi học / thi), vàng (giờ ngủ đêm 22–6h, phần ngủ trưa còn lại)
  -> UC tự TẠM DỪNG phiên tập trung (không huỷ) + báo lý do, gỡ chặn (chủ chốt 03/11 ~19:30: UC dừng gỡ chặn,
  bạn tự bấm dừng thì giữ chặn — xem wallet.pause).
- đỏ (khung thể dục UC xếp) -> UC DỪNG BẮT BUỘC: gỡ chặn (máy tính + máy ảo), kể cả khi bạn đang tự dừng;
  phiên giải trí (tiêu ví) đang chạy thì kết thúc hẳn, chỉ trừ phút đã dùng.
- tím (ăn sáng 7:30–8:00, ăn trưa 12–13h, ăn tối 19–20h / Camp 17:30–18:30) -> nhắc mỗi 10 phút, không dừng.
Gọi mỗi phút trong copilot_app.alert_loop.
Đi tắt: giờ ăn chép lại lần thứ 3 (ui/index.html, ui/widget.html, đây) — sửa lịch ăn thì sửa cả ba; chưa xét ngoại khoá
(chỉ có ở phía giao diện) như xanh biển.
"""
import datetime as dt, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'focus_rules.json'
TZ = dt.timezone(dt.timedelta(hours=7))
MEALS = {'ăn sáng': ('07:30', '08:00'), 'ăn trưa': ('12:00', '13:00'), 'ăn tối': ('19:00', '20:00')}
DINNER_CAMP = ('17:30', '18:30')
_camp = {'day': None, 'v': False, 't': 0}


def camp_today(post, today):
    """⛺ Camp hôm nay? Đọc Notion tối đa 30 phút/lần."""
    if _camp['day'] == today and time.time() - _camp['t'] < 1800: return _camp['v']
    try:
        import daymode
        from academic import Notion
        v = daymode.mode_of(Notion(post), dt.date.fromisoformat(today)).get('mode') == 'Camp'
    except Exception as e: print('focus_rules camp:', e); v = _camp['v']
    _camp.update(day=today, v=v, t=time.time()); return v


def color_now(post, now):
    """-> (màu, mô tả) của thời điểm now theo luật lớp: xanh biển > vàng > đỏ > tím > trắng."""
    import nap, walk
    today, hm = now.date().isoformat(), now.strftime('%H:%M')
    ev = nap.events(post)
    for e in ev:
        st, en = str(e.get('start') or ''), str(e.get('end') or e.get('start') or '')
        if e.get('kind') in ('Class', 'Exam') and 'T' in st and st[:10] == today and st[11:16] <= hm < en[11:16] and 'NGHỈ' not in str(e.get('title') or ''):
            return 'blue', f"giờ {'thi' if e.get('kind') == 'Exam' else 'học'}: {e.get('title')} ({st[11:16]}–{en[11:16]})"
    if hm >= '22:00' or hm < '06:00': return 'yellow', 'giờ ngủ đêm (22:00–06:00)'
    free, _ = nap.spans(ev, today)
    for a, b in free:
        if a <= hm < b: return 'yellow', f'giờ ngủ trưa ({a}–{b})'
    try:
        w = walk.view(now)
        sl = w.get('slot') or {}
        if w.get('red') and sl.get('start') and sl['start'][11:16] <= hm < sl['end'][11:16]:
            return 'red', f"giờ thể dục ({sl['start'][11:16]}–{sl['end'][11:16]})"
    except Exception as e: print('focus_rules walk:', e)
    meals = dict(MEALS)
    if camp_today(post, today): meals['ăn tối'] = DINNER_CAMP
    for k, (a, b) in meals.items():
        if a <= hm < b: return 'purple', f'giờ {k} ({a}–{b})'
    return 'white', ''


def walk_red(now):
    """Đang trong khung thể dục (đỏ) UC xếp hôm nay? Chỉ đọc walk.view (không cần Notion)."""
    try:
        import walk
        w = walk.view(now); sl = w.get('slot') or {}
        return bool(w.get('red') and sl.get('start') and sl['start'][11:16] <= now.strftime('%H:%M') < sl['end'][11:16])
    except Exception as e: print('focus_rules walk_red:', e); return False


def tick(post, notify, now=None):
    import wallet
    now = (now or dt.datetime.now(TZ)).astimezone(TZ)
    with wallet.lock:
        st = wallet.load(); a = st.get('active') or {}
        if a.get('type') not in ('focus', 'fun'): return None
        if wallet.by_user(a): wallet.hold_signal(st, now)   # bạn tự bấm dừng: gia hạn chặn mỗi phút
        uc_paused = bool(a.get('paused_at')) and not wallet.by_user(a)
    if uc_paused:   # UC đã dừng: giữ tín hiệu "không chặn" (gỡ cả tín hiệu cũ còn hạn), chờ bạn bấm Tiếp tục
        wallet._signal(False, None, now); return None
    color, why = color_now(post, now)
    if color == 'red':   # (chủ 03/11) khung thể dục: UC dừng bắt buộc, gỡ chặn (kể cả khi bạn đang tự dừng); giải trí dừng hẳn
        with wallet.lock:
            st = wallet.load(); a = st.get('active') or {}
            if a.get('type') == 'fun':
                spent = wallet.end_fun(st, now)['spent']; wallet.save(st)
                notify('UC · đã dừng giải trí', f"Đang là {why}. Phiên giải trí kết thúc, ví chỉ trừ {spent} phút đã dùng. Đi tập thôi.")
                return ('fun_end', why)
            if a.get('type') != 'focus' or (a.get('paused_at') and not wallet.by_user(a)): return None
            wallet.pause(st, now, forced=why, by='uc'); wallet.save(st)
        notify('UC · đã tạm dừng tập trung', f"Đang là {why}. Phiên tập trung dừng bắt buộc, đã gỡ hết chặn. Tập xong bấm Tiếp tục để chặn lại.")
        return ('pause', why)
    if a.get('type') != 'focus' or a.get('paused_at'): return None   # đang dừng tay: im lặng, chặn đã gỡ
    if color in ('blue', 'yellow'):
        with wallet.lock:
            st = wallet.load(); a = st.get('active') or {}
            if a.get('type') != 'focus' or a.get('paused_at'): return None
            wallet.pause(st, now, by='uc'); wallet.save(st)
        notify('UC · đã tạm dừng tập trung', f"Đang là {why}. Phiên tập trung tự tạm dừng (không huỷ, đã gỡ chặn). Hết giờ thì bấm Tiếp tục để chặn lại.")
        return ('pause', why)
    if color == 'purple':
        try: s = json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: s = {}
        last = s.get('purple_at')
        if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < 600: return None
        STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps({'purple_at': now.isoformat(timespec='seconds')}), encoding='utf-8')
        notify('UC · đang là ' + why, 'Bạn vẫn đang bật tập trung. Đây là giờ sinh hoạt cá nhân: nên nghỉ để ăn / vận động.')
        return ('warn', why)
    return None
