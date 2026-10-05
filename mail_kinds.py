# -*- coding: utf-8 -*-
"""Phân loại MỌI thư trường + bài Teams thành 4 loại (Claude 2026-10-05):
  mon_hoc         -> tab Lịch (lớp, bài tập, thi môn — đã có qua mail_events)
  ngoai_khoa      -> tab Ngoại khoá (chung với iCTSV: "Hoạt động ngoại khoá có thể đăng ký")
  hanh_chinh      -> tab Hành chính (học vụ, đăng ký học tập, thủ tục, giấy tờ, BHYT, NVQS, học phí…)
  thong_bao_chung -> tab Hành chính, mục Thông báo chung (tin chung, tuyển dụng / doanh nghiệp, khảo sát, biên nhận Forms…)
  (học bổng: thư về học bổng -> loại 'hoc_bong' -> tab Học bổng)
Luật trước (0 quota); thư luật không quyết được -> gom LÔ ~30 thư / 1 lần gọi Gemini flash-lite.
Ra: school/mail_kinds.json {id: {loai, subject, from, at, tom_tat, links, nguon}}."""
import datetime as dt, json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'school' / 'mail_kinds.json'
TZ = dt.timezone(dt.timedelta(hours=7))
KINDS = ('mon_hoc', 'ngoai_khoa', 'hanh_chinh', 'thong_bao_chung', 'hoc_bong')
URL = re.compile(r'https?://[^\s"<>)\]\\]+')
REG = re.compile(r'forms\.gle|forms\.office|forms\.cloud\.microsoft|aka\.ms|docs\.google\.com/forms|ctsv\.hust\.edu\.vn/(hoat-dong|dat-ve|viet-giay)|bit\.ly|tinyurl|dang-?ky', re.I)


def load():
    try: return json.loads(OUT.read_text(encoding='utf-8'))
    except Exception: return {}


def links_of(text):
    urls = [u.rstrip('.,;') for u in URL.findall(text or '') if 'safelinks' not in u and 'aka.ms/LearnAboutSenderIdentification' not in u]
    urls = list(dict.fromkeys(urls))
    return sorted(urls, key=lambda u: 0 if REG.search(u) else 1)[:6]


def rule(m):
    """Luật chắc chắn -> loại, hoặc None (để AI quyết)."""
    s = (m.get('Subject') or '') + ' ' + (m.get('Body') or '')[:1500]
    sender = (m.get('FromName') or '') + ' ' + (m.get('FromAddress') or '')
    if m.get('CourseCode'): return 'mon_hoc'
    if re.search(r'Microsoft Forms|^My responses', sender + ' ' + (m.get('Subject') or ''), re.I): return 'thong_bao_chung'
    if re.search(r'học bổng|scholarship', m.get('Subject') or '', re.I): return 'hoc_bong'
    if re.search(r'\b[A-Z]{2,3}\d{4}\b', (m.get('Team') or '') + ' ' + (m.get('Subject') or '')) and re.search(r'lớp|buổi|bài tập|quiz|thi|kiểm tra|điểm danh', s, re.I):
        return 'mon_hoc'
    return None


PROMPT = """Phân loại từng thư / bài đăng gửi sinh viên ĐH Bách khoa Hà Nội vào ĐÚNG MỘT loại:
- mon_hoc: liên quan một MÔN HỌC cụ thể (lớp, buổi học, bài tập, thi / kiểm tra môn, tài liệu môn).
- hanh_chinh: học vụ & thủ tục (đăng ký học phần / kế hoạch học tập, học phí, giấy tờ, BHYT, nghĩa vụ quân sự, thẻ SV, ký túc xá, khảo sát bắt buộc của trường, quy định).
- ngoai_khoa: hoạt động sinh viên CÓ THỂ THAM GIA / ĐĂNG KÝ (CLB, Đoàn – Hội, cuộc thi, tuyển thành viên / đội, thể thao, tình nguyện, hội thảo, sinh hoạt định hướng / công dân, khai giảng, sự kiện).
- hoc_bong: học bổng (thông báo, hồ sơ, kết quả).
- thong_bao_chung: tin chung khác (tuyển dụng / doanh nghiệp, tham quan công ty, quảng bá, thông tin không cần hành động).
Trả lời CHỈ một JSON object: {{"<id>": {{"loai": "...", "tom_tat": "<1 câu tiếng Việt>"}}, ...}}

{items}"""


def classify(gemini=None, limit_ai=90):
    import mail_events as me
    gemini = gemini or me.gemini
    db = load(); todo = []
    for m in me.sources():
        mid = m['Id']
        if mid in db: continue
        at = (m.get('Created') or m.get('ReceivedDateTime') or '')
        try: at = dt.datetime.fromisoformat(at.replace('Z', '+00:00')).astimezone(TZ).isoformat(timespec='minutes')
        except Exception: pass
        rec = {'subject': (m.get('Subject') or '').strip()[:200], 'from': m.get('FromName') or '', 'at': at,
               'nguon': ('Teams · ' + (m.get('Team') or '')[:60]) if m.get('Source') == 'teams' else 'Mail',
               'links': links_of((m.get('Body') or '') + ' ' + (m.get('BodyHtml') or '')), 'course': m.get('CourseCode')}
        k = rule(m)
        if k: db[mid] = {**rec, 'loai': k, 'by': 'luật'}
        else: todo.append((mid, rec, me.clean(m.get('Body') or '')[:500]))
    n_ai = 0
    for i in range(0, min(len(todo), limit_ai), 30):
        batch = todo[i:i + 30]
        lines = '\n'.join(f"[{n}] Người gửi: {r['from']} | Nguồn: {r['nguon']} | Tiêu đề: {r['subject']}\n    {body.replace(chr(10), ' ')[:400]}"
                          for n, (mid, r, body) in enumerate(batch))
        try:
            out = gemini(PROMPT.format(items=lines), caller='mail')
        except Exception as e:
            print('mail_kinds gemini:', e); break
        n_ai += 1
        for n, (mid, r, body) in enumerate(batch):
            x = (out or {}).get(str(n)) or (out or {}).get(f'[{n}]') or {}
            if x.get('loai') in KINDS: db[mid] = {**r, 'loai': x['loai'], 'tom_tat': (x.get('tom_tat') or '')[:300], 'by': 'AI'}
    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'total': len(db), 'ai_calls': n_ai, 'pending': max(0, len(todo) - limit_ai)}


def by_kind(kind, days=120):
    lim = (dt.datetime.now(TZ) - dt.timedelta(days=days)).isoformat()
    return sorted([{**v, 'id': k} for k, v in load().items() if v.get('loai') == kind and (v.get('at') or '') >= lim],
                  key=lambda x: x.get('at') or '', reverse=True)


if __name__ == '__main__':
    import sys; sys.stdout.reconfigure(encoding='utf-8')
    print(classify())
    from collections import Counter
    print(Counter(v['loai'] for v in load().values()))
