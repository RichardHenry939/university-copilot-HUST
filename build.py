"""Build the single unified n8n workflow "University — Copilot".

Sections merged from existing workflows (Codex agents + Freebuff phases) are copied
node-for-node, renamed with a prefix, and given their own staggered schedule plus an
on-demand webhook. New sections: Copilot chat brain (Gemini, LM Studio fallback) and
Morning/Evening brief (LM Studio worker).

Run:  python build.py            -> create/update (inactive unless --activate)
      python build.py --activate
"""
import uc_config as cfg
import copy, json, os, re, sys, uuid
from n8napi import api, NOTION, GEMINI, LMSTUDIO, APPKEY, DRIVE
from exprfix import fix_tree

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = cfg.path("n8n_template_dir")
STATE = os.path.join(HERE, "state.json")
NS = uuid.UUID("6b1f4c1e-8f53-4d0a-9c3e-2f6c1d7a0b11")
WF_NAME = "University — Copilot (hệ thống hợp nhất)"
TZ = "Asia/Ho_Chi_Minh"

DB = {
    "intake": cfg.notion("intake"),
    "tasks": cfg.notion("academic_tasks"),
    "daily": cfg.notion("daily_plan"),
    "events": cfg.notion("calendar_events"),
    "courses": cfg.notion("courses"),
    "eq": cfg.notion("exam_questions"),
    "materials": cfg.notion("materials"),
    "brief": cfg.notion("daily_brief"),
}

STATE_DB = cfg.notion("semester_state")      # Semester State
TRACKER_DB = cfg.notion("credit_tracker")    # Semester Credit Tracker
GRADES_DB = cfg.notion("grades")     # 📊 Grades & Transcript
ATTEND_DB = cfg.notion("attendance")     # 🧑‍🏫 Attendance
CONDUCT_DB = cfg.notion("conduct")    # 🏅 Điểm rèn luyện (tạo 03/10)
RESEARCH_DB = cfg.notion("research_requests")   # 🔍 Research Requests
NOTEBOOK_DB = cfg.notion("notebooklm_inbox")   # 🧠 NotebookLM Inbox
WORK_DB = cfg.notion("academic_work")       # 📋 Academic Work
REVISION_DB = cfg.notion("exam_revision")   # 📝 Exam Revision
CERT_DBS = [cfg.notion("cert_catalog"), cfg.notion("cert_rules"), cfg.notion("cert_mine")]   # chứng chỉ: danh mục / quy định / của tôi
MODES_DB = cfg.notion("day_modes")       # 🌗 Chế độ ngày
WEEKLY_DB = cfg.notion("weekly_reviews")      # 📅 Weekly Reviews
CONTROL_DB = cfg.notion("control")     # 🎛️ University Control
BACKUP_DB = cfg.notion("backup")      # 💾 Backup & Drive Sync
MILESTONES_DB = cfg.notion("milestones")   # ⚙️ Mốc năm học
GRAD_DB = cfg.notion("graduation")       # 🎓 Xét tốt nghiệp (Home Dashboard)
SUMMER_DB = cfg.notion("summer")     # ☀️ Summer Planning
ATTEMPTS_DB = cfg.notion("attempts")   # 🔁 Lần học (lịch sử lần học — QCĐT 2025)
SCHOOL_LOG_DB = cfg.notion("school_log")   # 🏫 Đồng bộ trường (nhật ký đồng bộ qldt/iCTSV)
EVENTS_TRACK_DB = cfg.notion("events_track")   # 📡 Sự kiện theo dõi (mail trường)
PHONE_PAGE = cfg.notion("phone_page")         # 📱 University Copilot (điện thoại) — trang riêng cấp cao nhất
EXTRA_DB = cfg.notion("extracurricular")          # 🎯 Hoạt động ngoại khoá (CTSV + mail/Teams)
RESULTS_DB = cfg.notion("research_results")    # 🌐 Research Results


def sid(*parts):
    return str(uuid.uuid5(NS, "|".join(parts)))

# --------------------------------------------------------------------------- merge
SECTIONS = [
    # prefix, source id, title, {old trigger name: new cron or None to keep}, run-now webhook
    ("A1", "jJEKXFiaNFd5658j", "Mục 2 · Intake: TKB / Deadline (Codex)", {"Every 15 Minutes": "0 0/15 * * * *"}, True),
    ("A2", "nnIyFww4eY5qdSgM", "Mục 3·30 · University Inbox: tài liệu (Codex)", {"Every 15 Minutes": "0 5/15 * * * *"}, True),
    ("A3", "WyAsZmZOXqR8yibs", "Mục 3·40 · Coursework Breakdown (Codex)", {"Every 15 Minutes": "0 10/15 * * * *"}, True),
    ("A4", "VsytHV7Cuy21P66F", "Mục 6 · Dynamic Daily Planning (Codex)", {}, True),
    ("S5", "i1DOTALMrMxYwJOI", "Mục 5 · Progress Recorder (Codex)", {"Every 30 Minutes": "0 20/30 * * * *"}, True),
    ("S6", "7fD3LcYmOr3KMDvx", "Mục 7 · Material Recommendations (Codex)", {}, True),
    ("C9", "phaseICouncilBridge", "Mục 9 · Council Bridge (Freebuff)", {}, False),
    ("H10", "phaseHHealthPing1", "Mục 10 · Health Ping (Freebuff)", {"Health Ping · 6h": "0 0 */6 * * *"}, False),
    ("R10", "phaseHRecon00001", "Mục 10 · Reconciliation (Freebuff)", {"Reconcile · 6h": "0 30 */6 * * *"}, False),
    ("QU", "phaseB0000000001", "Mục 1 · Quick Upload form (Freebuff)", {}, False),
]
DROP_TYPES = {"n8n-nodes-base.manualTrigger", "n8n-nodes-base.executeWorkflowTrigger"}
TRIGGER_TYPES = {"n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.webhook", "n8n-nodes-base.formTrigger"}
REF_PATTERNS = [
    (r"(\$\(\s*)(['\"])(.+?)\2", 3),
    (r"(\$node\[\s*)(['\"])(.+?)\2", 3),
    (r"(\$items\(\s*)(['\"])(.+?)\2", 3),
]

def rename_refs(value, names):
    if isinstance(value, str):
        def fix(m):
            old = m.group(3)
            return m.group(1) + m.group(2) + names.get(old, old) + m.group(2)
        for pat, _ in REF_PATTERNS:
            value = re.sub(pat, fix, value)
        return value
    if isinstance(value, list):
        return [rename_refs(v, names) for v in value]
    if isinstance(value, dict):
        return {k: rename_refs(v, names) for k, v in value.items()}
    return value

def merge_section(prefix, src_id, title, retime, run_now, y_off):
    w = json.load(open(os.path.join(SRC, src_id + ".json"), encoding="utf-8-sig"))
    nodes = [n for n in w["nodes"] if n["type"] not in DROP_TYPES and not n["name"].startswith("DR ")]
    keep = {n["name"] for n in nodes}
    names = {n["name"]: f"{prefix} · {n['name']}" for n in nodes}
    xs = [n["position"][0] for n in nodes]; ys = [n["position"][1] for n in nodes]
    x0, y0 = min(xs), min(ys)
    out_nodes, triggers = [], []
    for n in nodes:
        m = copy.deepcopy(n)
        m["name"] = names[n["name"]]
        m["id"] = sid(prefix, n["name"])
        m["position"] = [n["position"][0] - x0 + 200, n["position"][1] - y0 + y_off + 120]
        m["parameters"] = rename_refs(m.get("parameters", {}), names)
        if "webhookId" in m:
            m["webhookId"] = sid(prefix, n["name"], "webhook")
        p = m["parameters"]
        # Health ping used the Notion credential id under the Gemini credential type.
        if m["type"] == "n8n-nodes-base.httpRequest":
            url = str(p.get("url", ""))
            if "generativelanguage.googleapis.com" in url:
                m["credentials"] = copy.deepcopy(GEMINI); p["nodeCredentialType"] = "googlePalmApi"
            elif "api.notion.com" in url:
                m["credentials"] = copy.deepcopy(NOTION); p["nodeCredentialType"] = "notionApi"
        if m["type"] == "n8n-nodes-base.scheduleTrigger" and n["name"] in retime:
            p["rule"] = {"interval": [{"field": "cronExpression", "expression": retime[n["name"]]}]}
        if m["type"] in TRIGGER_TYPES:
            triggers.append(n["name"])
        out_nodes.append(m)
    conns = {}
    for src, by_type in w["connections"].items():
        if src not in keep:
            continue
        nt = {}
        for ctype, outs in by_type.items():
            new_outs = []
            for o in outs:
                new_outs.append([dict(c, node=names[c["node"]]) for c in (o or []) if c["node"] in keep])
            nt[ctype] = new_outs
        conns[names[src]] = nt
    # reachability check (dropped DR / trigger nodes must not orphan real logic)
    reach, stack = set(), [names[t] for t in triggers]
    sched = [t for t in triggers if next(x for x in nodes if x["name"] == t)["type"] == "n8n-nodes-base.scheduleTrigger"]
    for t in [names[x] for x in triggers]:
        pass
    # nodes fed by a removed executeWorkflowTrigger also count as entry points
    removed_entry_targets = set()
    for src, by_type in w["connections"].items():
        srcnode = next((x for x in w["nodes"] if x["name"] == src), None)
        if srcnode and srcnode["type"] in DROP_TYPES:
            for o in by_type.get("main", []):
                for c in (o or []):
                    removed_entry_targets.add(c["node"])
    while stack:
        cur = stack.pop()
        if cur in reach:
            continue
        reach.add(cur)
        for ctype, outs in conns.get(cur, {}).items():
            for o in outs:
                for c in o:
                    stack.append(c["node"])
    sub = {names[n["name"]] for n in nodes if any(k.startswith("ai_") for k in conns.get(names[n["name"]], {}))}
    orphans = [x for x in names.values() if x not in reach and x not in sub]
    if orphans:
        print(f"  ! {prefix}: unreachable nodes after merge: {orphans}")
    # on-demand webhook wired like the first schedule trigger (or the removed entry target)
    if run_now:
        first_targets = []
        if sched:
            first_targets = conns.get(names[sched[0]], {}).get("main", [[]])[0]
        if not first_targets and removed_entry_targets:
            first_targets = [{"node": names[t], "type": "main", "index": 0} for t in removed_entry_targets if t in names]
        hook = f"{prefix} · Chạy ngay (webhook)"
        out_nodes.append({"id": sid(prefix, "runnow"), "name": hook, "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [0, y_off + 340], "webhookId": sid(prefix, "runnow", "webhook"),
            "parameters": {"path": f"copilot-run-{prefix.lower()}", "httpMethod": "GET", "responseMode": "onReceived", "options": {}}})
        conns[hook] = {"main": [first_targets]}
    h = max(ys) - y0 + 420
    out_nodes.append(sticky(prefix + "-note", f"## {title}\nNguồn: workflow `{src_id}` (giữ nguyên logic). Chạy ngay: `/webhook/copilot-run-{prefix.lower()}`" if run_now
                            else f"## {title}\nNguồn: workflow `{src_id}` (giữ nguyên logic).",
                            [-60, y_off], max(xs) - x0 + 600, h, 4))
    return out_nodes, conns, h

def sticky(key, content, pos, w, h, color):
    return {"id": sid("sticky", key), "name": f"Ghi chú {key}", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
            "position": pos, "parameters": {"content": content, "width": int(w), "height": int(h), "color": color}}

