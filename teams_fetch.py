# -*- coding: utf-8 -*-
"""Đọc Microsoft Teams của trường cho UC (Claude 2026-10-04) — CHỈ ĐỌC.

Dùng hồ sơ Chrome đồng bộ (school_fetch, tự đăng nhập) + token Graph của chính trang Teams web:
  • lớp (joinedTeams) → kênh → bài đăng (kể cả bài đã SỬA: mỗi lần sửa là một phiên bản để so "Trước → Nay")
  • thẻ bài tập của app Assignments (tên bài + "Due …") → hạn nộp
  • file trong thư mục của từng kênh (bỏ Recordings, ảnh chụp chat, .loop)
Không gửi tin, không bấm gì, không tải lên. Khoá school/chrome.lock dùng chung với mail + qldt.
Ra: school/teams/posts.json (cùng dạng với school/mail/inbox.json để mail_events xử lý chung)
     school/teams/files.json (danh sách file + link tải tạm thời, teams_files.py tải về)
  python teams_fetch.py   -> {ok, teams, posts_new, files}"""
import json, re, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIR = HERE / 'school' / 'teams'
POSTS = DIR / 'posts.json'
FILES = DIR / 'files.json'
KEEP = 1500

JS = r"""async () => {
  let tok = null;
  for (const k of Object.keys(localStorage)) { if (!/accesstoken/i.test(k)) continue;
    try { const o = JSON.parse(localStorage.getItem(k)); if (/graph\.microsoft\.com\/ChannelMessage\.Read\.All/i.test(o.target)) tok = o.secret; } catch (e) {} }
  if (!tok) return {ok: false, error: 'no graph token'};
  const g = async u => {
    for (let i = 0; i < 3; i++) {
      let r;   // giới hạn 30 s/lần gọi: fetch treo thì page.evaluate chờ vô hạn và giữ khoá Chrome (lỗi 15:16 4/10)
      try { r = await fetch(u.startsWith('http') ? u : 'https://graph.microsoft.com/v1.0' + u, {headers: {Authorization: 'Bearer ' + tok}, signal: AbortSignal.timeout(30000)}); }
      catch (e) { if (i < 2) continue; return {error: 'timeout'}; }
      if (r.status === 429) { await new Promise(s => setTimeout(s, 3000 * (i + 1))); continue; }
      return r.ok ? r.json() : {error: r.status};
    }
    return {error: 429};
  };
  const text = h => (h || '').replace(/<br\s*\/?>|<\/p>|<\/div>|<\/li>/gi, '\n').replace(/<a [^>]*href="([^"]+)"[^>]*>([^<]*)<\/a>/gi, '$2 ($1)')
     .replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
     .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  const cardText = a => { try { const out = []; const walk = o => { if (!o || typeof o !== 'object') return;
      if (typeof o.text === 'string' && o.text.trim()) out.push(o.text.trim()); for (const v of Object.values(o)) walk(v); };
      walk(JSON.parse(a.content)); return out.join('\n'); } catch (e) { return ''; } };
  const res = {ok: true, teams: [], posts: [], files: [], errors: []};
  const teams = (await g('/me/joinedTeams')).value || [];
  for (const t of teams) {
    res.teams.push({id: t.id, name: t.displayName});
    const chs = (await g(`/teams/${t.id}/channels`)).value || [];
    for (const c of chs) {
      let url = `/teams/${t.id}/channels/${c.id}/messages?$top=50`;
      for (let page = 0; page < 3 && url; page++) {
        const m = await g(url); if (m.error) { res.errors.push(`${t.displayName}/${c.displayName}: ${m.error}`); break; }
        for (const x of (m.value || [])) {
          if (x.messageType !== 'message' || x.deletedDateTime) continue;
          const from = x.from && x.from.user ? x.from.user.displayName : x.from && x.from.application ? 'app:' + x.from.application.displayName : '';
          const cards = (x.attachments || []).filter(a => /card/.test(a.contentType || '')).map(cardText).filter(Boolean);
          const files = (x.attachments || []).filter(a => a.contentType === 'reference').map(a => a.name);
          res.posts.push({id: x.id, team: t.displayName, teamId: t.id, channel: c.displayName, from, subject: x.subject || '',
                          created: x.createdDateTime, modified: x.lastModifiedDateTime || x.createdDateTime,
                          body: (text(x.body && x.body.content) + (cards.length ? '\n' + cards.join('\n') : '')).slice(0, 20000), files});
        }
        url = m['@odata.nextLink'] || null;
      }
      const ff = await g(`/teams/${t.id}/channels/${c.id}/filesFolder`);
      if (!ff.parentReference) continue;
      const walk = async (itemId, path, depth) => {
        const ch = await g(`/drives/${ff.parentReference.driveId}/items/${itemId}/children?$top=200`);
        for (const it of (ch.value || [])) {
          if (it.folder) { if (depth < 3 && !/^recordings$/i.test(it.name)) await walk(it.id, path + it.name + '/', depth + 1); continue; }
          res.files.push({id: it.id, driveId: ff.parentReference.driveId, name: it.name, path, size: it.size, modified: it.lastModifiedDateTime,
                          team: t.displayName, channel: c.displayName, url: it['@microsoft.graph.downloadUrl'] || null,
                          qxh: it.file && it.file.hashes ? it.file.hashes.quickXorHash : null, web: it.webUrl});
        }
      };
      await walk(ff.id, '', 0);
    }
  }
  return res;
}"""


