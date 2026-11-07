# -*- coding: utf-8 -*-
"""(v1.00.49, chủ 02/11) Luật của xanh lá (chế độ tập trung) trên đồng hồ 24 giờ.

Xanh lá dừng trước mọi màu khác, trừ trắng (mục tiêu chính, không cảnh báo), xanh biển và tím (vẫn chạy nhưng cảnh báo liên tục):
- xanh biển (đang có buổi học / thi) -> (chủ 05/11) KHÔNG dừng: tập trung chạy tiếp, chặn giữ nguyên; trên đồng hồ
  thành XANH NÕN CHUỐI (vừa trong lịch vừa khoá như tập trung), tính cho mặt trận như xanh lá.
- vàng (giờ ngủ đêm 22–6h, phần ngủ trưa còn lại) -> (chủ 05/11) UC KẾT THÚC phiên (chốt phần đã tập trung).
- đỏ (khung thể dục UC xếp, đang đi bộ iCTSV) -> UC DỪNG BẮT BUỘC: gỡ chặn (máy tính + máy ảo), kể cả khi bạn đang tự dừng;
  hết khung thì (chủ 05/11) TỰ TIẾP TỤC. Phiên giải trí (tiêu ví) đang chạy thì kết thúc hẳn, chỉ trừ phút đã dùng.
- tím (ăn sáng 6:30–7:30 (chủ 07/11), ăn trưa 12–13h, ăn tối 19–20h / Camp 17:30–18:30) -> (chủ 05/11) UC tự
  tạm dừng, hết giờ tím thì tự tiếp tục (trước đây: chỉ nhắc mỗi 10 phút).
Gọi mỗi phút trong copilot_app.alert_loop.
Đi tắt: giờ ăn chép lại lần thứ 3 (ui/index.html, ui/widget.html, đây) — sửa lịch ăn thì sửa cả ba; chưa xét ngoại khoá
(chỉ có ở phía giao diện) như xanh biển.
"""
import datetime as dt, json, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / 'school' / 'focus_rules.json'
TZ = dt.timezone(dt.timedelta(hours=7))
BREAKFAST_WEEKEND = ('06:30', '08:00')   # (chủ 07/11) T7, CN
MEALS = {'ăn sáng': ('06:30', '07:30'), 'ăn trưa': ('12:00', '13:00'), 'ăn tối': ('19:00', '20:00')}
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
    import sleep_tonight
    if sleep_tonight.lock_until(now): return 'yellow', 'ngủ bù tối nay'   # (06/11) kết thúc phiên tập trung (hết nhạc, hết chuông); chặn do tick() giữ
    free, _ = nap.spans(ev, today)
    for a, b in free:
        if a <= hm < b: return 'yellow', f'giờ ngủ trưa ({a}–{b})'
    try:   # (chủ 05/11) đang trong lượt đi bộ iCTSV (điện thoại báo về) = thể dục = ĐỎ
        import walk_phone
        act = walk_phone.load().get('active')
        if act and act.get('start'): return 'red', f"đang đi bộ (iCTSV, từ {act['start'][11:16]})"
    except Exception as e: print('focus_rules walk_phone:', e)
    try:
        w = walk.view(now)
        sl = w.get('slot') or {}
        if w.get('red') and sl.get('start') and sl['start'][11:16] <= hm < sl['end'][11:16]:
            return 'red', f"giờ thể dục ({sl['start'][11:16]}–{sl['end'][11:16]})"
    except Exception as e: print('focus_rules walk:', e)
    try:   # (chủ 05/11) chống muộn: 15 phút trước buổi trực tiếp (buổi đầu trước 8h: từ 06:00) = tím, đi học
        import late
        for a, b in late.prep_spans(ev, today):
            if a[11:16] <= hm < b[11:16]: return 'purple', f'giờ đi học ({a[11:16]}–{b[11:16]})'
    except Exception as e: print('focus_rules late:', e)
    meals = dict(MEALS)
    if camp_today(post, today): meals['ăn tối'] = DINNER_CAMP
    if dt.date.fromisoformat(today).weekday() >= 5: meals['ăn sáng'] = BREAKFAST_WEEKEND   # (chủ 07/11) T7, CN nhà không nấu sáng
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