# --------------------------------------------------------------------------- shared snapshot
def notion_http(name, pos, url, body_expr, method="POST", extra=None):
    n = {"id": sid("node", name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
         "parameters": {"method": method, "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
                        "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": body_expr, "options": {}},
         "credentials": copy.deepcopy(NOTION), "executeOnce": True, "alwaysOutputData": True, "onError": "continueRegularOutput"}
    if extra:
        n.update(extra)
    return n

DATES_JS = r"""
const tz = 'Asia/Ho_Chi_Minh';
const d = (offsetDays) => new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(new Date(Date.now() + offsetDays * 86400000));
const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', hour12: false }).format(new Date()));
return [{ json: { today: d(0), tomorrow: d(1), in8: d(8), hour, kind: hour < 12 ? 'Sáng' : 'Tối' } }];
"""

CONTEXT_JS = r"""
const P = '__PREFIX__';
const tz = 'Asia/Ho_Chi_Minh';
const rows = (n) => { try { return $(P + n).first().json.results || []; } catch (e) { return []; } };
const T = (p, k) => ((p[k] && p[k].title) || []).map(t => t.plain_text).join('');
const X = (p, k) => ((p[k] && p[k].rich_text) || []).map(t => t.plain_text).join('');
const S = (p, k) => (p[k] && ((p[k].select && p[k].select.name) || (p[k].status && p[k].status.name))) || '';
const D = (p, k) => (p[k] && p[k].date && p[k].date.start) || '';
const R = (p, k) => ((p[k] && p[k].relation) || []).map(r => r.id);
const N = (p, k) => (p[k] && typeof p[k].number === 'number') ? p[k].number : null;
const fmt = (s) => {
  if (!s) return 'không hạn';
  const hasTime = s.length > 10;
  const o = { timeZone: tz, weekday: 'short', day: '2-digit', month: '2-digit' };
  if (hasTime) { o.hour = '2-digit'; o.minute = '2-digit'; }
  return new Intl.DateTimeFormat('vi-VN', o).format(new Date(s));
};
const dates = $(P + 'Ngày giờ').first().json;
const courses = rows('Môn đang học');
const cname = {};
for (const c of courses) { const code = X(c.properties, 'Code'); cname[c.id] = (code ? code + ' ' : '') + T(c.properties, 'Name'); }
const cn = (ids) => ids.map(i => cname[i] || 'môn khác').join(', ');
const L = [];
L.push('HÔM NAY: ' + new Intl.DateTimeFormat('vi-VN', { timeZone: tz, weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date()) + ' (ISO ' + dates.today + ')');
L.push('');
L.push('MÔN ĐANG HỌC (' + courses.length + '):');
for (const c of courses) L.push('- ' + cname[c.id] + ' · ' + (N(c.properties, 'Credits') ?? '?') + ' tín');
L.push('');
const ev = rows('Lịch 7 ngày');
L.push('LỊCH 7 NGÀY TỚI (' + ev.length + ' mục):');
const day = (s) => !s ? '' : (s.length <= 10 ? s : new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(new Date(s)));
for (const e of ev) { const p = e.properties; const w = D(p, 'When'); L.push('- ' + (day(w) === dates.today ? '[HÔM NAY] ' : (day(w) === dates.tomorrow ? '[NGÀY MAI] ' : '')) + fmt(w) + ' · ' + (S(p, 'Kind') === 'Deadline' ? 'HẠN NỘP' : 'Lên lớp') + ' · ' + T(p, 'Event') + ' · ' + cn(R(p, 'Course')) + (X(p, 'Location') ? ' · phòng ' + X(p, 'Location') : '')); }
L.push('');
const daily = rows('Việc hôm nay');
L.push('VIỆC HÔM NAY trong kế hoạch (' + daily.length + '):');
for (const t of daily) { const p = t.properties; L.push('- [daily_id ' + t.id + '] ' + T(p, 'Task') + ' · ' + S(p, 'Status') + ' · ' + (N(p, 'Estimate (hrs)') ?? '?') + 'h · ưu tiên ' + (S(p, 'Priority') || '-')); }
L.push('');
const tasks = rows('Task chưa xong');
L.push('TASK GỐC CHƯA XONG (' + tasks.length + ', sắp theo hạn):');
// (Claude 2026-10-03) "Quá hạn" = deadline THẬT của bài (Academic Work chưa nộp). Việc nhỏ trượt lịch khi bài chưa tới hạn chỉ là "dời lại" —
// bạn làm dồn theo tuần, 📅 Weekly Reviews mới kết luận ổn / không ổn.
const works = rows('Bài chưa nộp'); const wdue = {}; const wname = {};
for (const w of works) { wdue[w.id] = D(w.properties, 'Due'); wname[w.id] = T(w.properties, 'Name'); }
const realDue = (p) => { const ws = R(p, 'Academic Work').filter(i => i in wdue); return ws.length ? wdue[ws[0]] : (R(p, 'Academic Work').length ? '' : D(p, 'Due')); };
let overdue = 0, slipped = 0;
for (const t of tasks) { const p = t.properties; const due = D(p, 'Due'); const rd = realDue(p);
  const od = rd && day(rd) < dates.today; const sl = !od && due && day(due) < dates.today; if (od) overdue++; if (sl) slipped++;
  const late = od ? Math.round((new Date(dates.today) - new Date(day(rd))) / 86400000) : 0;
  L.push('- [task_id ' + t.id + '] ' + (od ? '⚠️ BÀI QUÁ HẠN THẬT ' + late + ' ngày · ' : (sl ? '↪ dời lại (bài hạn ' + fmt(rd) + ') · ' : (day(due) === dates.today ? '🔴 HẠN HÔM NAY · ' : ''))) + T(p, 'Task') + ' · hạn việc ' + fmt(due) + ' · ' + S(p, 'Status') + ' · ' + (N(p, 'Estimate (hrs)') ?? '?') + 'h · ' + cn(R(p, 'Course'))); }
L.push('=> Tổng: ' + tasks.length + ' task chưa xong; ' + overdue + ' thuộc bài đã QUÁ HẠN THẬT; ' + slipped + ' việc nhỏ dời lại (KHÔNG phải quá hạn — bạn làm dồn theo tuần).');
L.push('');
const eq = rows('Cần hỏi bạn');
L.push('ĐANG CHỜ BẠN QUYẾT (' + eq.length + '):');
for (const q of eq) { const p = q.properties; L.push('- [eq_id ' + q.id + '] ' + T(p, 'Issue') + ' · ' + S(p, 'Reason Type') + ' · ' + X(p, 'Reason').slice(0, 220)); }
const facts = { todayClasses: [], tomorrowClasses: [], deadlines7: [], overdue: [], dueToday: [] };
for (const e of ev) { const p = e.properties; const w = D(p, 'When'); const line = fmt(w) + ' · ' + T(p, 'Event') + (X(p, 'Location') ? ' · phòng ' + X(p, 'Location') : '');
  if (S(p, 'Kind') === 'Deadline') facts.deadlines7.push(line + ' · ' + cn(R(p, 'Course')));
  else if (day(w) === dates.today) facts.todayClasses.push(line);
  else if (day(w) === dates.tomorrow) facts.tomorrowClasses.push(line); }
for (const w of works) { const d = wdue[w.id];   // quá hạn: theo BÀI, deadline thật
  if (d && day(d) < dates.today) facts.overdue.push(wname[w.id] + ' · hạn ' + fmt(d) + ' · ' + cn(R(w.properties, 'Course')) + ' — đã nộp chưa?'); }
facts.slipped = 0;
for (const t of tasks) { const p = t.properties; const due = D(p, 'Due'); const rd = realDue(p); const line = T(p, 'Task') + ' · hạn ' + fmt(due) + ' · ' + cn(R(p, 'Course'));
  if (rd && day(rd) < dates.today) continue;
  if (due && day(due) < dates.today) { facts.slipped++; continue; }
  if (due && day(due) === dates.today) facts.dueToday.push(line);
  else if (due && day(due) < dates.in8) facts.deadlines7.push(line); }
facts.daily = daily.map(t => T(t.properties, 'Task') + ' · ' + S(t.properties, 'Status'));
facts.eq = eq.map(q => T(q.properties, 'Issue'));
facts.courses = courses.map(c => ({ id: c.id, code: X(c.properties, 'Code'), name: T(c.properties, 'Name') }));
const hm = (s) => s && s.length > 10 ? new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit' }).format(new Date(s)) : '';
facts.todaySlots = ev.filter(e => S(e.properties, 'Kind') !== 'Deadline' && day(D(e.properties, 'When')) === dates.today)
  .map(e => ({ time: hm(D(e.properties, 'When')), title: T(e.properties, 'Event'), room: X(e.properties, 'Location'), course: cn(R(e.properties, 'Course')) }));
return [{ json: { facts, context: L.join('\n'), today: dates.today, kind: dates.kind, counts: { courses: courses.length, events: ev.length, daily: daily.length, tasks: tasks.length, eq: eq.length } } }];
"""

def snapshot_chain(prefix, x, y):
    """Dates -> 5 Notion queries -> context text. Returns (nodes, conns, first, last)."""
    nm = lambda s: prefix + s
    today = "$('" + nm("Ngày giờ") + "').first().json"
    nodes = [
        {"id": sid("node", nm("Ngày giờ")), "name": nm("Ngày giờ"), "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [x, y], "parameters": {"jsCode": DATES_JS.strip()}},
        notion_http(nm("Môn đang học"), [x + 220, y], f"https://api.notion.com/v1/databases/{DB['courses']}/query",
                    json.dumps({"page_size": 60, "filter": {"property": "Status", "status": {"equals": "Taking"}}})),
        notion_http(nm("Lịch 7 ngày"), [x + 440, y], f"https://api.notion.com/v1/databases/{DB['events']}/query",
                    "={{ JSON.stringify({page_size:60, sorts:[{property:'When',direction:'ascending'}], filter:{and:[{property:'When',date:{on_or_after:" + today + ".today}},{property:'When',date:{before:" + today + ".in8}}]}}) }}"),
        notion_http(nm("Việc hôm nay"), [x + 660, y], f"https://api.notion.com/v1/databases/{DB['daily']}/query",
                    "={{ JSON.stringify({page_size:50, filter:{property:'Date',date:{equals:" + today + ".today}}}) }}"),
        notion_http(nm("Task chưa xong"), [x + 880, y], f"https://api.notion.com/v1/databases/{DB['tasks']}/query",
                    json.dumps({"page_size": 40, "sorts": [{"property": "Due", "direction": "ascending"}],
                                "filter": {"property": "Status", "status": {"does_not_equal": "Done"}}})),
        notion_http(nm("Bài chưa nộp"), [x + 990, y + 160], f"https://api.notion.com/v1/databases/{WORK_DB}/query",
                    json.dumps({"page_size": 60, "filter": {"and": [{"property": "Status", "status": {"does_not_equal": "Submitted"}},
                                                                    {"property": "Status", "status": {"does_not_equal": "Graded"}}]}})),
        notion_http(nm("Cần hỏi bạn"), [x + 1100, y], f"https://api.notion.com/v1/databases/{DB['eq']}/query",
                    json.dumps({"page_size": 20, "filter": {"property": "Status", "select": {"equals": "Open"}}})),
        {"id": sid("node", nm("Tổng hợp ngữ cảnh")), "name": nm("Tổng hợp ngữ cảnh"), "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [x + 1320, y], "parameters": {"jsCode": CONTEXT_JS.replace("__PREFIX__", prefix).strip()}},
    ]
    conns = {}
    for a, b in zip(nodes, nodes[1:]):
        conns[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    return nodes, conns, nodes[0]["name"], nodes[-1]["name"]

# --------------------------------------------------------------------------- chat brain
SYSTEM_PROMPT = r"""Bạn là "University Copilot" — phi công phụ học tập của một sinh viên năm 1 ngành Computer Engineering (Kỹ thuật Máy tính), Đại học Bách khoa Hà Nội (HUST). Bạn là mặt tiền DUY NHẤT của cả hệ thống: sinh viên không cần mở Notion hay n8n, chỉ cần nói chuyện với bạn.

Cách nói chuyện:
- Tiếng Việt, ngắn gọn, thân thiện, đi thẳng vào việc. Dùng gạch đầu dòng khi liệt kê.
- Chỉ dựa trên NGỮ CẢNH bên dưới và kết quả công cụ. Không bịa môn, hạn, điểm. Không có dữ liệu thì nói thẳng.
- Khi chưa chắc (môn nào, hạn ngày nào), HỎI LẠI đúng 1 câu ngắn, có gợi ý lựa chọn.
- Sinh viên KHÔNG làm đều mỗi ngày: có ngày nghỉ, có ngày dồn (Camp Mode). Đừng coi "hôm nay chưa làm" hay việc nhỏ "dời lại" là trễ, đừng cảnh báo theo ngày.
  Chỉ deadline THẬT của bài (đánh dấu BÀI QUÁ HẠN THẬT) mới là quá hạn — hỏi gọn 'đã nộp chưa?' và đề nghị đánh dấu, đừng trách móc.
  Ngày 💤 Rest (sinh viên nghỉ) thì đừng gợi ý việc, chỉ nhắc deadline thật; ngày ⛺ Camp thì giúp xếp việc dồn. Đặt chế độ bằng ghi_hoc_tap loai=che_do.
  Muốn biết ổn hay không: dùng ghi_hoc_tap loai=tuan (đánh giá cả tuần: giờ đã làm theo ngày, giờ cần tuần sau, gợi ý ngày camp).

Việc bạn làm được (công cụ):
- them_vao_he_thong: khi sinh viên báo deadline / bài tập / lịch học / thay đổi TKB mới. Viết lại thành mô tả đầy đủ, rõ môn + ngày. Hệ thống sẽ xử lý trong ≤15 phút (hoặc gọi chay_ngay với quy_trinh=a1 để xử lý luôn).
- cap_nhat_viec_hom_nay: đổi trạng thái một việc trong kế hoạch hôm nay (dùng daily_id).
- cap_nhat_task_goc: đổi trạng thái task gốc (dùng task_id).
- dong_ngoai_le: khi sinh viên đã trả lời một mục ĐANG CHỜ BẠN QUYẾT (dùng eq_id). Nếu câu trả lời chứa thông tin mới (ví dụ môn đúng là gì), gọi thêm them_vao_he_thong với thông tin đã làm rõ.
- tim_tai_lieu: tìm tài liệu đã lưu trong kho theo từ khóa / chủ đề / mã môn. Trả lời kèm link mở ngay (url Notion, Drive Backup URL).
- nhap_tkb: sinh viên gửi TKB cả kỳ (chữ hoặc ảnh) → tự tách thành danh sách lớp, gọi buoc=xem_truoc, đọc lại tóm tắt (số buổi mỗi môn, tuần đầu, đợt nghỉ, môn dự kiến không có trong TKB); sinh viên đồng ý mới gọi buoc=ghi. Luật đặc biệt (vd "thứ 2 tuần 1–2 của tháng học online") → tách lớp theo khoảng ngày hoặc ghi vào ghi_chu, và nói rõ với sinh viên phần nào ghi được, phần nào chỉ là ghi chú.
- Chuyển kỳ chạy tự động lúc 00:15 hằng ngày (đổi kỳ, Tết, hè, học lại, tín chỉ). Câu hỏi của bộ chuyển kỳ nằm trong Exception Queue như các câu hỏi khác; sinh viên trả lời → ghi_hoc_tap loai=he / module / doi_mon.
- ghi_hoc_tap: MỌI chuyện về luật môn, điểm, buổi vắng/đi muộn, điểm rèn luyện, GPA/CPA. Sinh viên nói tự nhiên, ví dụ "Giải tích theo luật là QT 30% CK 70%, vắng quá 3 buổi bị trừ điểm, nhưng tôi vắng 2 buổi rồi" → TÁCH thành các lần gọi: (1) loai=luat mon=Giải tích luat="QT 30%, CK 70%; vắng quá 3 buổi bị trừ điểm" trong_so_qt=30 vang_toi_da=3; (2) loai=vang mon=Giải tích so_buoi=2. "Được 7,5 giữa kỳ Giải tích" → loai=diem thanh_phan=giữa kỳ diem=7.5. "Còn được nghỉ mấy buổi Đại số?" / "GPA kỳ này?" → loai=xem. Luật một môn chỉ cần sinh viên nói MỘT lần — hệ thống tự nhớ; đừng hỏi lại luật đã có. Nếu kết quả có 'thieu' → hỏi lại đúng phần thiếu, nói rõ là chưa hiểu phần nào. Số liệu (điểm học phần, điểm chữ, GPA, CPA, số buổi còn được vắng) LẤY TỪ ket_qua, không tự tính.
- nghien_cuu: sinh viên muốn tìm tài liệu NGOÀI kho (Internet, Studocu, Scholar, docs…) → tạo yêu cầu, báo sẽ có kết quả sau; doc_ket_qua_nghien_cuu: đọc kết quả đã có và đưa link.
- gui_notebooklm: sinh viên thấy tài liệu khó, muốn học sâu / hỏi đáp trên tài liệu → tìm tài liệu bằng tim_tai_lieu để lấy link Drive, rồi gọi gui_notebooklm; đưa link Drive và hướng dẫn: notebooklm.google.com → Add source → Google Drive.
  Thứ tự gợi ý khi sinh viên cần tài liệu: tìm trong kho trước → không có thì đề nghị nghien_cuu → tài liệu khó thì đề nghị gui_notebooklm.
- chay_ngay: chạy ngay một quy trình nền: a1 (xử lý deadline/TKB vừa thêm), a2 (phân loại tài liệu mới), a3 (chia nhỏ bài lớn), a4 (lập lại kế hoạch hôm nay).
- hoi_hoi_dong: khi sinh viên muốn hỏi Hội đồng 4 AI (Claude/Codex/Gemini + Local AI làm ghế phản biện) về một vấn đề khó — gửi hồ sơ vào phòng họp AgentChattr (3 ghế trên mạng xáo ngẫu nhiên, Local AI luôn ở Ghế 3). Báo lại thứ tự ghế, mã phiên (session_key) và chỗ xem (localhost:8300, kênh #council). Hội đồng cần vài phút.
- doc_bien_ban_hoi_dong: khi sinh viên hỏi hội đồng nói gì / đã xong chưa — đọc và tóm tắt theo từng ghế.
- chot_hoi_dong: CHỈ khi sinh viên nói rõ "chốt"/"finalize" — ghi biên bản + quyết định vào Notion. Không tự chốt.

Tệp đính kèm: ảnh/PDF sinh viên gửi được chuyển thẳng cho bạn để đọc; tệp khác được trích chữ và nằm trong tin nhắn dưới dạng "[Tệp đính kèm ...]". Ảnh TKB / ảnh đề bài có hạn nộp → trích thông tin rồi gọi them_vao_he_thong. Nếu tin nhắn ghi "(đã lưu vào Uni-Documents)" thì tài liệu đã tự được xếp vào kho, không cần ghi lại.

Luật cứng: không bao giờ xóa dữ liệu; chỉ ghi điểm / buổi vắng / luật môn khi chính sinh viên báo (không suy đoán, không bịa điểm); không đổi tín chỉ của môn; sau mỗi lần ghi, nói rõ đã ghi gì để sinh viên kiểm tra. Nếu có mục ĐANG CHỜ BẠN QUYẾT, nhắc nhẹ 1 mục ở cuối câu trả lời (không dồn dập).

(Chỉ thị kỹ thuật cho model dự phòng: /no_think)

=== NGỮ CẢNH (đọc từ Notion lúc này) ===
"""

def tool(name, desc, method, url, body=None, x=0, y=0, cred="notion"):
    p = {"toolDescription": desc, "method": method, "url": url, "options": {}}
    if cred == "notion":
        p.update({"authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi"})
    if cred == "appkey":   # gửi header X-Copilot-Key (credential "Copilot web app key") tới web app trên máy
        p.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
    if body is not None:
        p.update({"sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": body})
    n = {"id": sid("tool", name), "name": name, "type": "n8n-nodes-base.httpRequestTool", "typeVersion": 4.2,
         "position": [x, y], "parameters": p}
    if cred == "notion":
        n["credentials"] = copy.deepcopy(NOTION)
    if cred == "appkey":
        n["credentials"] = copy.deepcopy(APPKEY)
    return n

def chat_section(y):
    nodes, conns = [], {}
    chat = {"id": sid("node", "Chat"), "name": "Chat", "type": "@n8n/n8n-nodes-langchain.chatTrigger", "typeVersion": 1.4,
            "position": [0, y + 200], "webhookId": sid("chat", "webhook"),
            "parameters": {"public": True, "mode": "hostedChat", "authentication": "__CHAT_AUTH__",
                           "initialMessages": "Chào bạn 👋 Mình là University Copilot — hỏi \"hôm nay làm gì?\", \"tuần này có hạn nào?\", hoặc báo deadline mới, mình ghi giúp.",
                           "options": {"title": "University Copilot", "subtitle": "Hậu phương học tập 4 năm · HUST",
                                       "inputPlaceholder": "Hỏi gì cũng được — ví dụ: thứ 6 nộp Lab 2 IT3190…", "responseMode": "lastNode",
                                       "loadPreviousSession": "notSupported",
                                       "customCss": open(os.path.join(HERE, "chat.css"), encoding="utf-8").read()}}}
    nodes.append(chat)
    # Second front door: the local web app (copilot_app.py) posts here with the X-Copilot-Key header.
    api_hook = {"id": sid("node", "Chat · Web app (API)"), "name": "Chat · Web app (API)", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
                "position": [0, y + 380], "webhookId": sid("chat", "api-webhook"),
                "parameters": {"path": "copilot-api", "httpMethod": "POST", "authentication": "headerAuth",
                               "responseMode": "lastNode", "options": {"binaryPropertyName": "file"}},
                "credentials": copy.deepcopy(APPKEY)}
    norm = {"id": sid("node", "Chat · Đầu vào"), "name": "Chat · Đầu vào", "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [110, y + 290],
            "parameters": {"jsCode": "const it = $input.first(); const j = it.json; const b = j.body || j;\n// ảnh/PDF đính kèm từ web app đi kèm dưới dạng binary (file0, file1...) để Gemini đọc trực tiếp\nreturn [{ json: { chatInput: String(b.chatInput || b.message || '').slice(0, 24000), sessionId: String(b.sessionId || 'web-default').slice(0, 120) }, binary: it.binary || {} }];"}}
    nodes += [api_hook, norm]
    snap, sconns, first, last = snapshot_chain("Chat · ", 220, y + 200)
    nodes += snap; conns.update(sconns)
    conns["Chat"] = {"main": [[{"node": norm["name"], "type": "main", "index": 0}]]}
    conns[api_hook["name"]] = {"main": [[{"node": norm["name"], "type": "main", "index": 0}]]}
    conns[norm["name"]] = {"main": [[{"node": first, "type": "main", "index": 0}]]}
    sysmsg = {"id": sid("node", "Chat · Lời nhắc hệ thống"), "name": "Chat · Lời nhắc hệ thống", "type": "n8n-nodes-base.code", "typeVersion": 2,
              "position": [1760, y + 200],
              "parameters": {"jsCode": "const sys = " + json.dumps(SYSTEM_PROMPT) + " + $json.context;\nconst src = $('Chat · Đầu vào').first(); const inp = src.json;\nreturn [{ json: { system: sys, chatInput: inp.chatInput, sessionId: inp.sessionId }, binary: src.binary || {} }];"}}
    nodes.append(sysmsg)
    conns[last] = {"main": [[{"node": sysmsg["name"], "type": "main", "index": 0}]]}
    agent = {"id": sid("node", "Copilot"), "name": "Copilot", "type": "@n8n/n8n-nodes-langchain.agent", "typeVersion": 3.1,
             "position": [1980, y + 200],
             "parameters": {"promptType": "define", "text": "={{ $json.chatInput }}", "needsFallback": True,
                            "options": {"systemMessage": "={{ $json.system }}", "maxIterations": 8, "enableStreaming": False,
                                        "passthroughBinaryImages": True, "passthroughBinaryPdfs": True}}}
    nodes.append(agent)
    conns[sysmsg["name"]] = {"main": [[{"node": "Copilot", "type": "main", "index": 0}]]}
    gem = {"id": sid("node", "Não · Gemini"), "name": "Não · Gemini", "type": "@n8n/n8n-nodes-langchain.lmChatGoogleGemini", "typeVersion": 1.1,
           "position": [1840, y + 460], "parameters": {"modelName": "models/gemini-3.5-flash", "options": {"temperature": 0.3, "maxOutputTokens": 2048}},
           "credentials": copy.deepcopy(GEMINI), "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000}
    lm = lmstudio_node("Não dự phòng · LM Studio", [1960, y + 460], "qwen3-8b")
    mem = {"id": sid("node", "Trí nhớ hội thoại"), "name": "Trí nhớ hội thoại", "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow", "typeVersion": 1.4,
           "position": [2080, y + 460], "parameters": {"sessionIdType": "customKey", "sessionKey": "={{ $('Chat · Đầu vào').first().json.sessionId }}", "contextWindowLength": 12}}
    nodes += [gem, lm, mem]
    conns["Não · Gemini"] = {"ai_languageModel": [[{"node": "Copilot", "type": "ai_languageModel", "index": 0}]]}
    conns["Não dự phòng · LM Studio"] = {"ai_languageModel": [[{"node": "Copilot", "type": "ai_languageModel", "index": 1}]]}
    conns["Trí nhớ hội thoại"] = {"ai_memory": [[{"node": "Copilot", "type": "ai_memory", "index": 0}]]}
    F = lambda key, desc, typ="string": "$fromAI('" + key + "', " + json.dumps(desc, ensure_ascii=False) + ", '" + typ + "')"
    tools = [
        tool("them_vao_he_thong",
             "Ghi một deadline / bài tập / buổi học / thay đổi lịch MỚI vào cửa nhập Academic Intake. Hệ thống nền sẽ tự đối chiếu môn, tạo Academic Work, sự kiện lịch và task gốc.",
             "POST", "https://api.notion.com/v1/pages",
             "={{ JSON.stringify({parent:{database_id:'" + DB["intake"] + "'}, properties:{Request:{title:[{text:{content:" + F("tieu_de", "Tiêu đề ngắn, ví dụ 'Lab 2 IT3190'") + "}}]}, Input:{rich_text:[{text:{content:" + F("noi_dung", "Mô tả đầy đủ bằng tiếng Việt tự nhiên: mã/tên môn, loại việc, ngày bắt đầu, hạn (ngày + giờ nếu có), phòng, ghi chú") + "}}]}, 'Input Type':{select:{name:" + F("loai", "Một trong: Auto, Deadline, Class") + "}}, Status:{status:{name:'Not started'}}}}) }}",
             2200, y + 520),
        tool("cap_nhat_viec_hom_nay", "Đổi trạng thái một việc trong kế hoạch hôm nay (Daily Task). Trạng thái hợp lệ: Not started, In progress, Done.",
             "PATCH", "=https://api.notion.com/v1/pages/{{ " + F("daily_id", "daily_id lấy từ ngữ cảnh") + " }}",
             "={{ JSON.stringify({properties:{Status:{status:{name:" + F("trang_thai", "Not started | In progress | Done") + "}}}}) }}", 2320, y + 520),
        tool("cap_nhat_task_goc", "Đổi trạng thái một task gốc (Academic Tasks). Trạng thái hợp lệ: To do, Doing, Done.",
             "PATCH", "=https://api.notion.com/v1/pages/{{ " + F("task_id", "task_id lấy từ ngữ cảnh") + " }}",
             "={{ JSON.stringify({properties:{Status:{status:{name:" + F("trang_thai", "To do | Doing | Done") + "}}}}) }}", 2440, y + 520),
        tool("dong_ngoai_le", "Đánh dấu một mục ĐANG CHỜ BẠN QUYẾT là đã giải quyết, kèm ghi chú quyết định của sinh viên.",
             "PATCH", "=https://api.notion.com/v1/pages/{{ " + F("eq_id", "eq_id lấy từ ngữ cảnh") + " }}",
             "={{ JSON.stringify({properties:{Status:{select:{name:'Resolved'}}, Reason:{rich_text:[{text:{content:'Đã quyết qua Copilot: ' + " + F("ghi_chu", "Quyết định / thông tin sinh viên đưa ra") + "}}]}}}) }}", 2560, y + 520),
        tool("tim_tai_lieu", "Tìm tài liệu đã lưu trong kho (Course Materials) theo từ khóa, chủ đề hoặc mã môn — tìm trong tên, Keywords và Summary. Kết quả có link Notion (url) và link Drive (Drive Backup URL) để đưa cho sinh viên mở ngay.",
             "POST", f"https://api.notion.com/v1/databases/{DB['materials']}/query",
             "={{ JSON.stringify({page_size:12, filter:{or:[{property:'Material',title:{contains:" + F("tu_khoa", "Từ khóa ngắn hoặc mã môn") + "}},{property:'Keywords',rich_text:{contains:" + F("tu_khoa", "Từ khóa ngắn hoặc mã môn") + "}},{property:'Summary',rich_text:{contains:" + F("tu_khoa", "Từ khóa ngắn hoặc mã môn") + "}}]}}) }}", 2680, y + 520),
        # (Claude 2026-10-03) học tập: luật môn, điểm, chuyên cần, rèn luyện — logic + tính điểm bằng Python trong web app
        tool("ghi_hoc_tap",
             "Ghi hoặc tra cứu HỌC TẬP của sinh viên. Gọi mỗi khi sinh viên nói về: LUẬT của một môn (trọng số điểm quá trình/cuối kỳ, số buổi được vắng, cách cộng/trừ điểm — thường do giảng viên nói buổi 1), ĐIỂM (chuyên cần, bài tập, thí nghiệm, giữa kỳ, quá trình, cuối kỳ, tổng kết), BUỔI VẮNG / ĐI MUỘN, ĐIỂM RÈN LUYỆN, trả lời câu hỏi chuyển kỳ (hè này học hè / nghỉ / thực tập → loai=he; chọn Module → loai=module; dời một môn sang kỳ khác → loai=doi_mon, ky=S..), KẾT QUẢ môn không chấm điểm số hoặc được miễn (“qua Lý luận TDTT”, “trượt Bóng rổ 1”, “được miễn môn X” → loai=ket_qua, lua_chon=dat|truot|mien), LỊCH THI (“thi giữa kỳ Giải tích 15/11 lúc 7h phòng D3” → loai=thi, thanh_phan=giữa kỳ, ngay, gio, phong), KẾ HOẠCH ÔN THI (“ôn giữa kỳ Giải tích chương 1-3, đang ôn, còn yếu” → loai=on_thi, thanh_phan, ngay=ngày thi, luat=chủ đề cần ôn, trang_thai=chua|dang|xong, lua_chon=yeu|vua|chac, so_buoi=số giờ dự kiến), ĐÁNH GIÁ TUẦN (“tuần này thế nào”, “mình có đang chậm không” → loai=tuan, đọc lại kết luận + gợi ý ngày camp), CHẾ ĐỘ NGÀY (“mai mình nghỉ” → loai=che_do, lua_chon=rest, ngay; “thứ Bảy camp 7 tiếng” → loai=che_do, lua_chon=camp, ngay, so_buoi=7; “hủy camp” → lua_chon=binh thuong), hoặc hỏi tình hình học tập (còn được vắng mấy buổi, điểm hiện tại, GPA, CPA). Một câu có nhiều ý thì gọi nhiều lần, mỗi lần một ý. Kết quả trả về 'da_ghi' (đã ghi gì), 'thieu' (thiếu gì để hỏi lại), 'ket_qua' (số liệu đã tính sẵn — đọc lại cho sinh viên, KHÔNG tự tính).",
             "POST", "http://host.docker.internal:8320/api/academic",
             "={{ JSON.stringify({loai:" + F("loai", "Một trong: luat | diem | vang | ren_luyen | xem | he | module | doi_mon | ket_qua | thi | on_thi | tuan | che_do") + ", mon:" + F("mon", "Tên hoặc mã môn đúng như sinh viên nói (để trống nếu là ren_luyen hoặc xem tổng hợp cả kỳ)") +
             ", luat:" + F("luat", "Với loai=luat: chép lại luật đúng ý sinh viên nói, đầy đủ, tiếng Việt. Loại khác để trống") +
             ", trong_so_qt:" + F("trong_so_qt", "Với loai=luat: phần trăm điểm QUÁ TRÌNH nếu sinh viên nói (vd 30 khi QT 30% CK 70%; 50 khi 50/50). Không nói thì để trống") +
             ", vang_toi_da:" + F("vang_toi_da", "Với loai=luat: số buổi được vắng tối đa nếu sinh viên nói. Không nói thì để trống") +
             ", thanh_phan:" + F("thanh_phan", "Với loai=diem: chuyên cần | bài tập | thí nghiệm | giữa kỳ | quá trình | cuối kỳ | tổng kết") +
             ", diem:" + F("diem", "Với loai=diem: số điểm thang 10 (vd 7.5). Với loai=ren_luyen: điểm thang 100. Không có thì để trống") +
             ", so_buoi:" + F("so_buoi", "Với loai=vang: số buổi vắng/muộn được báo, mặc định 1") +
             ", trang_thai:" + F("trang_thai", "Với loai=vang: vang | muon | co_phep") +
             ", ngay:" + F("ngay", "Ngày xảy ra dạng YYYY-MM-DD; để trống nếu là hôm nay") +
             ", ky:" + F("ky", "Với loai=ren_luyen: kỳ dạng S1..S8, để trống nếu là kỳ hiện tại. Với loai=doi_mon: kỳ đích dạng S1..S8") +
             ", lua_chon:" + F("lua_chon", "Với loai=he: hoc he | nghi | thuc tap. Với loai=module: Module 1 | Module 2 | Module 3. Với loai=ket_qua: dat | truot | mien. Với loai=on_thi: mức tự tin yeu | vua | chac. Với loai=che_do: camp | rest | binh thuong. Loại khác để trống") +
             ", gio:" + F("gio", "Với loai=thi: giờ thi dạng HH:MM nếu sinh viên nói, không thì để trống") +
             ", phong:" + F("phong", "Với loai=thi: phòng thi nếu có, không thì để trống") +
             ", ghi_chu:" + F("ghi_chu", "Ghi chú ngắn kèm theo (vd lý do vắng; với hè: môn học hè hoặc công ty, vị trí, giờ làm thực tập), có thể để trống") + "}) }}",
             3280, y + 520, cred="appkey"),
        tool("nghien_cuu",
             "Tìm TÀI LIỆU NGOÀI INTERNET (Research Hub): bài giảng, giáo trình, tài liệu chính thức, lời giải, bài báo không có trong kho. Hệ thống tìm ngay trên web (1–3 phút), chỉ giữ link mở được, ghi vào Research Results; kết quả tốt nhất của một môn tự vào University Inbox để xếp vào kho tài liệu. Báo sinh viên đang tìm và có thể hỏi lại sau ít phút (doc_ket_qua_nghien_cuu).",
             "POST", "http://host.docker.internal:8320/api/research-request",
             "={{ JSON.stringify({cau_hoi:" + F("cau_hoi", "Câu hỏi/chủ đề cần tìm, đủ rõ, KÈM TÊN HOẶC MÃ MÔN") + ", nguon:" + F("nguon", "Nguồn ưu tiên nếu sinh viên nói, cách nhau dấu phẩy, chọn trong: Google Scholar, Studocu, Microsoft Learn, Python Docs, Stack Overflow; không nói thì để trống") + "}) }}",
             3400, y + 520, cred="appkey"),
        tool("doc_ket_qua_nghien_cuu", "Đọc các kết quả tìm tài liệu ngoài mới nhất (Research Results) để đưa link cho sinh viên.",
             "POST", f"https://api.notion.com/v1/databases/{RESULTS_DB}/query",
             json.dumps({"page_size": 6, "sorts": [{"timestamp": "created_time", "direction": "descending"}]}), 3520, y + 520),
        tool("nhap_tkb",
             "Nạp THỜI KHOÁ BIỂU TOÀN KỲ sinh viên gửi (chữ hoặc ảnh) vào lịch: tạo mọi buổi học của kỳ, thay buổi cũ, đánh dấu môn đang học. Luôn gọi buoc=xem_truoc trước, đọc tóm tắt cho sinh viên; chỉ khi sinh viên đồng ý mới gọi lại buoc=ghi với CÙNG dữ liệu. Nếu kết quả có 'thieu' → hỏi lại đúng chỗ đó.",
             "POST", "http://host.docker.internal:8320/api/tkb",
             "={{ JSON.stringify({buoc:" + F("buoc", "xem_truoc | ghi") + ", ky:" + F("ky", "Kỳ trong chương trình dạng S1..S8 (kỳ hiện tại nếu sinh viên không nói)") +
             ", bat_dau:" + F("bat_dau", "Ngày buổi học đầu tiên của kỳ, YYYY-MM-DD") + ", ket_thuc:" + F("ket_thuc", "Ngày buổi học cuối cùng của kỳ, YYYY-MM-DD") +
             ", lop:" + F("lop", "MẢNG JSON (dạng chuỗi) các lớp; mỗi lớp là object với các khoá: mon (tên hoặc mã môn), loai (LT, BT, TN, Lớp...), thu (2..7 hoặc CN), bat_dau và ket_thuc (HH:MM), phong, giang_vien, hinh_thuc (Online hoặc Offline), tu_ngay và den_ngay (YYYY-MM-DD, chỉ khi lớp học trong một khoảng), tuan_chan_le (chan hoặc le, nếu có), ghi_chu. Một môn nhiều buổi mỗi tuần hoặc đổi phòng theo giai đoạn thì tách thành nhiều lớp") +
             ", nghi:" + F("nghi", "MẢNG JSON (dạng chuỗi) các đợt nghỉ; mỗi đợt là object với các khoá: tu, den (YYYY-MM-DD), ly_do, mon (chỉ khi nghỉ riêng một môn). Không có thì mảng rỗng") + "}) }}",
             3160, y + 640, cred="appkey"),
        tool("gui_notebooklm",
             "Đưa một tài liệu KHÓ sang luồng học sâu NotebookLM: ghi vào NotebookLM Inbox kèm link Drive của tài liệu (lấy Drive Backup URL từ tim_tai_lieu). NotebookLM không có API: sau khi ghi, đưa sinh viên link Drive và nhắc mở notebooklm.google.com → Add source → Google Drive.",
             "POST", "https://api.notion.com/v1/pages",
             "={{ JSON.stringify({parent:{database_id:'" + NOTEBOOK_DB + "'}, properties:{Item:{title:[{text:{content:" + F("ten", "Tên tài liệu") + "}}]}, Context:{rich_text:[{text:{content:" + F("muc_dich", "Học gì / câu hỏi cần NotebookLM giúp, kèm tên môn") + "}}]}, 'Drive URL':{url:(" + F("drive_url", "Link Google Drive của tài liệu; để trống nếu chưa có") + " || null)}, 'Upload Method':{select:{name:'Google Drive'}}, NotebookLM:{select:{name:'In Drive'}}, 'NotebookLM Source Status':{select:{name:'Ready in Drive'}}, Status:{status:{name:'Not started'}}}}) }}",
             3640, y + 520),
        tool("chay_ngay", "Chạy ngay một quy trình nền thay vì đợi lịch. quy_trinh: a1 = xử lý deadline/TKB mới thêm, a2 = phân loại tài liệu mới, a3 = chia nhỏ bài lớn, a4 = lập lại kế hoạch hôm nay.",
             "GET", "=http://host.docker.internal:5678/webhook/copilot-run-{{ " + F("quy_trinh", "a1 | a2 | a3 | a4") + " }}", None, 2800, y + 520, cred=None),
        tool("hoi_hoi_dong", "Gửi một câu hỏi khó vào phòng họp Hội đồng 4 AI (AgentChattr, kênh #council). Chỉ dùng khi sinh viên yêu cầu hỏi hội đồng.",
             "POST", "http://host.docker.internal:8310/council/ask",
             "={{ JSON.stringify({question:" + F("cau_hoi", "Câu hỏi đầy đủ cho hội đồng, kèm bối cảnh môn học") + ", channel:'council'}) }}", 2920, y + 520, cred=None),
        tool("doc_bien_ban_hoi_dong", "Đọc các tin nhắn gần nhất trong phòng họp Hội đồng (kênh #council) để tóm tắt cho sinh viên xem các ghế đã nói gì.",
             "GET", "=http://host.docker.internal:8310/council/transcript?channel=council&limit={{ " + F("so_tin", "Số tin gần nhất cần đọc, ví dụ 30", "number") + " }}", None, 3040, y + 520, cred=None),
        tool("chot_hoi_dong", "CHỈ dùng khi sinh viên (Chủ tọa) nói rõ muốn CHỐT/Finalize phiên hội đồng: ghi biên bản tóm tắt và quyết định cuối vào Notion (Council Sessions).",
             "POST", "http://host.docker.internal:5678/webhook/council-finalize",
             "={{ JSON.stringify({sessionKey:" + F("session_key", "Mã phiên dạng CS-YYYYMMDD-HHMMSS nhận được khi gửi hội đồng") + ", transcript:" + F("bien_ban", "Tóm tắt ý chính từng ghế") + ", decision:" + F("quyet_dinh", "Quyết định cuối của Chủ tọa") + "}) }}", 3160, y + 520, cred=None),
    ]
    for t in tools:
        nodes.append(t)
        conns[t["name"]] = {"ai_tool": [[{"node": "Copilot", "type": "ai_tool", "index": 0}]]}
    nodes.append(sticky("chat", "## 💬 Mặt tiền · Copilot (não: Gemini, dự phòng: LM Studio local)\nĐọc ngữ cảnh Notion mới nhất mỗi tin nhắn → trả lời / ghi qua công cụ. Không xóa dữ liệu.",
                        [-60, y], 3100, 720, 6))
    return nodes, conns, 760

def lmstudio_node(name, pos, model, max_tokens=1200):
    return {"id": sid("node", name), "name": name, "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi", "typeVersion": 1.3, "position": pos,
            "parameters": {"model": {"__rl": True, "mode": "id", "value": model}, "responsesApiEnabled": False, "builtInTools": {},
                           "options": {"baseURL": "http://host.docker.internal:1234/v1", "temperature": 0.3, "maxTokens": max_tokens, "timeout": 300000}},
            "credentials": copy.deepcopy(LMSTUDIO)}

# --------------------------------------------------------------------------- brief (worker tier)
BRIEF_PROMPT_JS = r"""
const c = $json;
const ask = c.kind === 'Sáng'
  ? 'Đề xuất 3 việc nên làm HÔM NAY theo thứ tự ưu tiên, mỗi việc 1 dòng kèm lý do ngắn (hạn, số giờ ước lượng). Nếu có nhiều task QUÁ HẠN lâu, việc đầu tiên là rà lại xem task nào thực ra đã xong để đánh dấu.'
  : 'Viết 2-3 dòng: nhận xét ngắn về hôm nay và việc nên ưu tiên NGÀY MAI, mỗi dòng 1 ý kèm lý do ngắn.';
const prompt = ask + '\n\nQuy tắc: tiếng Việt, tối đa 90 chữ, mỗi dòng bắt đầu bằng "- ", chỉ dùng dữ liệu dưới đây, không bịa, không nhắc ID.\n\nDỮ LIỆU:\n' + c.context + '\n/no_think';
return [{ json: { ...c, prompt } }];
"""

BRIEF_PAGE_JS = r"""
const c = $('Bản tin · Soạn yêu cầu').first().json;
let text = String($json.text || $json.output || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
if (!text) text = '- (Model local chưa sẵn sàng lúc này — LM Studio có thể đang tắt. Phần dữ kiện phía trên vẫn chính xác.)';
const f = c.facts || {};
const blocks = [];
const H = (t) => blocks.push({ object: 'block', type: 'heading_3', heading_3: { rich_text: [{ type: 'text', text: { content: t } }] } });
const B = (t) => blocks.push({ object: 'block', type: 'bulleted_list_item', bulleted_list_item: { rich_text: [{ type: 'text', text: { content: String(t).slice(0, 1900) } }] } });
const list = (title, arr, empty) => { H(title); if (!arr || !arr.length) B(empty); else arr.slice(0, 15).forEach(B); };
if (c.kind === 'Sáng') {
  list('🏫 Hôm nay lên lớp', f.todayClasses, 'Không có tiết nào hôm nay.');
  if ((f.dueToday || []).length) list('🔴 Hạn hôm nay', f.dueToday, '');
  list('📅 Hạn nộp 7 ngày tới', f.deadlines7, 'Không có hạn nộp nào trong 7 ngày tới.');
} else {
  list('✅ Kế hoạch hôm nay', f.daily, 'Hôm nay chưa có kế hoạch nào được lập.');
  list('🏫 Ngày mai lên lớp', f.tomorrowClasses, 'Ngày mai không có tiết.');
  list('📅 Hạn nộp 7 ngày tới', f.deadlines7, 'Không có hạn nộp nào trong 7 ngày tới.');
}
if ((c.checks || []).length) list('🎓 Cần xử lý về học tập', c.checks, '');
if ((f.overdue || []).length) { H('⚠️ Bài đã qua deadline thật, chưa đánh dấu nộp (' + f.overdue.length + ')'); f.overdue.slice(0, 10).forEach(B); }
if (f.slipped) { H('↪ Việc dời lại'); B(f.slipped + ' việc nhỏ chưa làm theo lịch ngày — bình thường, đánh giá tuần (tối Chủ nhật) mới kết luận ổn hay không.'); }
if ((f.eq || []).length) list('❓ Đang chờ bạn quyết', f.eq, '');
H('💡 Gợi ý của Copilot (model local)');
for (const line of text.split('\n')) {
  const s = line.trim();
  if (!s) continue;
  const isBullet = /^[-*•]\s+/.test(s);
  const content = s.replace(/^[-*•]\s+/, '').replace(/\*\*/g, '').slice(0, 1900);
  blocks.push(isBullet
    ? { object: 'block', type: 'bulleted_list_item', bulleted_list_item: { rich_text: [{ type: 'text', text: { content } }] } }
    : { object: 'block', type: 'paragraph', paragraph: { rich_text: [{ type: 'text', text: { content } }] } });
}
const title = 'Bản tin ' + (c.kind === 'Sáng' ? 'sáng ' : 'tối ') + c.today;
const body = { parent: { database_id: '__BRIEF_DB__' }, icon: { type: 'emoji', emoji: c.kind === 'Sáng' ? '☀️' : '🌙' },
  properties: { 'Bản tin': { title: [{ text: { content: title } }] }, 'Loại': { select: { name: c.kind } },
    'Ngày': { date: { start: c.today } }, 'Model': { rich_text: [{ text: { content: 'LM Studio · qwen3-8b (local)' } }] } },
  children: blocks.slice(0, 90) };
return [{ json: { body: JSON.stringify(body), title, text } }];
"""

def brief_section(y):
    nodes, conns = [], {}
    trig = [
        {"id": sid("node", "Bản tin · 07:20"), "name": "Bản tin · 07:20", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
         "position": [0, y + 120], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 20 7 * * *"}]}}},
        {"id": sid("node", "Bản tin · 21:30"), "name": "Bản tin · 21:30", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
         "position": [0, y + 280], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 30 21 * * *"}]}}},
        {"id": sid("node", "Bản tin · Chạy ngay (webhook)"), "name": "Bản tin · Chạy ngay (webhook)", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, y + 440], "webhookId": sid("brief", "webhook"),
         "parameters": {"path": "copilot-brief", "httpMethod": "GET", "responseMode": "lastNode", "options": {}}},
    ]
    nodes += trig
    snap, sconns, first, last = snapshot_chain("Bản tin · ", 220, y + 280)
    nodes += snap; conns.update(sconns)
    for t in trig:
        conns[t["name"]] = {"main": [[{"node": first, "type": "main", "index": 0}]]}
    # (Claude 2026-10-03) kiểm tra học tập thay "Exam Revision Planner" ChatGPT: checks.py trong web app, lỗi thì bản tin vẫn chạy
    chk = {"id": sid("node", "Bản tin · Kiểm tra học tập"), "name": "Bản tin · Kiểm tra học tập", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
           "position": [1540, y + 120], "onError": "continueRegularOutput", "alwaysOutputData": True,
           "parameters": {"method": "POST", "url": "http://host.docker.internal:8320/api/checks", "authentication": "genericCredentialType",
                          "genericAuthType": "httpHeaderAuth", "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
                          "body": "{}", "options": {"timeout": 180000}},
           "credentials": copy.deepcopy(APPKEY)}
    merge = {"id": sid("node", "Bản tin · Gộp cảnh báo"), "name": "Bản tin · Gộp cảnh báo", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [1760, y + 120],
             "parameters": {"jsCode": r"""
const c = $('__LAST__').first().json;
const w = ($json && Array.isArray($json.canh_bao)) ? $json.canh_bao : [];
const lines = w.map(x => (x.muc === 'cao' ? '🔴 ' : x.muc === 'vua' ? '🟠 ' : '• ') + x.noi_dung);
const context = String(c.context || '') + (lines.length ? '\n\nCẢNH BÁO HỌC TẬP (đưa lên đầu phần gợi ý):\n' + lines.join('\n') : '');
return [{ json: { ...c, context, checks: lines, checksOk: !!($json && $json.ok) } }];
""".replace("__LAST__", last).strip()}}
    nodes += [chk, merge]
    prompt = {"id": sid("node", "Bản tin · Soạn yêu cầu"), "name": "Bản tin · Soạn yêu cầu", "type": "n8n-nodes-base.code", "typeVersion": 2,
              "position": [1760, y + 280], "parameters": {"jsCode": BRIEF_PROMPT_JS.strip()}}
    chain = {"id": sid("node", "Bản tin · Viết (local)"), "name": "Bản tin · Viết (local)", "type": "@n8n/n8n-nodes-langchain.chainLlm", "typeVersion": 1.9,
             "position": [1980, y + 280], "parameters": {"promptType": "define", "text": "={{ $json.prompt }}"},
             "onError": "continueRegularOutput", "alwaysOutputData": True}
    lm = lmstudio_node("Thợ · LM Studio (qwen3-8b)", [1980, y + 480], "qwen3-8b", 900)
    page = {"id": sid("node", "Bản tin · Dựng trang"), "name": "Bản tin · Dựng trang", "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [2200, y + 280], "parameters": {"jsCode": BRIEF_PAGE_JS.replace("__BRIEF_DB__", DB["brief"]).strip()}}
    save = notion_http("Bản tin · Lưu vào Notion", [2420, y + 280], "https://api.notion.com/v1/pages", "={{ $json.body }}")
    nodes += [prompt, chain, lm, page, save]
    conns[last] = {"main": [[{"node": chk["name"], "type": "main", "index": 0}]]}
    conns[chk["name"]] = {"main": [[{"node": merge["name"], "type": "main", "index": 0}]]}
    conns[merge["name"]] = {"main": [[{"node": prompt["name"], "type": "main", "index": 0}]]}
    conns[prompt["name"]] = {"main": [[{"node": chain["name"], "type": "main", "index": 0}]]}
    conns[chain["name"]] = {"main": [[{"node": page["name"], "type": "main", "index": 0}]]}
    conns[page["name"]] = {"main": [[{"node": save["name"], "type": "main", "index": 0}]]}
    conns[lm["name"]] = {"ai_languageModel": [[{"node": chain["name"], "type": "ai_languageModel", "index": 0}]]}
    nodes.append(sticky("brief", "## 🗞️ Bản tin sáng 07:20 / tối 21:30 (tầng thợ: LM Studio local)\nGhi vào DB 🗞️ Bản tin Copilot. Chạy thử: `/webhook/copilot-brief`",
                        [-60, y], 2700, 640, 5))
    return nodes, conns, 680

# --------------------------------------------------------------------------- web app: suggestions
SUGGEST_JS = r"""
const c = $('Gợi ý · Tổng hợp ngữ cảnh').first().json; const f = c.facts || {};
const S = [];
const short = (s, n = 70) => String(s || '').length > n ? String(s).slice(0, n - 1) + '…' : String(s || '');
for (const t of (f.dueToday || []).slice(0, 3)) S.push({ group: 'Gấp hôm nay', icon: '🔴', label: short(t), prompt: 'Giúp mình xử lý việc hạn hôm nay: ' + t });
if ((f.overdue || []).length) {
  S.push({ group: 'Dọn việc tồn', icon: '🧹', label: 'Rà ' + f.overdue.length + ' bài đã qua deadline — đã nộp chưa?', prompt: 'Liệt kê các bài đã qua deadline thật mà chưa đánh dấu nộp, hỏi mình từng bài đã nộp chưa để đánh dấu.' });
  for (const t of f.overdue.slice(0, 3)) S.push({ group: 'Dọn việc tồn', icon: '⏰', label: short(t), prompt: 'Task này mình đã làm xong rồi, đánh dấu Done giúp: ' + t });
}
for (const t of (f.deadlines7 || []).slice(0, 3)) S.push({ group: 'Sắp tới', icon: '📅', label: short(t), prompt: 'Lập kế hoạch để kịp hạn này: ' + t });
for (const q of (f.eq || []).slice(0, 3)) S.push({ group: 'Chờ bạn quyết', icon: '❓', label: short(q), prompt: 'Hỏi mình về mục đang chờ quyết: ' + q });
const quick = [
  ['☀️', 'Hôm nay mình nên làm gì?'], ['📆', 'Tuần này có hạn nộp nào?'], ['🏫', 'Ngày mai học gì, ở phòng nào?'],
  ['🗂️', 'Tìm tài liệu Giải tích I'], ['📊', 'Tóm tắt tiến độ học kỳ này'], ['🏛️', 'Hỏi hội đồng: cách ôn thi giữa kỳ hiệu quả?'],
];
for (const [icon, p] of quick) S.push({ group: 'Hỏi nhanh', icon, label: p, prompt: p });
// Tài liệu Notion đã gợi ý hôm nay (Course Materials: Suggested Today + Suggestion Reason, do S6 tạo)
const cname = Object.fromEntries((f.courses || []).map(x => [x.id, [x.code, x.name].filter(Boolean).join(' ')]));
const TT = (p, k) => ((p[k] && p[k].title) || []).map(t => t.plain_text).join('');
const XX = (p, k) => ((p[k] && p[k].rich_text) || []).map(t => t.plain_text).join('');
let mats = [];
try { mats = ($('Gợi ý · Tài liệu Notion gợi ý').first().json.results || []).map(m => ({
  title: TT(m.properties, 'Material'), reason: XX(m.properties, 'Suggestion Reason'), url: m.url,
  type: (m.properties.Type && m.properties.Type.select && m.properties.Type.select.name) || '',
  course: ((m.properties.Course && m.properties.Course.relation) || []).map(r => cname[r.id] || '').filter(Boolean).join(', ') })); } catch (e) {}
return [{ json: { suggestions: S, materials: mats, courses: f.courses || [], counts: c.counts, today: c.today,
  todaySlots: f.todaySlots || [], stats: { overdue: (f.overdue || []).length, due7: (f.deadlines7 || []).length, dueToday: (f.dueToday || []).length, waiting: (f.eq || []).length },
  generatedAt: new Date().toISOString() } }];
"""

def suggest_section(y):
    nodes, conns = [], {}
    hook = {"id": sid("node", "Gợi ý · Web app"), "name": "Gợi ý · Web app", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [0, y + 200], "webhookId": sid("suggest", "webhook"),
            "parameters": {"path": "copilot-suggest", "httpMethod": "GET", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
            "credentials": copy.deepcopy(APPKEY)}
    snap, sconns, first, last = snapshot_chain("Gợi ý · ", 220, y + 200)
    mats = notion_http("Gợi ý · Tài liệu Notion gợi ý", [1760, y + 200], f"https://api.notion.com/v1/databases/{DB['materials']}/query",
                       json.dumps({"page_size": 20, "filter": {"property": "Suggested Today", "checkbox": {"equals": True}}}))
    out = {"id": sid("node", "Gợi ý · Tạo gợi ý"), "name": "Gợi ý · Tạo gợi ý", "type": "n8n-nodes-base.code", "typeVersion": 2,
           "position": [1980, y + 200], "parameters": {"jsCode": SUGGEST_JS.strip()}}
    nodes += [hook] + snap + [mats, out]; conns.update(sconns)
    conns[hook["name"]] = {"main": [[{"node": first, "type": "main", "index": 0}]]}
    conns[last] = {"main": [[{"node": mats["name"], "type": "main", "index": 0}]]}
    conns[mats["name"]] = {"main": [[{"node": out["name"], "type": "main", "index": 0}]]}
    nodes.append(sticky("suggest", "## 💡 Gợi ý cho web app (GET /webhook/copilot-suggest, cần X-Copilot-Key)", [-60, y], 2000, 420, 3))
    return nodes, conns, 460

# --------------------------------------------------------------------------- web app: file ingest (Uni-Documents -> Drive -> Notion Inbox -> A2)
DRIVE_BACKUP_FOLDER = "1JFJ24-rGAXbOsLdIxg-xs488htvw0wYQ"   # My Drive/University/Course Materials Backup
INBOX_DB = cfg.notion("inbox")
INGEST_ROW_JS = r"""
const b = $('Nhập file · Web app').first().json.body || {};
const up = $json || {};
const driveId = up.id || '';
const driveLink = driveId ? 'https://drive.google.com/file/d/' + driveId + '/view' : '';
const ctx = [
  b.courseCode || b.courseName ? 'Môn: ' + [b.courseCode, b.courseName].filter(Boolean).join(' ') : '',
  'Đã xếp vào Uni-Documents\\' + (b.relPath || ''),
  b.category ? 'Loại: ' + b.category : '',
  b.summary ? 'Tóm tắt: ' + b.summary : '',
  driveLink ? 'Drive: ' + driveLink : 'Drive: (sao lưu lỗi)',
].filter(Boolean).join(' | ').slice(0, 1900);
const body = { parent: { database_id: '__INBOX__' },
  properties: { Upload: { title: [{ text: { content: (b.title || b.fileName || 'Tài liệu').slice(0, 200) } }] },
    Context: { rich_text: [{ text: { content: ctx } }] },
    Files: { files: [{ name: (b.fileName || 'file').slice(0, 100), type: 'external', external: { url: b.downloadUrl } }] },
    'Triage Status': { status: { name: 'Not started' } } } };
return [{ json: { body: JSON.stringify(body), driveLink } }];
"""

def ingest_section(y):
    nodes, conns = [], {}
    hook = {"id": sid("node", "Nhập file · Web app"), "name": "Nhập file · Web app", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [0, y + 200], "webhookId": sid("ingest", "webhook"),
            "parameters": {"path": "copilot-file-ingest", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
            "credentials": copy.deepcopy(APPKEY)}
    dl = {"id": sid("node", "Nhập file · Tải từ máy"), "name": "Nhập file · Tải từ máy", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [220, y + 200],
          "parameters": {"method": "GET", "url": "={{ $json.body.downloadUrl }}",
                         "options": {"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}}}
    up = {"id": sid("node", "Nhập file · Sao lưu Drive"), "name": "Nhập file · Sao lưu Drive", "type": "n8n-nodes-base.googleDrive", "typeVersion": 3,
          "position": [440, y + 200], "onError": "continueRegularOutput", "alwaysOutputData": True,
          "parameters": {"resource": "file", "operation": "upload", "authentication": "oAuth2", "inputDataFieldName": "data",
                         "name": "={{ $('Nhập file · Web app').first().json.body.driveName }}",
                         "driveId": {"__rl": True, "mode": "list", "value": "My Drive", "cachedResultName": "My Drive"},
                         "folderId": {"__rl": True, "mode": "id", "value": DRIVE_BACKUP_FOLDER, "cachedResultName": "Course Materials Backup"},
                         "options": {"simplifyOutput": True}},
          "credentials": copy.deepcopy(DRIVE)}
    row = {"id": sid("node", "Nhập file · Dựng dòng Inbox"), "name": "Nhập file · Dựng dòng Inbox", "type": "n8n-nodes-base.code", "typeVersion": 2,
           "position": [660, y + 200], "parameters": {"jsCode": INGEST_ROW_JS.replace("__INBOX__", INBOX_DB).strip()}}
    create = notion_http("Nhập file · Tạo dòng University Inbox", [880, y + 200], "https://api.notion.com/v1/pages", "={{ $json.body }}")
    create.pop("onError"); create.pop("alwaysOutputData")
    kick = {"id": sid("node", "Nhập file · Gọi A2 ngay"), "name": "Nhập file · Gọi A2 ngay", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [1100, y + 200], "onError": "continueRegularOutput",
            "parameters": {"method": "GET", "url": "http://host.docker.internal:5678/webhook/copilot-run-a2", "options": {}}}
    res = {"id": sid("node", "Nhập file · Kết quả"), "name": "Nhập file · Kết quả", "type": "n8n-nodes-base.code", "typeVersion": 2,
           "position": [1320, y + 200],
           "parameters": {"jsCode": "const r = $('Nhập file · Tạo dòng University Inbox').first().json;\nreturn [{ json: { ok: !!r.id, inboxId: r.id || null, inboxUrl: r.url || null, driveLink: $('Nhập file · Dựng dòng Inbox').first().json.driveLink } }];"}}
    nodes += [hook, dl, up, row, create, res]
    chain = [hook, dl, up, row, create, res]   # (Claude 2026-10-03) A2 do web app bơm tuần tự, không kích theo từng file
    for a, b in zip(chain, chain[1:]):
        conns[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    # (Claude 2026-10-03) chống trùng: ghi đè nội dung file Drive đã có (file sửa trên máy) + gỡ tài liệu bản cũ khỏi kho
    up_hook = {"id": sid("node", "Cập nhật file · Webhook"), "name": "Cập nhật file · Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
               "position": [0, y + 420], "webhookId": sid("ingest", "update"),
               "parameters": {"path": "copilot-file-update", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
               "credentials": copy.deepcopy(APPKEY)}
    up_dl = {"id": sid("node", "Cập nhật file · Tải từ máy"), "name": "Cập nhật file · Tải từ máy", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
             "position": [220, y + 420],
             "parameters": {"method": "GET", "url": "={{ $json.body.downloadUrl }}",
                            "options": {"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}}}}
    up_drive = {"id": sid("node", "Cập nhật file · Ghi đè Drive"), "name": "Cập nhật file · Ghi đè Drive", "type": "n8n-nodes-base.googleDrive", "typeVersion": 3,
                "position": [440, y + 420], "onError": "continueRegularOutput", "alwaysOutputData": True,
                "parameters": {"resource": "file", "operation": "update", "authentication": "oAuth2",
                               "fileId": {"__rl": True, "mode": "id", "value": "={{ $('Cập nhật file · Webhook').first().json.body.fileId }}"},
                               "changeFileContent": True, "inputDataFieldName": "data", "updateFields": {}},
                "credentials": copy.deepcopy(DRIVE)}
    up_res = {"id": sid("node", "Cập nhật file · Kết quả"), "name": "Cập nhật file · Kết quả", "type": "n8n-nodes-base.code", "typeVersion": 2,
              "position": [660, y + 420],
              "parameters": {"jsCode": "const r = $json || {};\nreturn [{ json: { ok: !!r.id && !r.error, id: r.id || null, error: r.error ? String(r.error.message || r.error) : null } }];"}}
    mat_db = DB["materials"].replace("-", "")
    ar_hook = {"id": sid("node", "Gỡ tài liệu · Webhook"), "name": "Gỡ tài liệu · Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
               "position": [0, y + 600], "webhookId": sid("ingest", "material-archive"),
               "parameters": {"path": "copilot-material-archive", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
               "credentials": copy.deepcopy(APPKEY)}
    ar_get = {"id": sid("node", "Gỡ tài liệu · Đọc trang"), "name": "Gỡ tài liệu · Đọc trang", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
              "position": [220, y + 600], "credentials": copy.deepcopy(NOTION),
              "parameters": {"method": "GET", "url": "={{ 'https://api.notion.com/v1/pages/' + String($json.body.id || '').replace(/[^0-9a-f-]/g, '') }}",
                             "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
                             "options": {"response": {"response": {"neverError": True}}}}}
    ar_chk = {"id": sid("node", "Gỡ tài liệu · Kiểm tra"), "name": "Gỡ tài liệu · Kiểm tra", "type": "n8n-nodes-base.code", "typeVersion": 2,
              "position": [440, y + 600],
              "parameters": {"jsCode": "// chỉ gỡ trang thuộc 📚 Course Materials; trang khác -> từ chối\n"
                                       "const ok = String($json.parent?.database_id || '').replace(/-/g, '') === '" + mat_db + "' && !$json.archived;\n"
                                       "return [{ json: { id: $json.id, ok } }];"}}
    ar_do = {"id": sid("node", "Gỡ tài liệu · Bỏ vào thùng rác"), "name": "Gỡ tài liệu · Bỏ vào thùng rác", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
             "position": [660, y + 600], "credentials": copy.deepcopy(NOTION),
             "parameters": {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.id }}",
                            "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
                            "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": "={{ JSON.stringify($json.ok ? { archived: true } : {}) }}",
                            "options": {"response": {"response": {"neverError": True, "fullResponse": True}}}}}
    ar_res = {"id": sid("node", "Gỡ tài liệu · Kết quả"), "name": "Gỡ tài liệu · Kết quả", "type": "n8n-nodes-base.code", "typeVersion": 2,
              "position": [880, y + 600],
              "parameters": {"jsCode": "const k = $('Gỡ tài liệu · Kiểm tra').first().json;\nreturn [{ json: { ok: k.ok && $json.statusCode === 200, refused: !k.ok } }];"}}
    for ch in ([up_hook, up_dl, up_drive, up_res], [ar_hook, ar_get, ar_chk, ar_do, ar_res]):
        nodes += ch
        for a, b in zip(ch, ch[1:]):
            conns[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    nodes.append(sticky("ingest", "## 📥 Nhập file từ web app → Drive (Course Materials Backup) → University Inbox → A2\nPOST /webhook/copilot-file-ingest (cần X-Copilot-Key)\n"
                        "Chống trùng: /copilot-file-update ghi đè nội dung file Drive · /copilot-material-archive gỡ tài liệu bản cũ (chỉ trang Course Materials).", [-60, y], 1600, 780, 4))
    return nodes, conns, 820

# --------------------------------------------------------------------------- mục 9: Notion <-> phòng họp
COUNCIL_DB = cfg.notion("council_sessions")     # 🏛️ Council Sessions
RELAY = "http://host.docker.internal:8310"

N9_PICK_JS = r"""
// Mỗi dòng Council Sessions đang tick Convene -> 1 hành động. Hội đồng KHÔNG tự khởi động: chỉ chạy khi Chủ tọa tick.
const txt = p => p ? (p.rich_text || p.title || []).map(t => t.plain_text).join('') : '';
const out = [];
for (const r of ($json.results || [])) {
  const P = r.properties || {};
  const status = (P['Status'] && P['Status'].select && P['Status'].select.name) || 'Draft';
  const prompt = txt(P['Chair Prompt']).trim();
  const decision = txt(P['Final Decision']).trim();
  const title = txt(P['Session']).trim();
  const sources = ((P['Source Work'] || {}).relation || []).map(x => x.id);
  let key = txt(P['Session Key']).trim();
  if (!key) { const d = new Date(Date.now() + 7 * 3600e3).toISOString(); key = 'CS-' + d.slice(0, 10).replace(/-/g, '') + '-' + d.slice(11, 19).replace(/:/g, ''); }
  let action;
  if (status === 'In council' || status === 'Finalized') action = 'reset';          // đang họp / đã chốt: chỉ gỡ tick
  else if (status === 'Awaiting Chair') action = decision ? 'finalize' : 'continue';
  else action = (prompt || title || sources.length) ? 'start' : 'reset';            // Draft/Convened: mở phiên
  out.push({ json: { pageId: r.id, url: r.url, key, status, action, prompt, decision, title,
                     sourceId: action === 'start' ? (sources[0] || '') : '', sourceCount: sources.length } });
}
return out;
"""

N9_BUILD_JS = r"""
// Khoá snapshot hồ sơ (Source Work đầu tiên) + dựng lệnh cập nhật Notion và lệnh gửi phòng họp.
const a = $('N9 · Chọn hành động').item.json;
const src = $json || {};
const flat = v => {
  if (!v) return '';
  switch (v.type) {
    case 'title': case 'rich_text': return (v[v.type] || []).map(t => t.plain_text).join('');
    case 'select': case 'status': return v[v.type] ? v[v.type].name : '';
    case 'multi_select': return (v.multi_select || []).map(o => o.name).join(', ');
    case 'date': return v.date ? (v.date.start + (v.date.end ? ' → ' + v.date.end : '')) : '';
    case 'number': return v.number == null ? '' : String(v.number);
    case 'checkbox': return v.checkbox ? '✓' : '';
    case 'url': case 'email': case 'phone_number': return v[v.type] || '';
    case 'formula': return v.formula ? String(v.formula[v.formula.type] ?? '') : '';
    default: return '';
  }
};
let snapshot = '';
if (a.action === 'start') {
  if (a.sourceId && src.object === 'page') {
    const lines = Object.entries(src.properties || {}).map(([k, v]) => [k, flat(v)]).filter(([, v]) => v).map(([k, v]) => `• ${k}: ${v}`);
    snapshot = `Nguồn: ${src.url}\n` + lines.join('\n');
    if (a.sourceCount > 1) snapshot += `\n(+${a.sourceCount - 1} mục Source Work khác — xem trong Notion)`;
  } else snapshot = '(Phiên không gắn Source Work)';
  snapshot = `Snapshot khoá lúc ${new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 16).replace('T', ' ')}\n` + snapshot;
  snapshot = snapshot.slice(0, 1990);
}
const rt = s => ({ rich_text: [{ text: { content: s.slice(0, 1990) } }] });
const props = { 'Convene': { checkbox: false } };
let relay = null;
if (a.action === 'start') {
  Object.assign(props, { 'Status': { select: { name: 'In council' } }, 'Session Key': rt(a.key), 'Snapshot': rt(snapshot) });
  relay = { path: '/council/ask', body: { mode: 'start', session_key: a.key, page_id: a.pageId, channel: 'council', title: a.title,
    question: (a.title ? `Chủ đề: ${a.title}\n\n` : '') + `Yêu cầu của Chủ tọa: ${a.prompt || '(chưa ghi — bàn dựa trên hồ sơ)'}\n\n${snapshot}` } };
} else if (a.action === 'continue') {
  props['Status'] = { select: { name: 'In council' } };
  relay = { path: '/council/ask', body: { mode: 'continue', session_key: a.key, page_id: a.pageId, channel: 'council', title: a.title,
    question: a.prompt ? `Chủ tọa góp ý / yêu cầu: ${a.prompt}` : 'Chủ tọa yêu cầu bàn tiếp (không thêm góp ý mới).' } };
} else if (a.action === 'finalize') {
  props['Status'] = { select: { name: 'Finalized' } };
  relay = { path: '/council/note', body: { session_key: a.key, channel: 'council',
    text: `🏁 Chủ tọa đã CHỐT phiên ${a.key}${a.title ? ' · ' + a.title : ''}.\nQuyết định: ${a.decision}\nHội đồng kết thúc phiên này.` } };
}
return { json: { ...a, patchBody: { properties: props }, relay } };
"""

N9_TRANSCRIPT_JS = r"""
// Biên bản từ relay -> Transcript (chia khúc 1990 ký tự, tối đa 100 khúc) + Status Awaiting Chair. Hội đồng dừng hẳn.
const b = $('N9 · Nhận biên bản').first().json.body || {};
const found = ($json.results || [])[0];
const pageId = b.pageId || (found && found.id);
if (!pageId) throw new Error('Không tìm thấy Council Session cho key ' + b.sessionKey);
const t = String(b.transcript || '');
const chunks = [];
for (let i = 0; i < t.length && chunks.length < 100; i += 1990) chunks.push({ text: { content: t.slice(i, i + 1990) } });
return [{ json: { pageId, patchBody: { properties: {
  'Transcript': { rich_text: chunks },
  'Status': { select: { name: 'Awaiting Chair' } },
  'Convene': { checkbox: false } } } } }];
"""


def council_section(y):
    nodes, conns = [], {}

    def node(name, typ, pos, params, ver=None, **extra):
        n = {"id": sid("node", name), "name": name, "type": typ, "typeVersion": ver, "position": pos, "parameters": params}
        n.update(extra)
        nodes.append(n)
        return n

    def link(a, b, out=0):
        conns.setdefault(a, {"main": []})
        while len(conns[a]["main"]) <= out:
            conns[a]["main"].append([])
        conns[a]["main"][out].append({"node": b, "type": "main", "index": 0})

    notion_auth = {"authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi"}
    # --- Chủ tọa tick Convene -> xử lý
    node("N9 · Mỗi phút", "n8n-nodes-base.scheduleTrigger", [0, y + 200],
         {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}}, 1.2)
    node("N9 · Phiên tick Convene", "n8n-nodes-base.httpRequest", [220, y + 200],
         {"method": "POST", "url": f"https://api.notion.com/v1/databases/{COUNCIL_DB}/query", **notion_auth,
          "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
          "body": json.dumps({"page_size": 20, "filter": {"property": "Convene", "checkbox": {"equals": True}}}), "options": {}},
         4.2, credentials=copy.deepcopy(NOTION))
    node("N9 · Chọn hành động", "n8n-nodes-base.code", [440, y + 200], {"jsCode": N9_PICK_JS.strip()}, 2)
    node("N9 · Đọc hồ sơ nguồn", "n8n-nodes-base.httpRequest", [660, y + 200],
         {"method": "GET", "url": "={{ $json.sourceId ? 'https://api.notion.com/v1/pages/' + $json.sourceId : 'https://api.notion.com/v1/users/me' }}",
          **notion_auth, "options": {}}, 4.2, credentials=copy.deepcopy(NOTION), onError="continueRegularOutput", alwaysOutputData=True)
    node("N9 · Khoá snapshot + dựng lệnh", "n8n-nodes-base.code", [880, y + 200],
         {"jsCode": N9_BUILD_JS.strip(), "mode": "runOnceForEachItem"}, 2)
    node("N9 · Cập nhật phiên", "n8n-nodes-base.httpRequest", [1100, y + 200],
         {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.pageId }}", **notion_auth,
          "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
          "body": "={{ JSON.stringify($json.patchBody) }}", "options": {}}, 4.2, credentials=copy.deepcopy(NOTION))
    node("N9 · Có việc cho phòng họp?", "n8n-nodes-base.if", [1320, y + 200],
         {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                         "conditions": [{"id": sid("cond", "n9relay"), "leftValue": "={{ !!$('N9 · Khoá snapshot + dựng lệnh').item.json.relay }}",
                                         "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                         "combinator": "and"}, "options": {}}, 2.2)
    node("N9 · Gửi phòng họp", "n8n-nodes-base.httpRequest", [1540, y + 200],
         {"method": "POST", "url": "=" + RELAY + "{{ $('N9 · Khoá snapshot + dựng lệnh').item.json.relay.path }}",
          "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
          "body": "={{ JSON.stringify($('N9 · Khoá snapshot + dựng lệnh').item.json.relay.body) }}",
          "options": {"timeout": 120000}}, 4.2, onError="continueRegularOutput")
    for a, b in [("N9 · Mỗi phút", "N9 · Phiên tick Convene"), ("N9 · Phiên tick Convene", "N9 · Chọn hành động"),
                 ("N9 · Chọn hành động", "N9 · Đọc hồ sơ nguồn"), ("N9 · Đọc hồ sơ nguồn", "N9 · Khoá snapshot + dựng lệnh"),
                 ("N9 · Khoá snapshot + dựng lệnh", "N9 · Cập nhật phiên"), ("N9 · Cập nhật phiên", "N9 · Có việc cho phòng họp?")]:
        link(a, b)
    link("N9 · Có việc cho phòng họp?", "N9 · Gửi phòng họp", 0)

    # --- Relay báo hội đồng đã dừng -> Transcript + Awaiting Chair
    y2 = y + 460
    node("N9 · Nhận biên bản", "n8n-nodes-base.webhook", [0, y2],
         {"path": "council-transcript", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "onReceived", "options": {}},
         2, webhookId=sid("n9", "transcript"), credentials=copy.deepcopy(APPKEY))
    node("N9 · Tìm phiên theo key", "n8n-nodes-base.httpRequest", [220, y2],
         {"method": "POST", "url": f"https://api.notion.com/v1/databases/{COUNCIL_DB}/query", **notion_auth,
          "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
          "body": "={{ JSON.stringify({ page_size: 1, filter: { property: 'Session Key', rich_text: { equals: $json.body.sessionKey || '-' } } }) }}",
          "options": {}}, 4.2, credentials=copy.deepcopy(NOTION))
    node("N9 · Dựng biên bản", "n8n-nodes-base.code", [440, y2], {"jsCode": N9_TRANSCRIPT_JS.strip()}, 2)
    node("N9 · Ghi biên bản + Awaiting Chair", "n8n-nodes-base.httpRequest", [660, y2],
         {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.pageId }}", **notion_auth,
          "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
          "body": "={{ JSON.stringify($json.patchBody) }}", "options": {}}, 4.2, credentials=copy.deepcopy(NOTION))
    for a, b in [("N9 · Nhận biên bản", "N9 · Tìm phiên theo key"), ("N9 · Tìm phiên theo key", "N9 · Dựng biên bản"),
                 ("N9 · Dựng biên bản", "N9 · Ghi biên bản + Awaiting Chair")]:
        link(a, b)
    nodes.append(sticky("n9", "## 🏛️ Mục 9 · Hội đồng AI ↔ Notion (bản vẽ)\n"
                        "Chủ tọa tick **Convene** trong 🏛️ Council Sessions → khoá snapshot Source Work → relay xáo ghế, gửi #council\n"
                        "→ ghế cuối tổng hợp → relay gửi biên bản → **Awaiting Chair**. Chủ tọa: góp ý vào *Chair Prompt* + tick Convene = vòng mới;"
                        " ghi *Final Decision* + tick Convene = **Finalized**. Hội đồng không tự khởi động.",
                        [-60, y], 1800, 700, 6))
    return nodes, conns, 740


# --------------------------------------------------------------------------- tab Ghi bài giảng (Copilot)
SESSIONS_DB = cfg.notion("lecture_sessions")     # 🎙️ Lecture Sessions

LECTURE_LIST_JS = r"""
const txt = (P, n) => ((P[n] && (P[n].rich_text || P[n].title)) || []).map(t => t.plain_text).join('');
const out = ($json.results || []).map(p => { const P = p.properties || {};
  return { pageId: p.id, url: p.url, title: txt(P, 'Session'), captureId: txt(P, 'Capture ID'),
    state: (P.State && P.State.select && P.State.select.name) || '', notes: txt(P, 'Processing Notes'),
    noteUrl: (P['Processed Note'] && P['Processed Note'].url) || '', startedAt: (P['Started At'] && P['Started At'].date && P['Started At'].date.start) || '',
    endedAt: (P['Ended At'] && P['Ended At'].date && P['Ended At'].date.start) || '', created: p.created_time }; });
return [{ json: { sessions: out } }];
"""


def lecture_section(y):
    nodes, conns = [], {}
    hook = {"id": sid("node", "Bài giảng · Danh sách"), "name": "Bài giảng · Danh sách", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [0, y + 200], "webhookId": sid("lecture", "list"),
            "parameters": {"path": "copilot-lectures", "httpMethod": "GET", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
            "credentials": copy.deepcopy(APPKEY)}
    q = notion_http("Bài giảng · Đọc Lecture Sessions", [220, y + 200], f"https://api.notion.com/v1/databases/{SESSIONS_DB}/query",
                    json.dumps({"page_size": 15, "sorts": [{"timestamp": "created_time", "direction": "descending"}]}))
    m = {"id": sid("node", "Bài giảng · Gọn danh sách"), "name": "Bài giảng · Gọn danh sách", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [440, y + 200], "parameters": {"jsCode": LECTURE_LIST_JS.strip()}}
    hook2 = {"id": sid("node", "Bài giảng · Phân tích lại"), "name": "Bài giảng · Phân tích lại", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, y + 420], "webhookId": sid("lecture", "reanalyze"),
             "parameters": {"path": "copilot-lecture-reanalyze", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
             "credentials": copy.deepcopy(APPKEY)}
    p = notion_http("Bài giảng · Xếp hàng phân tích lại", [220, y + 420], "={{ 'https://api.notion.com/v1/pages/' + $json.body.pageId }}",
                    "={{ JSON.stringify({ properties: { State: { select: { name: 'Uploaded' } }, 'Analysis Key': { rich_text: [] },"
                    " 'Processing Notes': { rich_text: [{ text: { content: 'Phân tích lại theo yêu cầu từ Copilot lúc ' + $now.setZone('Asia/Ho_Chi_Minh').toFormat('dd/MM HH:mm') + ' (lần thử 1).' } }] } } }) }}",
                    method="PATCH")
    r = {"id": sid("node", "Bài giảng · Kết quả phân tích lại"), "name": "Bài giảng · Kết quả phân tích lại", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [440, y + 420], "parameters": {"jsCode": "return [{ json: { ok: !!$json.id, state: (($json.properties || {}).State || {}).select } }];"}}
    nodes += [hook, q, m, hook2, p, r]
    conns[hook["name"]] = {"main": [[{"node": q["name"], "type": "main", "index": 0}]]}
    conns[q["name"]] = {"main": [[{"node": m["name"], "type": "main", "index": 0}]]}
    conns[hook2["name"]] = {"main": [[{"node": p["name"], "type": "main", "index": 0}]]}
    conns[p["name"]] = {"main": [[{"node": r["name"], "type": "main", "index": 0}]]}
    nodes.append(sticky("lecture", "## 🎙️ Tab Ghi bài giảng (Copilot)\nGET /webhook/copilot-lectures · POST /webhook/copilot-lecture-reanalyze (cần X-Copilot-Key).\n"
                        "Ghi âm do app trên máy làm (chỉ khi bấm Start/Stop trong Copilot); phân tích ở workflow Lecture Analysis v2.", [-60, y], 1000, 640, 5))
    return nodes, conns, 680


# --------------------------------------------------------------------------- tab Lịch + Học kỳ (Claude 2026-10-03)
TIMETABLE_JS = r"""
const pt = (p) => { if (!p) return ''; const v = p[p.type]; if (Array.isArray(v)) return v.map(x => x.plain_text || '').join('');
  if (v && typeof v === 'object') return v.name || v.start || ''; return v ?? ''; };
const from = $('Lịch · Webhook').first().json.query.from;
const rows = [...($('Lịch · Trong khoảng').first().json.results || []), ...($('Lịch · Sự kiện dài').first().json.results || [])];
const seen = new Set(); const out = [];
for (const r of rows) {
  if (seen.has(r.id)) continue; seen.add(r.id);
  const p = r.properties || {}; const w = p.When?.date || {};
  if (!w.start) continue;
  // Notion lọc ngày theo UTC -> đã lấy rộng thêm 1 ngày mỗi đầu; lọc lại theo ngày giờ Việt Nam (chuỗi đã mang +07:00)
  const to = $('Lịch · Webhook').first().json.query.to;
  if ((w.end || w.start).slice(0, 10) < from) continue;
  if (w.start.slice(0, 10) > to) continue;
  out.push({ id: r.id, title: pt(p.Event), kind: p.Kind?.select?.name || '', start: w.start, end: w.end || null,
             location: pt(p.Location), notes: pt(p.Notes), url: r.url });
}
out.sort((a, b) => a.start.localeCompare(b.start));
return [{ json: { from, to: $('Lịch · Webhook').first().json.query.to, events: out } }];
"""

SEMESTER_PICK_JS = r"""
const rows = $json.results || [];
const cur = rows.find(r => (r.properties?.State?.title || []).map(t => t.plain_text).join('') === 'Current') || rows[0] || {};
const p = cur.properties || {};
const no = p['Semester No.']?.select?.name || '1';
const period = p.Period?.select?.name || 'Semester';
const notes = (p.Notes?.rich_text || []).map(t => t.plain_text).join('');
return [{ json: { sem: /^\d$/.test(no) ? 'S' + no : 'S1', period, no, notes, updatedBy: (p['Updated By']?.rich_text || []).map(t => t.plain_text).join('') } }];
"""

SEMESTER_JS = r"""
const pt = (p) => { if (!p) return null; const v = p[p.type]; if (Array.isArray(v)) return p.type === 'relation' ? v.map(x => x.id) : v.map(x => x.plain_text || '').join('');
  if (p.type === 'formula') return v[v.type]; if (v && typeof v === 'object') return v.name ?? v.start ?? null; return v ?? null; };
const pick = $('Học kỳ · Kỳ hiện tại').first().json;
const courses = ($('Học kỳ · Môn').first().json.results || []).map(r => { const p = r.properties; return {
  id: r.id, url: r.url, code: pt(p.Code), name: pt(p.Name), credits: pt(p.Credits) || 0, category: pt(p.Category), status: pt(p.Status),
  result: pt(p.Result), retake: !!pt(p.Retake), gpa4: pt(p['Current GPA 4']), risk: pt(p['Attendance Risk']), module: pt(p['Module/Track']),
  notes: pt(p['Course Notes']), original: pt(p['Original Semester']),
  rule: pt(p['Luật môn']), wqt: pt(p['Trọng số QT (%)']), maxAbs: pt(p['Vắng tối đa']) }; });
const tracker = ($('Học kỳ · Tín chỉ').first().json.results || []).map(r => { const p = r.properties; return {
  semester: pt(p.Semester), order: pt(p.Order), planned: pt(p['Planned Credits']), done: pt(p['Completed Credits']), required: pt(p['Required Credits']),
  common: pt(p['Tín chỉ chung']), modules: pt(p['Tín chỉ Module']), check: pt(p['Đối soát']) }; }).sort((a, b) => (a.order || 0) - (b.order || 0));
const grades = ($('Học kỳ · Điểm').first().json.results || []).map(r => { const p = r.properties; return {
  course: (pt(p.Course) || [])[0] || null, component: pt(p.Component), score: pt(p['Score 10']), weight: pt(p['Weight %']),
  letter: pt(p['Letter Grade']), gpa4: pt(p['GPA 4']), notes: pt(p.Notes) }; });
const absences = {};
for (const r of ($('Học kỳ · Chuyên cần').first().json.results || [])) { const p = r.properties; const st = pt(p.Status); const c = (pt(p.Course) || [])[0];
  if (!c) continue; absences[c] = absences[c] || { absent: 0, late: 0, excused: 0 };
  if (st === 'Absent') absences[c].absent++; else if (st === 'Late') absences[c].late++; else if (st === 'Excused') absences[c].excused++; }
return [{ json: { ...pick, courses, tracker, grades, absences } }];
"""


def academic_section(y):
    """GET /webhook/copilot-timetable?from=YYYY-MM-DD&to=YYYY-MM-DD và GET /webhook/copilot-semester cho 2 tab mới của web app."""
    def hook(name, path, pos):
        return {"id": sid("node", name), "name": name, "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": pos,
                "webhookId": sid("academic", path),
                "parameters": {"path": path, "httpMethod": "GET", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
                "credentials": copy.deepcopy(APPKEY)}
    def code(name, pos, js):
        return {"id": sid("node", name), "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
                "parameters": {"jsCode": js.strip()}}
    q = lambda db: f"https://api.notion.com/v1/databases/{db}/query"
    wk = "$('Lịch · Webhook').first().json.query"
    t = [hook("Lịch · Webhook", "copilot-timetable", [0, y + 200]),
         notion_http("Lịch · Trong khoảng", [220, y + 200], q(DB["events"]),
                     "={{ JSON.stringify({page_size:100, sorts:[{property:'When',direction:'ascending'}], filter:{and:[{property:'When',date:{on_or_after:DateTime.fromISO(" + wk + ".from).minus({days:1}).toISODate()}},{property:'When',date:{on_or_before:DateTime.fromISO(" + wk + ".to).plus({days:1}).toISODate()}}]}}) }}"),
         # sự kiện kéo dài nhiều ngày (vd đợt QP-AN) bắt đầu trước tuần đang xem
         notion_http("Lịch · Sự kiện dài", [440, y + 200], q(DB["events"]),
                     "={{ JSON.stringify({page_size:50, filter:{and:[{property:'When',date:{before:" + wk + ".from}},{property:'When',date:{on_or_after:$now.minus({days:60}).toISODate()}},{property:'Event',title:{does_not_contain:'·'}}]}}) }}"),
         code("Lịch · Gọn", [660, y + 200], TIMETABLE_JS)]
    s = [hook("Học kỳ · Webhook", "copilot-semester", [0, y + 420]),
         notion_http("Học kỳ · Trạng thái", [220, y + 420], q(STATE_DB), json.dumps({"page_size": 10})),
         code("Học kỳ · Kỳ hiện tại", [440, y + 420], SEMESTER_PICK_JS),
         notion_http("Học kỳ · Môn", [660, y + 420], q(DB["courses"]),
                     "={{ JSON.stringify({page_size:100, filter:{property:'Semester', select:{equals:$json.sem}}}) }}"),
         notion_http("Học kỳ · Tín chỉ", [880, y + 420], q(TRACKER_DB), json.dumps({"page_size": 20})),
         notion_http("Học kỳ · Điểm", [1100, y + 420], q(GRADES_DB),
                     "={{ JSON.stringify({page_size:100, filter:{property:'Semester', select:{equals:$('Học kỳ · Kỳ hiện tại').first().json.sem}}}) }}"),
         notion_http("Học kỳ · Chuyên cần", [1320, y + 420], q(ATTEND_DB), json.dumps({"page_size": 100})),
         code("Học kỳ · Gom", [1540, y + 420], SEMESTER_JS)]
    nodes, conns = t + s, {}
    for chain in (t, s):
        for a, b in zip(chain, chain[1:]):
            conns[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    # Cổng Notion cho logic học tập trong web app (copilot_app.py /api/academic): chỉ các bảng học tập, không xoá.
    allowed = [DB["courses"], DB["events"], DB["materials"], STATE_DB, TRACKER_DB, GRADES_DB, ATTEND_DB, CONDUCT_DB, RESEARCH_DB, NOTEBOOK_DB, DB["tasks"], DB["eq"], SUMMER_DB, RESULTS_DB, INBOX_DB, WORK_DB, REVISION_DB, GRAD_DB, MILESTONES_DB, BACKUP_DB, DB["daily"], WEEKLY_DB, CONTROL_DB, MODES_DB, ATTEMPTS_DB, SCHOOL_LOG_DB, EVENTS_TRACK_DB, EXTRA_DB] + CERT_DBS
    guard_js = ("const ALLOW = " + json.dumps([a.replace("-", "") for a in allowed]) + ";\n"
                "const ops = ($json.body && $json.body.ops) || [];\n"
                "if (!Array.isArray(ops) || ops.length > 60) throw new Error('ops không hợp lệ');\n"
                "return ops.map(o => {\n"
                "  const url = String(o.url || ''); const body = o.body || {}; const flat = url.replace(/-/g, '');\n"
                "  if (!url.startsWith('https://api.notion.com/v1/')) throw new Error('chỉ Notion API');\n"
                "  if (body.archived !== undefined || body.in_trash !== undefined) throw new Error('cổng này không xoá dữ liệu');\n"
                "  const qm = flat.match(/databases\\/([0-9a-f]{32})\\/query$/);\n"
                "  if (o.method === 'POST' && qm) { if (!ALLOW.includes(qm[1])) throw new Error('bảng không được phép'); }\n"
                "  else if (o.method === 'POST' && /\\/v1\\/pages$/.test(url)) { const p = String(body.parent?.database_id || '').replace(/-/g, ''); if (!ALLOW.includes(p)) throw new Error('bảng không được phép'); }\n"
                "  else if (o.method === 'PATCH' && /\\/v1\\/pages\\/[0-9a-f-]{32,36}$/.test(url)) {}\n"
                "  else throw new Error('thao tác không được phép: ' + o.method + ' ' + url);\n"
                "  return { json: { method: o.method, url, body: JSON.stringify(body) } };\n"
                "});")
    g = [{"id": sid("node", "Cổng Notion · Webhook"), "name": "Cổng Notion · Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
          "position": [0, y + 640], "webhookId": sid("academic", "copilot-notion"),
          "parameters": {"path": "copilot-notion", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
          "credentials": copy.deepcopy(APPKEY)},
         code("Cổng Notion · Kiểm tra", [220, y + 640], guard_js),
         {"id": sid("node", "Cổng Notion · Gọi"), "name": "Cổng Notion · Gọi", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [440, y + 640],
          "parameters": {"method": "={{ $json.method }}", "url": "={{ $json.url }}", "authentication": "predefinedCredentialType",
                         "nodeCredentialType": "notionApi", "sendBody": True, "contentType": "raw",
                         "rawContentType": "application/json", "body": "={{ $json.body }}",
                         "options": {"batching": {"batch": {"batchSize": 3, "batchInterval": 1000}},
                                     "response": {"response": {"neverError": True, "fullResponse": True}}}},
          "credentials": copy.deepcopy(NOTION)},
         code("Cổng Notion · Kết quả", [660, y + 640], "return [{ json: { res: $input.all().map(i => ({ code: i.json.statusCode, body: i.json.body })) } }];")]
    nodes += g
    for a, b in zip(g, g[1:]):
        conns[a["name"]] = {"main": [[{"node": b["name"], "type": "main", "index": 0}]]}
    # Cổng thùng rác cho nạp TKB (tkb.py): chỉ nhận trang thuộc Academic Timetable có Kind=Class; lệch 1 trang -> không bỏ trang nào.
    ev_db = DB["events"].replace("-", "")
    a = [{"id": sid("node", "Thùng rác TKB · Webhook"), "name": "Thùng rác TKB · Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
          "position": [0, y + 1160], "webhookId": sid("academic", "copilot-tkb-archive"),
          "parameters": {"path": "copilot-tkb-archive", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
          "credentials": copy.deepcopy(APPKEY)},
         code("Thùng rác TKB · Danh sách", [220, y + 1160],
              "const ids = ($json.body && $json.body.ids) || [];\n"
              "if (!Array.isArray(ids) || !ids.length || ids.length > 400) throw new Error('ids không hợp lệ');\n"
              "return ids.map(i => { const id = String(i); if (!/^[0-9a-f-]{32,36}$/.test(id)) throw new Error('id lạ'); return { json: { id } }; });"),
         {"id": sid("node", "Thùng rác TKB · Đọc trang"), "name": "Thùng rác TKB · Đọc trang", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [440, y + 1160],
          "parameters": {"method": "GET", "url": "=https://api.notion.com/v1/pages/{{ $json.id }}",
                         "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
                         "options": {"batching": {"batch": {"batchSize": 3, "batchInterval": 1000}},
                                     "response": {"response": {"neverError": True}}}},
          "credentials": copy.deepcopy(NOTION)},
         code("Thùng rác TKB · Kiểm tra", [660, y + 1160],
              "const ids = $('Thùng rác TKB · Danh sách').all().map(i => i.json.id);\n"
              "const pages = $input.all().map(i => i.json);\n"
              "const bad = pages.map((p, k) => ({ p, id: ids[k] })).filter(({ p }) => !(String(p.parent?.database_id || '').replace(/-/g, '') === '" + ev_db + "' && p.properties?.Kind?.select?.name === 'Class' && !p.archived)).map(x => x.id);\n"
              "return ids.map(id => ({ json: { id, ok: bad.length === 0, bad } }));"),
         {"id": sid("node", "Thùng rác TKB · Bỏ"), "name": "Thùng rác TKB · Bỏ", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [880, y + 1160],
          "parameters": {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.id }}",
                         "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
                         "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": "={{ JSON.stringify($json.ok ? { archived: true } : {}) }}",
                         "options": {"batching": {"batch": {"batchSize": 3, "batchInterval": 1000}},
                                     "response": {"response": {"neverError": True, "fullResponse": True}}}},
          "credentials": copy.deepcopy(NOTION)},
         code("Thùng rác TKB · Kết quả", [1100, y + 1160],
              "const k = $('Thùng rác TKB · Kiểm tra').first().json;\n"
              "return [{ json: k.ok ? { da_bo: $input.all().filter(i => i.json.statusCode === 200).length } : { da_bo: 0, bo_qua: k.bad } }];")]
    nodes += a
    for x, z in zip(a, a[1:]):
        conns[x["name"]] = {"main": [[{"node": z["name"], "type": "main", "index": 0}]]}
    # 📱 Trang điện thoại (04/10): thay TOÀN BỘ nội dung của ĐÚNG MỘT trang (PHONE_PAGE) — không nhận id trang khác, không đụng trang khác.
    pg = PHONE_PAGE
    def nh(name, pos, method, url, body=None, batch=(3, 1000)):
        p = {"method": method, "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
             "options": {"batching": {"batch": {"batchSize": batch[0], "batchInterval": batch[1]}}, "response": {"response": {"neverError": True, "fullResponse": True}}}}
        if body: p.update({"sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": body})
        return {"id": sid("node", name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos, "parameters": p,
                "credentials": copy.deepcopy(NOTION)}
    ph = [{"id": sid("node", "Trang điện thoại · Webhook"), "name": "Trang điện thoại · Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
           "position": [0, y + 1290], "webhookId": sid("academic", "copilot-phone-page"),
           "parameters": {"path": "copilot-phone-page", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
           "credentials": copy.deepcopy(APPKEY)},
          code("Trang điện thoại · Kiểm tra", [220, y + 1290],
               "const b = ($json.body && $json.body.blocks) || [];\n"
               "if (!Array.isArray(b) || !b.length || b.length > 300) throw new Error('blocks không hợp lệ');\n"
               "return [{ json: { n: b.length } }];"),
          nh("Trang điện thoại · Đọc khối cũ", [440, y + 1290], "GET", f"https://api.notion.com/v1/blocks/{pg}/children?page_size=100"),
          code("Trang điện thoại · Danh sách xoá", [660, y + 1290],
               "const r = ($json.body && $json.body.results) || [];\n"
               "return r.length ? r.map(x => ({ json: { id: x.id } })) : [{ json: { skip: true } }];"),
          nh("Trang điện thoại · Xoá khối cũ", [880, y + 1290], "={{ $json.skip ? 'GET' : 'DELETE' }}",
             f"={{{{ $json.skip ? 'https://api.notion.com/v1/blocks/{pg}' : 'https://api.notion.com/v1/blocks/' + $json.id }}}}"),
          code("Trang điện thoại · Chia khối", [1100, y + 1290],
               "const b = $('Trang điện thoại · Webhook').first().json.body.blocks; const out = [];\n"
               "for (let i = 0; i < b.length; i += 40) out.push({ json: { body: JSON.stringify({ children: b.slice(i, i + 40) }) } });\n"
               "return out;"),
          nh("Trang điện thoại · Ghi khối mới", [1320, y + 1290], "PATCH", f"https://api.notion.com/v1/blocks/{pg}/children", "={{ $json.body }}", batch=(1, 350)),
          code("Trang điện thoại · Kết quả", [1540, y + 1290],
               "const r = $input.all().map(i => i.json.statusCode);\n"
               "return [{ json: { ok: r.every(c => c === 200), codes: r, msg: $input.all().map(i => i.json.body && i.json.body.message).filter(Boolean).slice(0, 3) } }];")]
    nodes += ph
    for x, z in zip(ph, ph[1:]):
        conns[x["name"]] = {"main": [[{"node": z["name"], "type": "main", "index": 0}]]}
    # Research Hub (thay Research Agent ChatGPT): app chọn việc, tìm bằng SearXNG, kiểm link; n8n gọi Gemini (không tools) chọn kết quả.
    APP = "http://host.docker.internal:8320"
    def app_http(name, pos, path, body):
        return {"id": sid("node", name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
                "parameters": {"method": "POST", "url": APP + path, "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                               "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": body,
                               "options": {"timeout": 300000}},
                "credentials": copy.deepcopy(APPKEY)}
    r = [{"id": sid("node", "Nghiên cứu · 15 phút"), "name": "Nghiên cứu · 15 phút", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
          "position": [0, y + 1400], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 7/15 * * * *"}]}}},
         {"id": sid("node", "Nghiên cứu · Chạy ngay"), "name": "Nghiên cứu · Chạy ngay", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
          "position": [0, y + 1560], "webhookId": sid("academic", "copilot-run-research"),
          "parameters": {"path": "copilot-run-research", "httpMethod": "GET", "authentication": "headerAuth", "responseMode": "onReceived", "options": {}},
          "credentials": copy.deepcopy(APPKEY)},
         app_http("Nghiên cứu · Lấy việc", [240, y + 1480], "/api/research-next", "{}"),
         {"id": sid("node", "Nghiên cứu · Có việc?"), "name": "Nghiên cứu · Có việc?", "type": "n8n-nodes-base.if", "typeVersion": 2,
          "position": [460, y + 1480],
          "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                        "conditions": [{"leftValue": "={{ !!$json.job }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true"}}],
                                        "combinator": "and"}, "looseTypeValidation": True, "options": {}}},
         {"id": sid("node", "Nghiên cứu · Gemini chọn kết quả"), "name": "Nghiên cứu · Gemini chọn kết quả", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [680, y + 1460],
          "parameters": {"method": "POST", "url": GEMINI_GATE + "/v1beta/models/gemini-3.5-flash-lite:generateContent?caller=research",
                         "authentication": "predefinedCredentialType", "nodeCredentialType": "googlePalmApi",
                         "sendBody": True, "contentType": "raw", "rawContentType": "application/json", "body": "={{ JSON.stringify($json.body) }}",
                         "options": {"timeout": 240000, "response": {"response": {"neverError": True, "fullResponse": True}}}},
          "credentials": {"googlePalmApi": cfg.n8n_cred("googlePalmApi", "Google Gemini(PaLM) Api account")}},
         app_http("Nghiên cứu · Lưu", [900, y + 1460], "/api/research-save",
                  "={{ JSON.stringify({job: $('Nghiên cứu · Lấy việc').first().json.job, status: $json.statusCode, resp: $json.body}) }}")]
    nodes += r
    for t in r[:2]:
        conns[t["name"]] = {"main": [[{"node": "Nghiên cứu · Lấy việc", "type": "main", "index": 0}]]}
    conns["Nghiên cứu · Lấy việc"] = {"main": [[{"node": "Nghiên cứu · Có việc?", "type": "main", "index": 0}]]}
    conns["Nghiên cứu · Có việc?"] = {"main": [[{"node": "Nghiên cứu · Gemini chọn kết quả", "type": "main", "index": 0}], []]}
    conns["Nghiên cứu · Gemini chọn kết quả"] = {"main": [[{"node": "Nghiên cứu · Lưu", "type": "main", "index": 0}]]}
    # 📅 Weekly Reviews (Claude 2026-10-03): Chủ nhật 21:00 đánh giá cả tuần -> web app weekly.py ghi 1 dòng
    wk = [{"id": sid("node", "Đánh giá tuần · CN 21:00"), "name": "Đánh giá tuần · CN 21:00", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
           "position": [0, y + 1760], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 0 21 * * 0"}]}}},
          app_http("Đánh giá tuần · Chạy", [240, y + 1760], "/api/weekly", '{"save": true}')]
    nodes += wk
    conns[wk[0]["name"]] = {"main": [[{"node": wk[1]["name"], "type": "main", "index": 0}]]}
    # Bộ chuyển kỳ (thay tác vụ hằng ngày của ChatGPT): logic ở semester.py trong web app; n8n chỉ hẹn giờ.
    k = [{"id": sid("node", "Chuyển kỳ · 00:15"), "name": "Chuyển kỳ · 00:15", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
          "position": [0, y + 820], "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 15 0 * * *"}]}}},
         {"id": sid("node", "Chuyển kỳ · Chạy tay"), "name": "Chuyển kỳ · Chạy tay", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
          "position": [0, y + 980], "webhookId": sid("academic", "copilot-run-hk"),
          "parameters": {"path": "copilot-run-hk", "httpMethod": "GET", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
          "credentials": copy.deepcopy(APPKEY)},
         {"id": sid("node", "Chuyển kỳ · Chạy"), "name": "Chuyển kỳ · Chạy", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
          "position": [260, y + 900],
          "parameters": {"method": "POST", "url": "http://host.docker.internal:8320/api/semester-tick",
                         "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                         "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
                         "body": "={{ JSON.stringify({dry: ($json.query && $json.query.dry) || false, today: ($json.query && $json.query.today) || ''}) }}",
                         "options": {"timeout": 300000}},
          "credentials": copy.deepcopy(APPKEY)}]
    nodes += k
    for t in k[:2]:
        conns[t["name"]] = {"main": [[{"node": "Chuyển kỳ · Chạy", "type": "main", "index": 0}]]}
    nodes.append(sticky("academic", "## 🗓️ Tab Lịch + 🎓 Tab Học kỳ + 🔐 Cổng Notion (Copilot)\nGET /webhook/copilot-timetable?from=&to= · GET /webhook/copilot-semester · POST /webhook/copilot-notion (đều cần X-Copilot-Key).\n"
                        "Cổng Notion: logic điểm/luật môn/chuyên cần chạy bằng Python trong web app; ở đây chỉ cho phép các bảng học tập, không xoá.\n"
                        "⏭️ Chuyển kỳ 00:15 hằng ngày → web app /api/semester-tick (semester.py): đổi kỳ theo semester_calendar.json, chốt môn, học lại, task Tết, hỏi hè/Module qua Exception Queue, tính lại tín chỉ. Chạy tay: GET /webhook/copilot-run-hk?dry=1\n🔍 Nghiên cứu mỗi 15 phút (+ chạy ngay khi Copilot nhận yêu cầu): research.py chọn việc + tìm bằng SearXNG (Docker :8888) → Gemini Flash-Lite chọn và chú thích (cổng :8350, hết quota → LM Studio) → kiểm link → Research Results + University Inbox (A2).", [-60, y], 1800, 1880, 4))
    return nodes, conns, 1920


# --------------------------------------------------------------------------- patches
GEMINI_GATE = "http://host.docker.internal:8350"


def patch_gemini_gate(nodes):
    """Mọi node HTTP gọi Gemini đi qua cổng Gemini trên máy (đếm quota, ưu tiên, dự phòng LM Studio).
    Key vẫn do credential n8n gắn vào từng lời gọi; cổng không lưu key. Nhãn đường vào theo tiền tố section."""
    callers = {"A1": "a1", "A3": "a3", "H10": "health"}
    for n in nodes:
        url = n["parameters"].get("url") if n["type"] == "n8n-nodes-base.httpRequest" else None
        if isinstance(url, str) and "generativelanguage.googleapis.com" in url:
            caller = callers.get(n["name"].split(" ·")[0], "unknown")
            u = url.replace("https://generativelanguage.googleapis.com", GEMINI_GATE)
            n["parameters"]["url"] = u + ("&" if "?" in u else "?") + "caller=" + caller


def patch_a2_claim(nodes, conns):
    """(Claude 2026-10-03) Nhiều lượt A2 chạy cùng lúc (lịch 15 phút + kích ngay) từng giành cùng một dòng Inbox
    -> tạo Course Material trùng. Giờ: khoá kèm mã lượt chạy -> chờ 4 s -> đọc lại -> chỉ lượt có mã trên dòng mới chạy tiếp."""
    lock = next(n for n in nodes if n["name"] == "A2 · Lock Inbox")
    old = '"content":"Agent 2 triage started."'
    assert old in lock["parameters"]["body"], "A2 lock body changed"
    lock["parameters"]["body"] = lock["parameters"]["body"].replace(old, '"content":"Agent 2 triage started · {{ $execution.id }}"')
    x, y = lock["position"]
    wait = {"id": sid("node", "A2 · Chờ giành quyền"), "name": "A2 · Chờ giành quyền", "type": "n8n-nodes-base.wait", "typeVersion": 1.1,
            "position": [x + 60, y + 160], "webhookId": sid("a2", "claim-wait"), "parameters": {"amount": 4, "unit": "seconds"}}
    read = {"id": sid("node", "A2 · Đọc lại khoá"), "name": "A2 · Đọc lại khoá", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [x + 260, y + 160], "credentials": copy.deepcopy(NOTION),
            "parameters": {"method": "GET", "url": "=https://api.notion.com/v1/pages/{{ $('A2 · Normalize Inbox').item.json.inboxId }}",
                           "authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi", "options": {}}}
    won = {"id": sid("node", "A2 · Giành được?"), "name": "A2 · Giành được?", "type": "n8n-nodes-base.code", "typeVersion": 2,
           "position": [x + 460, y + 160], "parameters": {"jsCode": (
               "const notes = (($json.properties || {})['Triage Notes']?.rich_text || []).map(t => t.plain_text || '').join('');\n"
               "// lượt khác đã ghi mã của nó lên dòng này -> dừng, để lượt đó xử lý\n"
               "return notes.includes('· ' + $execution.id) ? [{ json: $json }] : [];")}}
    nodes += [wait, read, won]
    # (Claude 2026-10-03) File thả vào thư mục môn ở Uni-Documents mang sẵn "Môn: <mã> …" trong Context (môn do BẠN chọn qua thư mục).
    # A2 tin môn đó thay vì đoán theo nội dung (nội dung hay nhắc nhiều môn -> "multiple exact course signals");
    # file không đọc được nội dung nhưng đã có môn -> vẫn ghi vào kho dạng bản ghi theo metadata.
    psc = next(n for n in nodes if n["name"] == "A2 · Prepare Search Context")
    js = psc["parameters"]["jsCode"]
    anchor = "ctx.searchText="
    assert anchor in js, "A2 Prepare Search Context changed"
    psc["parameters"]["jsCode"] = js.replace(anchor,
        r"const dm = String(ctx.context || '').match(/Môn: ([A-Z]{2,4}\d{4})/);" + "\n"
        "if (dm) { ctx.declaredCode = dm[1]; if (ctx.fileReadable === false) { ctx.fileReadable = true; ctx.metadataOnly = true; delete ctx.reviewReason; } }\n" + anchor, 1)
    mec = next(n for n in nodes if n["name"] == "A2 · Match Exact Course")
    js = mec["parameters"]["jsCode"]
    anchor = "const matches = courses.filter(c => {"
    assert anchor in js, "A2 Match Exact Course changed"
    mec["parameters"]["jsCode"] = js.replace(anchor,
        "const declared = inbox.declaredCode ? courses.filter(c => c.code === inbox.declaredCode) : [];\n"
        "const matches = declared.length === 1 ? declared : courses.filter(c => {", 1)
    # bước đọc file ra 0 dòng (vd file đuôi .xlsx nhưng thật ra là ảnh) -> A2 từng dừng im lặng, dòng kẹt "In progress".
    # Cho đi tiếp: "Attach Extracted Content" thấy rỗng -> Needs review — không đọc được nội dung.
    for n in nodes:
        if n["name"].startswith("A2 · Extract") and n["name"] != "A2 · Extract Route":
            n["alwaysOutputData"] = True
    nxt = conns["A2 · Lock Inbox"]
    conns["A2 · Lock Inbox"] = {"main": [[{"node": wait["name"], "type": "main", "index": 0}]]}
    conns[wait["name"]] = {"main": [[{"node": read["name"], "type": "main", "index": 0}]]}
    conns[read["name"]] = {"main": [[{"node": won["name"], "type": "main", "index": 0}]]}
    conns[won["name"]] = nxt


def patch_a4_rest(nodes):
    """(Claude 2026-10-03) 💤 Rest Mode (đồng bộ từ 🌗 Chế độ ngày qua 🎛️ University Control): ngày nghỉ không xếp việc mới,
    chỉ giữ việc có hạn đúng hôm nay; không ghi OVERLOADED."""
    n = next(x for x in nodes if x["name"] == "A4 · Build Dynamic Daily Plan")
    js = n["parameters"]["jsCode"]
    pairs = [("const campOn=ctrlProps['Camp Mode']?.checkbox===true;",
              "const campOn=ctrlProps['Camp Mode']?.checkbox===true;\nconst restOn=ctrlProps['Rest Mode']?.checkbox===true;"),
             ("const sustainableCeiling=campOn?campHours:(weekday?4.5:6);", "const sustainableCeiling=restOn?0:(campOn?campHours:(weekday?4.5:6));"),
             ("const safetyCap=campOn?campHours+1:(weekday?6:7);", "const safetyCap=restOn?0:(campOn?campHours+1:(weekday?6:7));"),
             ("const target=Math.min(availableHours,demandTarget);", "const target=restOn?mandatoryHours:Math.min(availableHours,demandTarget);"),
             ("const overloaded=mandatoryHours>availableHours+0.01;", "const overloaded=!restOn&&mandatoryHours>availableHours+0.01;"),
             ("const reason=sliceNote+", "const reason=(restOn?'💤 REST DAY — chỉ giữ việc có hạn hôm nay. ':'')+sliceNote+")]
    for a, b in pairs:
        assert a in js, ("A4 changed", a)
        js = js.replace(a, b, 1)
    n["parameters"]["jsCode"] = js

def patch_c9(nodes):
    """Phiên mở từ chat Copilot (relay -> council-convene) đã đang họp: không để tick Convene, nếu không
    N9 sẽ tưởng Chủ tọa vừa tick và mở phiên lần 2."""
    n = next(n for n in nodes if n["name"] == "C9 · Build Convene Props")
    code = n["parameters"]["jsCode"]
    code = code.replace("'Status': { select: { name: 'Convened' } }", "'Status': { select: { name: 'In council' } }")
    code = code.replace("'Convene': { checkbox: true }", "'Convene': { checkbox: false }")
    assert "'In council'" in code and "checkbox: false" in code, "C9 patch did not apply"
    n["parameters"]["jsCode"] = code
def patch_s5(nodes, conns):
    """Freebuff's Phase-G edit put the estimate-drift code after `return` (dead) and fed every
    progress item into the EQ create node (no eqBody -> Notion 400). Emit both kinds, then split."""
    prep = next(n for n in nodes if n["name"] == "S5 · Prepare Progress History")
    code = prep["parameters"]["jsCode"]
    code = code.replace("return rows.map(t=>{", "const out = rows.map(t=>{", 1)
    code = re.sub(r"\nif\(triggers\.length\)\{return triggers\.concat\(rows\.map\(t=>\(\{json:t\.json\}\)\)\);\}\s*$",
                  "\nreturn out.concat(triggers);", code)
    assert "return out.concat(triggers);" in code, "S5 patch did not apply"
    prep["parameters"]["jsCode"] = code
    gate = {"id": sid("node", "S5 · Là cảnh báo lệch ước lượng?"), "name": "S5 · Là cảnh báo lệch ước lượng?", "type": "n8n-nodes-base.if",
            "typeVersion": 2.2, "position": [prep["position"][0] + 200, prep["position"][1] + 200],
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                                          "conditions": [{"id": sid("cond", "s5"), "leftValue": "={{ !!$json.eqBody }}", "rightValue": "",
                                                          "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                          "combinator": "and"}, "options": {}}}
    nodes.append(gate)
    conns[prep["name"]] = {"main": [[{"node": gate["name"], "type": "main", "index": 0}]]}
    # (Claude 2026-10-03) không còn cảnh báo lệch ước lượng theo TỪNG task -> 📅 Weekly Reviews gộp thành 1 dòng mỗi tuần
    conns[gate["name"]] = {"main": [[], [{"node": "S5 · Create Progress Snapshot", "type": "main", "index": 0}]]}

# --------------------------------------------------------------------------- assemble
def build(chat_auth="none"):
    all_nodes, all_conns, y = [], {}, 0
    for fn in (chat_section, brief_section, suggest_section, ingest_section, council_section, lecture_section, academic_section):
        n, c, h = fn(y); all_nodes += n; all_conns.update(c); y += h + 120
    for prefix, src, title, retime, run_now in SECTIONS:
        n, c, h = merge_section(prefix, src, title, retime, run_now, y)
        all_nodes += n; all_conns.update(c); y += h + 160
    patch_s5(all_nodes, all_conns)
    patch_a2_claim(all_nodes, all_conns)
    patch_a4_rest(all_nodes)
    patch_c9(all_nodes)
    patch_gemini_gate(all_nodes)
    names = [n["name"] for n in all_nodes]
    dup = {x for x in names if names.count(x) > 1}
    assert not dup, f"duplicate node names: {dup}"
    paths = [n["parameters"].get("path") for n in all_nodes if n["type"] == "n8n-nodes-base.webhook"]
    assert len(paths) == len(set(paths)), f"duplicate webhook paths: {paths}"
    fixed = 0
    for n in all_nodes:
        n["parameters"], hits = fix_tree(n.get("parameters", {}))
        fixed += bool(hits)
    print(f"expressions with inner '}}' fixed in {fixed} nodes")
    raw = json.dumps(all_nodes, ensure_ascii=False).replace("__CHAT_AUTH__", chat_auth)
    return {"name": WF_NAME, "nodes": json.loads(raw), "connections": all_conns,
            "settings": {"executionOrder": "v1", "timezone": TZ, "saveManualExecutions": True,
                         "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all", "executionTimeout": 900}}

def main():
    activate = "--activate" in sys.argv
    chat_auth = "n8nUserAuth" if "--secure-chat" in sys.argv else "none"
    wf = build(chat_auth)
    json.dump(wf, open(os.path.join(HERE, "copilot.workflow.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    wid = state.get("id")
    if wid:
        try:
            api("POST", f"/workflows/{wid}/deactivate")
        except RuntimeError:
            pass
        r = api("PUT", f"/workflows/{wid}", wf)
    else:
        r = api("POST", "/workflows", wf); wid = r["id"]
        json.dump({"id": wid}, open(STATE, "w"))
    print(f"workflow {wid}: {len(wf['nodes'])} nodes (chat auth: {chat_auth})")
    if activate:
        api("POST", f"/workflows/{wid}/activate"); print("activated")
    chat = next(n for n in wf["nodes"] if n["name"] == "Chat")
    print("chat url: http://localhost:5678/webhook/" + chat["webhookId"] + "/chat")

if __name__ == "__main__":
    main()