def _load(p, empty):
    try: return json.loads(p.read_text(encoding='utf-8'))
    except Exception: return empty


def fetch():
    import school_fetch as f
    from school_mail import ChromeLock
    from playwright.sync_api import sync_playwright
    with ChromeLock(), sync_playwright() as p:
        ctx = f._launch(p, True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto('https://teams.cloud.microsoft/', wait_until='commit', timeout=90000)
            res = None
            for i in range(30):   # chờ Teams tự lấy token Graph (hoặc chuyển sang đăng nhập)
                page.wait_for_timeout(3000)
                if any(h in page.url for h in ('login.microsoftonline', 'adfs', 'sso.hust', 'asso.hust')):
                    f._through_sso(page, 'teams.cloud.microsoft', deadline=120); continue
                try: has = page.evaluate("() => Object.keys(localStorage).some(k => /accesstoken/i.test(k) && /ChannelMessage\\.Read/.test(localStorage.getItem(k) || ''))")
                except Exception: has = False
                if has: break
            res = page.evaluate(JS)
        finally:
            try: ctx.close()
            except Exception: pass
    if not res.get('ok'): return {'ok': False, 'error': res.get('error')}
    DIR.mkdir(parents=True, exist_ok=True)
    box = _load(POSTS, {'items': []}); have = {m['Id'] for m in box['items']}
    new = []
    for x in res['posts']:
        vid = f"teams:{x['id']}@{x['modified']}"   # mỗi lần sửa bài = 1 phiên bản mới -> so Trước/Nay với bản trước
        if vid in have: continue
        first = (x['body'].split('\n') or [''])[0][:120]
        new.append({'Id': vid, 'ConversationId': f"teams:{x['id']}", 'Subject': x['subject'] or first,
                    'FromName': x['from'], 'FromAddress': f"{x['team']} › {x['channel']}", 'ReceivedDateTime': x['modified'],
                    'Created': x['created'], 'Edited': x['modified'] != x['created'], 'Body': x['body'], 'Team': x['team'],
                    'Channel': x['channel'], 'Files': x['files'], 'Source': 'teams',
                    'fetched_at': dt.datetime.now().isoformat(timespec='seconds')})
    box['items'] = sorted(box['items'] + new, key=lambda m: m['ReceivedDateTime'])[-KEEP:]
    box['teams'] = res['teams']; box['last_fetch'] = dt.datetime.now().isoformat(timespec='seconds'); box['errors'] = res['errors']
    POSTS.write_text(json.dumps(box, ensure_ascii=False, indent=1), encoding='utf-8')
    FILES.write_text(json.dumps({'at': box['last_fetch'], 'items': res['files']}, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'ok': True, 'teams': len(res['teams']), 'posts_new': len(new), 'posts': len(box['items']), 'files': len(res['files']), 'errors': res['errors'][:5]}


if __name__ == '__main__':
    try: r = fetch()
    except Exception as e: r = {'ok': False, 'error': f'{type(e).__name__}: {e}'[:300]}
    print(json.dumps(r, ensure_ascii=False))