EXAM_FOCUS_MIN = 175   # 6 khối 25 phút + 5 lượt nghỉ 5 phút
EXAM_FOCUS_HOURS = ('06:00', '22:00')
EXAM_OFF = HERE / 'school' / 'exam_focus_off.json'   # (chủ 06/11) nghỉ tự bật tập trung một ngày


def auto_exam(post, notify, now):
    """(v1.00.65, chủ 05/11) D-2, D-1 trước thi (exam_focus): không có phiên nào thì UC tự bật tập trung, không cần MSSV, cả ngày.
    Chỉ bật ở trắng / xanh biển; tím, đỏ, vàng thì chờ. Phiên hết giờ / bị vàng kết thúc thì lượt sau tự bật lại."""
    import exam_focus, wallet
    if not EXAM_FOCUS_HOURS[0] <= now.strftime('%H:%M') < EXAM_FOCUS_HOURS[1]: return None
    subj = exam_focus.subject(now.date().isoformat())
    if not subj: return None
    try:   # (chủ 06/11) nghỉ ốm / đi khám: school/exam_focus_off.json {"date": "YYYY-MM-DD"} -> hôm đó không tự bật; ngày khác như cũ
        if json.loads(EXAM_OFF.read_text(encoding='utf-8')).get('date') == now.date().isoformat(): return None
    except Exception: pass
    if color_now(post, now)[0] not in ('white', 'blue'): return None
    with wallet.lock:
        st = wallet.load()
        if st.get('active'): return None
        wallet.start_focus(st, EXAM_FOCUS_MIN, subj, now); wallet.save(st)
    notify('UC · tự bật tập trung trước thi', f'{subj}. Phiên {EXAM_FOCUS_MIN} phút đã chạy, đã chặn. Giờ ăn / thể dục tự dừng rồi tự tiếp.')
    return ('auto_start', subj)


def tick(post, notify, now=None):
    """(06/11) Trong khung ngủ bù: sau luật thường, giữ tín hiệu chặn của máy tính tới giờ hết (không cần phiên tập trung)."""
    r = _tick(post, notify, now)
    import sleep_tonight, wallet
    t = (now or dt.datetime.now(TZ)).astimezone(TZ); u = sleep_tonight.lock_until(t)
    if u: wallet._signal(True, u, t)
    return r


def _phase_sync(st, now):
    """(chủ 07/11) Đổi pha trong phiên tập trung: vào quãng nghỉ 5 phút -> gỡ chặn + báo "Đã bắt đầu nghỉ";
    vào khối tập trung -> chặn lại + báo "Đã bắt đầu tập trung". Gọi trong wallet.lock, st là bản vừa load (tự lưu khi đổi).
    -> (tiêu đề, nội dung) để báo, hoặc None. Đi tắt: tick 1 phút/lần nên pha đổi trễ tối đa ~1 phút; khoá điện thoại theo vòng của phone_lock."""
    import wallet
    a = st['active']; p = wallet.progress(st, now)
    if not p or p['phase'] not in ('focus', 'break'): return None
    key = f"{p['phase']}{p['index']}"
    prev = a.get('phase_seen'); a['phase_seen'] = key
    if prev == key: return None
    wallet.save(st)
    if p['phase'] == 'break':
        wallet._signal(False, None, now)
        return ('UC · Đã bắt đầu nghỉ', f"Nghỉ {p['phase_min']} phút, đã gỡ chặn. Hết nghỉ UC tự chặn lại.")
    wallet._signal(True, (now + dt.timedelta(seconds=wallet._left_s(a, now))).isoformat(timespec='seconds'), now)
    if prev is None and p['index'] == 0: return None   # mới bắt đầu phiên: đã có thông báo bắt đầu riêng
    return ('UC · Đã bắt đầu tập trung', f"Khối {p['phase_min']} phút, đã chặn lại.")


def _tick(post, notify, now=None):
    """(chủ 05/11) Luật mới:
    - TÍM (giờ ăn, đang đi bộ iCTSV) và ĐỎ (khung thể dục): UC tự tạm dừng (gỡ chặn) và hết màu đó thì TỰ TIẾP TỤC.
    - VÀNG (giờ ngủ đêm / ngủ trưa còn lại): UC KẾT THÚC luôn phiên (chốt phút / khối đã có, không để phiên cũ treo).
    - Xanh biển: chạy tiếp (xanh nõn chuối). Bạn tự bấm dừng thì UC không tự tiếp tục (trừ đỏ / vàng vẫn áp như trên).
    - Không có phiên nào + ngày trước thi: tự bật (auto_exam)."""
    import wallet
    now = (now or dt.datetime.now(TZ)).astimezone(TZ)
    with wallet.lock:
        st = wallet.load(); had = st.get('active')
        wallet.view(st, now)   # phiên hết giờ thì chốt ngay, không chờ có tab mở (nếu không ngày trước thi sẽ kẹt, không tự bật lại được)
        if had: wallet.save(st)   # (07/11) lưu cả khi phiên còn chạy: view() có thể vừa cộng khối 25 phút vào ví
        a = st.get('active') or {}
        if a.get('type') not in ('focus', 'fun'): a = None
        elif wallet.by_user(a): wallet.hold_signal(st, now)   # bạn tự bấm dừng: gia hạn chặn mỗi phút
        phase_msg = _phase_sync(st, now) if a and a.get('type') == 'focus' and not a.get('paused_at') else None
    if phase_msg: notify(*phase_msg)
    if a is None: return auto_exam(post, notify, now)
    color, why = color_now(post, now)
    if color == 'yellow':   # giờ ngủ: chốt phiên tập trung (giải trí không đụng tới — giờ ngủ đã có khoá riêng)
        with wallet.lock:
            st = wallet.load(); a = st.get('active') or {}
            if a.get('type') != 'focus': return None
            r = wallet.end_focus(st, now, at=now, cut='giờ ngủ'); wallet.save(st)
        notify('UC · đã kết thúc tập trung', f"Đang là {why}. Phiên tập trung kết thúc ({r['blocks']} khối, +{r['reward']} phút ví). Đi ngủ thôi.")
        return ('end', why)
    if color in ('red', 'purple'):
        with wallet.lock:
            st = wallet.load(); a = st.get('active') or {}
            if color == 'red' and a.get('type') == 'fun':   # (chủ 03/11) khung thể dục: giải trí dừng hẳn
                spent = wallet.end_fun(st, now)['spent']; wallet.save(st)
                notify('UC · đã dừng giải trí', f"Đang là {why}. Phiên giải trí kết thúc, ví chỉ trừ {spent} phút đã dùng. Đi tập thôi.")
                return ('fun_end', why)
            if a.get('type') != 'focus' or a.get('auto') == color: return None   # không có phiên / đã tự dừng vì đúng màu này
            if a.get('paused_at') and wallet.by_user(a) and color == 'purple': return None   # bạn đang tự dừng: giờ ăn không đụng tới
            wallet.pause(st, now, forced=why, by='uc'); st['active']['auto'] = color; wallet.save(st)
        notify('UC · đã tạm dừng tập trung', f"Đang là {why}. Phiên tập trung tạm dừng, đã gỡ chặn. Hết giờ này UC tự tiếp tục.")
        return ('pause', why)
    with wallet.lock:   # hết tím / đỏ: tự tiếp tục phiên UC đã tự dừng
        st = wallet.load(); a = st.get('active') or {}
        if a.get('type') == 'focus' and a.get('paused_at') and a.get('auto') in ('red', 'purple') and not wallet.by_user(a):
            was = a['auto']; wallet.resume(st, now); wallet.save(st)
        else:
            if a.get('type') == 'focus' and a.get('paused_at') and not wallet.by_user(a): wallet._signal(False, None, now)   # UC dừng kiểu cũ: giữ gỡ chặn
            return None
    notify('UC · tập trung tiếp tục', ('Hết giờ ăn / đi bộ' if was == 'purple' else 'Hết khung thể dục') + '. Phiên tập trung tự chạy lại, đã chặn lại.')
    return ('resume', was)
