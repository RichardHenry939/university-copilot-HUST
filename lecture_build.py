"""Dựng lại workflow "University — Lecture Analysis" (<lecture_analysis>) theo plan đã chốt 2/10 — Claude.

AUDIO KHÔNG BAO GIỜ ĐI TỚI GEMINI.
  Phần A (5 phút/lần): phiên Uploaded -> khoá -> tải audio Drive -> gửi cổng âm thanh→chữ→nén (máy, cổng 8340).
  Phần B (cổng gọi lại /webhook/lecture-transcript-ready):
     audio không dùng được -> Needs review (0 token)
     dùng được -> tìm tiết học trùng giờ (gán Course) -> Gemini nhận BẢN NÉN (chữ) + đoạn quanh marker + ảnh slide
       -> cổng chất lượng (is_lecture) -> Lecture Note (Course, nội dung đầy đủ, transcript) -> Inbox (Detected Course) -> Completed
  Cứu hộ: phiên Processing quá 6 giờ mà cổng không còn xử lý -> xếp hàng lại (tối đa 3 lần) -> Needs review.

Chạy:  python lecture_build.py [--dry]
Bản gốc các lần trước: D:\\Tools\\n8n-temp\\backup-claude-lecture-20261002\\
"""
import uc_config as cfg
import copy, json, sys, uuid
from n8napi import api, NOTION, GEMINI, APPKEY, DRIVE
from exprfix import fix_tree

WID = cfg.n8n_workflow("lecture_analysis")
NS = uuid.UUID("2f6c1d7a-0b11-4c1e-8f53-6b1f9d0a3e21")
SESSIONS_DB = cfg.notion("lecture_sessions")
NOTES_DB = cfg.notion("lecture_notes")
INBOX_DB = cfg.notion("inbox")
TIMETABLE_DB = cfg.notion("calendar_events")
GATE = "http://host.docker.internal:8340"
CALLBACK = "http://127.0.0.1:5678/webhook/lecture-transcript-ready"   # cổng chạy trên máy -> n8n qua cổng 5678
GEM = "http://host.docker.internal:8350/v1beta/models/{m}:generateContent?caller=lecture"   # qua cổng Gemini (đếm quota, dự phòng)

nodes, conns = [], {}


def sid(*p):
    return str(uuid.uuid5(NS, "|".join(p)))


def node(name, typ, pos, params, ver, **extra):
    n = {"id": sid("node", name), "name": name, "type": typ, "typeVersion": ver, "position": pos, "parameters": params}
    n.update(extra)
    nodes.append(n)
    return n


def link(a, b, out=0):
    c = conns.setdefault(a, {"main": []})
    while len(c["main"]) <= out:
        c["main"].append([])
    c["main"][out].append({"node": b, "type": "main", "index": 0})


def chain(*names):
    for a, b in zip(names, names[1:]):
        link(a, b)


NOTION_AUTH = {"authentication": "predefinedCredentialType", "nodeCredentialType": "notionApi",
               "sendHeaders": True, "specifyHeaders": "keypair",
               "headerParameters": {"parameters": [{"name": "Notion-Version", "value": "2022-06-28"}]}}


def notion(name, pos, method, url, body, **extra):
    p = {"method": method, "url": url, **copy.deepcopy(NOTION_AUTH), "options": {}}
    if body is not None:
        p.update(sendBody=True, contentType="raw", rawContentType="application/json", body=body)
    return node(name, "n8n-nodes-base.httpRequest", pos, p, 4.2, credentials=copy.deepcopy(NOTION),
                retryOnFail=True, maxTries=3, waitBetweenTries=5000, **extra)


def code(name, pos, js, each=False):
    p = {"jsCode": js.strip()}
    if each:
        p["mode"] = "runOnceForEachItem"
    return node(name, "n8n-nodes-base.code", pos, p, 2)


def iff(name, pos, expr):
    return node(name, "n8n-nodes-base.if", pos,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                                "conditions": [{"id": sid("cond", name), "leftValue": expr, "rightValue": "",
                                                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                "combinator": "and"}, "options": {}}, 2.2)


def patch_session(name, pos, body_expr, page_expr="={{ 'https://api.notion.com/v1/pages/' + $json.sessionPageId }}"):
    return notion(name, pos, "PATCH", page_expr, body_expr)


# =============================================================== PHẦN A: gửi audio cho cổng chép lời (máy)
Y = 0
node("Mỗi 5 phút", "n8n-nodes-base.scheduleTrigger", [0, Y], {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, 1.2)
notion("Tìm phiên đã upload", [220, Y], "POST", f"https://api.notion.com/v1/databases/{SESSIONS_DB}/query",
       json.dumps({"page_size": 1, "filter": {"and": [{"property": "State", "select": {"equals": "Uploaded"}},
                                                      {"property": "Drive File ID", "rich_text": {"is_not_empty": True}},
                                                      {"property": "Analysis Key", "rich_text": {"is_empty": True}}]}}))
code("Chuẩn hoá phiên", [440, Y], r"""
const r = $input.first().json.results || []; if (!r.length) return [];
const p = r[0], P = p.properties || {};
const txt = n => ((P[n] && P[n].rich_text) || []).map(t => t.plain_text).join('');
const dt = n => (P[n] && P[n].date && P[n].date.start) || '';
const cap = txt('Capture ID') || p.id;
return [{ json: { sessionPageId: p.id, sessionUrl: p.url, captureId: cap, driveFileId: txt('Drive File ID'),
  audioUrl: (P['Audio URL'] && P['Audio URL'].url) || '', markers: txt('Markers') || '[]',
  startedAt: dt('Started At'), endedAt: dt('Ended At'), analysisKey: cap + ':lecture-v2' } }];
""")
patch_session("Khoá phiên (đang chép lời)", [660, Y],
              "={{ JSON.stringify({ properties: { State: { select: { name: 'Processing' } },"
              " 'Analysis Key': { rich_text: [{ text: { content: $json.analysisKey } }] },"
              " 'Processing Notes': { rich_text: [{ text: { content: 'Đang chép lời TRÊN MÁY (cổng âm thanh→chữ→nén). Audio không gửi cho Gemini.' } }] } } }) }}")
node("Tải audio từ Drive", "n8n-nodes-base.googleDrive", [880, Y],
     {"resource": "file", "operation": "download", "authentication": "oAuth2",
      "fileId": {"__rl": True, "mode": "id", "value": "={{ $('Chuẩn hoá phiên').item.json.driveFileId }}"}, "options": {}},
     3, credentials=copy.deepcopy(DRIVE), retryOnFail=True, maxTries=3, waitBetweenTries=5000)
node("Gửi cổng chép lời", "n8n-nodes-base.httpRequest", [1100, Y],
     {"method": "POST",
      "url": "={{ '" + GATE + "/jobs?captureId=' + encodeURIComponent($('Chuẩn hoá phiên').item.json.captureId)"
             " + '&startedAt=' + encodeURIComponent($('Chuẩn hoá phiên').item.json.startedAt)"
             " + '&endedAt=' + encodeURIComponent($('Chuẩn hoá phiên').item.json.endedAt)"
             " + '&markers=' + encodeURIComponent($('Chuẩn hoá phiên').item.json.markers)"
             " + '&callback=' + encodeURIComponent('" + CALLBACK + "') }}",
      "sendBody": True, "contentType": "binaryData", "inputDataFieldName": "data", "options": {"timeout": 300000}},
     4.2, onError="continueErrorOutput", retryOnFail=True, maxTries=3, waitBetweenTries=20000)
patch_session("Mở khoá khi cổng lỗi", [1320, Y + 180],
              "={{ JSON.stringify({ properties: { State: { select: { name: 'Uploaded' } }, 'Analysis Key': { rich_text: [] },"
              " 'Processing Notes': { rich_text: [{ text: { content: 'Cổng chép lời trên máy không phản hồi lúc ' + $now.setZone('Asia/Ho_Chi_Minh').toFormat('dd/MM HH:mm') + ' — tự thử lại lượt sau.' } }] } } }) }}",
              page_expr="={{ 'https://api.notion.com/v1/pages/' + $('Chuẩn hoá phiên').item.json.sessionPageId }}")
chain("Mỗi 5 phút", "Tìm phiên đã upload", "Chuẩn hoá phiên", "Khoá phiên (đang chép lời)", "Tải audio từ Drive", "Gửi cổng chép lời")
link("Gửi cổng chép lời", "Mở khoá khi cổng lỗi", 1)

# --- cứu hộ: Processing > 6 giờ và cổng không còn xử lý -> xếp hàng lại / Needs review
Y = 360
notion("Tìm phiên kẹt", [220, Y], "POST", f"https://api.notion.com/v1/databases/{SESSIONS_DB}/query",
       "={{ JSON.stringify({ page_size: 20, filter: { and: [ { property: 'State', select: { equals: 'Processing' } },"
       " { timestamp: 'last_edited_time', last_edited_time: { before: new Date(Date.now() - 6 * 3600e3).toISOString() } } ] } }) }}")
code("Tách phiên kẹt", [440, Y], r"""
return ($json.results || []).map(p => ({ json: { sessionPageId: p.id,
  captureId: ((p.properties['Capture ID'] || {}).rich_text || []).map(t => t.plain_text).join(''),
  notes: ((p.properties['Processing Notes'] || {}).rich_text || []).map(t => t.plain_text).join('') } }));
""")
node("Hỏi cổng còn xử lý?", "n8n-nodes-base.httpRequest", [660, Y],
     {"method": "GET", "url": "={{ '" + GATE + "/jobs?captureId=' + encodeURIComponent($json.captureId) }}",
      "options": {"response": {"response": {"neverError": True}}}}, 4.2, onError="continueRegularOutput", alwaysOutputData=True)
code("Quyết định cứu hộ", [880, Y], r"""
const s = $('Tách phiên kẹt').item.json, g = $json || {};
if (g.status === 'queued' || g.status === 'running') return [];                  // cổng còn đang chép lời: để yên
const m = s.notes.match(/lần thử (\d+)/); const tries = m ? Number(m[1]) : 1;
const stamp = $now.setZone('Asia/Ho_Chi_Minh').toFormat('dd/MM HH:mm');
const props = tries >= 3
  ? { State: { select: { name: 'Needs review' } }, 'Processing Notes': { rich_text: [{ text: { content: `Xử lý lỗi ${tries} lần (${stamp}) — cần xem lại.` } }] } }
  : { State: { select: { name: 'Uploaded' } }, 'Analysis Key': { rich_text: [] },
      'Processing Notes': { rich_text: [{ text: { content: `Xử lý bị treo/lỗi — xếp hàng chạy lại (lần thử ${tries + 1}) lúc ${stamp}.` } }] } };
return [{ json: { sessionPageId: s.sessionPageId, body: { properties: props } } }];
""", each=True)
patch_session("Xếp hàng lại", [1100, Y], "={{ JSON.stringify($json.body) }}")
link("Mỗi 5 phút", "Tìm phiên kẹt")
chain("Tìm phiên kẹt", "Tách phiên kẹt", "Hỏi cổng còn xử lý?", "Quyết định cứu hộ", "Xếp hàng lại")

# =============================================================== PHẦN B: cổng gọi lại -> Gemini (chữ) -> Notion
Y = 640
node("Nhận bản chép lời", "n8n-nodes-base.webhook", [0, Y],
     {"path": "lecture-transcript-ready", "httpMethod": "POST", "authentication": "headerAuth", "responseMode": "onReceived",
      "options": {"rawBody": False}}, 2, webhookId=sid("hook", "transcript"), credentials=copy.deepcopy(APPKEY))
notion("Tìm phiên theo Capture ID", [220, Y], "POST", f"https://api.notion.com/v1/databases/{SESSIONS_DB}/query",
       "={{ JSON.stringify({ page_size: 1, filter: { property: 'Capture ID', rich_text: { equals: $json.body.captureId || '-' } } }) }}")
code("Gom dữ liệu phiên", [440, Y], r"""
const b = $('Nhận bản chép lời').first().json.body || {};
const p = ($json.results || [])[0];
if (!p) throw new Error('Không thấy Lecture Session cho ' + b.captureId);
const P = p.properties || {};
const dt = n => (P[n] && P[n].date && P[n].date.start) || '';
return [{ json: { sessionPageId: p.id, captureId: b.captureId, status: b.status, reason: b.reason || '', stats: b.stats || {},
  compact: b.compact || '', excerpts: b.excerpts || [], transcript: b.transcript || '', slides: b.slides || [],
  audioUrl: (P['Audio URL'] && P['Audio URL'].url) || '', startedAt: dt('Started At') || b.startedAt || '',
  endedAt: dt('Ended At') || b.endedAt || '' } }];
""")
iff("Audio dùng được?", [660, Y], "={{ $json.status === 'done' }}")
patch_session("Ghi: audio không dùng được", [880, Y + 200],
              "={{ JSON.stringify({ properties: { State: { select: { name: 'Needs review' } },"
              " 'Processing Notes': { rich_text: [{ text: { content: ('Cổng chép lời: ' + ($json.status === 'error' ? 'LỖI — ' : '') + $json.reason).slice(0, 1900) } }] } } }) }}")
notion("Tìm tiết học trùng giờ", [880, Y], "POST", f"https://api.notion.com/v1/databases/{TIMETABLE_DB}/query",
       "={{ JSON.stringify({ page_size: 20, filter: { and: [ { property: 'Kind', select: { equals: 'Class' } },"
       " { property: 'When', date: { on_or_after: new Date(new Date($json.startedAt).getTime() - 4 * 3600e3).toISOString() } },"
       " { property: 'When', date: { on_or_before: ($json.endedAt || new Date(new Date($json.startedAt).getTime() + 4 * 3600e3).toISOString()) } } ] } }) }}")
code("Dựng yêu cầu Gemini (chữ)", [1100, Y], r"""
// Gemini chỉ nhận CHỮ đã nén + ảnh slide. Gán môn theo tiết học trùng giờ nhiều nhất.
const s = $('Gom dữ liệu phiên').item.json;
const t0 = new Date(s.startedAt).getTime(), t1 = s.endedAt ? new Date(s.endedAt).getTime() : t0 + 3 * 3600e3;
let best = null, bestOv = 0;
for (const e of ($json.results || [])) {
  const w = (e.properties.When || {}).date || {}; if (!w.start) continue;
  const a = new Date(w.start).getTime(), b = w.end ? new Date(w.end).getTime() : a + 3600e3;
  const ov = Math.min(b, t1) - Math.max(a, t0);
  if (ov > bestOv) { bestOv = ov; best = e; }
}
const title = p => ((p.properties.Event || {}).title || []).map(t => t.plain_text).join('');
const course = best ? { name: title(best), courseIds: ((best.properties.Course || {}).relation || []).map(r => r.id),
  location: ((best.properties.Location || {}).rich_text || []).map(t => t.plain_text).join(''), overlapMin: Math.round(bestOv / 60000) } : null;
const st = s.stats || {};
const instruction = [
  'Bạn là hệ thống xử lý bài giảng đại học tiếng Việt (sinh viên năm 1 Kỹ thuật Máy tính, HUST).',
  'Đầu vào KHÔNG phải audio mà là BẢN NÉN từ bản chép lời tự động (PhoWhisper chạy trên máy): có thể sai chính tả thuật ngữ',
  '(ví dụ "gắn mác" = "gán max", "ngôn ngữ X" có thể là "ngôn ngữ C"). Sửa theo ngữ cảnh môn học, nhưng TUYỆT ĐỐI không bịa nội dung không có trong bản nén.',
  course ? `Môn theo thời khoá biểu (trùng ${course.overlapMin} phút): ${course.name}${course.location ? ' — phòng ' + course.location : ''}.` : 'Không tìm thấy tiết học trùng giờ trong thời khoá biểu.',
  `Chất lượng audio: ${st.speech_min} phút tiếng nói / ${st.duration_min} phút; độ tin cậy chép lời avg_logprob=${st.avg_logprob}.`,
  'TRƯỚC HẾT xác định đây có thật là bài giảng/lớp học không. Hội thoại sinh hoạt, chuyện ngoài lề, nội dung vô nghĩa => is_lecture=false.',
  'Trả về duy nhất một JSON object hợp lệ với các khóa: is_lecture (boolean), title, summary, language, key_concepts, definitions, formulas,',
  'worked_examples, important_points, unclear_points, homework, deadlines, next_lecture_preparation, confidence.',
  'Mỗi trường danh sách là array chuỗi (tối đa 10 phần tử, mỗi phần tử ≤ 200 ký tự); confidence 0..1. Deadline ghi rõ ngày nếu suy ra được từ ngày học ' + (s.startedAt || '').slice(0, 10) + '.',
  'Các đoạn quanh MARKER do sinh viên bấm trong giờ học là tín hiệu ưu tiên (quan trọng / BTVN / có thể thi).',
].join('\n');
const parts = [{ text: instruction }, { text: '=== BẢN NÉN BÀI GIẢNG ===\n' + s.compact }];
if (s.excerpts.length) parts.push({ text: '=== ĐOẠN QUANH MARKER (nguyên văn chép lời) ===\n' + s.excerpts.map(x => `[${x.at}] (${x.kind}${x.note ? ': ' + x.note : ''}) ${x.text}`).join('\n') });
for (const im of s.slides.slice(0, 12)) parts.push({ inline_data: { mime_type: im.mime, data: im.data } });
if (s.slides.length) parts.push({ text: `(${s.slides.length} ảnh slide/bảng sinh viên chụp trong giờ học ở trên — dùng để kiểm chứng và bổ sung.)` });
return { json: { course, requestBody: { contents: [{ parts }], generationConfig: { responseMimeType: 'application/json', temperature: 0.1, maxOutputTokens: 8192 } } } };
""", each=True)
gl = node("Gemini phân tích (Flash-Lite)", "n8n-nodes-base.httpRequest", [1320, Y],
          {"method": "POST", "url": GEM.format(m="gemini-3.5-flash-lite"), "authentication": "predefinedCredentialType",
           "nodeCredentialType": "googlePalmApi", "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
           "body": "={{ JSON.stringify($json.requestBody) }}", "options": {"timeout": 300000}},
          4.2, credentials=copy.deepcopy(GEMINI), retryOnFail=True, maxTries=3, waitBetweenTries=20000, onError="continueErrorOutput")
node("Gemini phân tích (Flash dự phòng)", "n8n-nodes-base.httpRequest", [1320, Y + 200],
     {**copy.deepcopy(gl["parameters"]), "url": GEM.format(m="gemini-3.5-flash"),
      "body": "={{ JSON.stringify($('Dựng yêu cầu Gemini (chữ)').item.json.requestBody) }}"},
     4.2, credentials=copy.deepcopy(GEMINI), retryOnFail=True, maxTries=4, waitBetweenTries=30000)
code("Chuẩn hoá kết quả Gemini", [1540, Y], r"""
const cands = $json.candidates || [];
const part = cands[0] && cands[0].content && cands[0].content.parts && cands[0].content.parts[0];
const raw = part && part.text; let x = null, note = '';
if (raw) { const s = String(raw); const a = s.indexOf('{'), b = s.lastIndexOf('}');
  if (a >= 0 && b > a) { try { x = JSON.parse(s.slice(a, b + 1)); } catch (e) { note = 'unparseable'; } } }
const str = v => v == null ? '' : (typeof v === 'string' ? v : (Array.isArray(v) ? v.map(str).join('; ') : (typeof v === 'object' ? Object.values(v).map(str).join(' — ') : String(v))));
const arr = n => (x && Array.isArray(x[n]) ? x[n] : []).map(str).filter(Boolean).slice(0, 12);
const s = $('Gom dữ liệu phiên').item.json, req = $('Dựng yêu cầu Gemini (chữ)').item.json;
const u = $json.usageMetadata || {};
return { json: { ok: !!x, is_lecture: !!x && x.is_lecture !== false, title: str(x && x.title).slice(0, 180) || ('Bài giảng ' + s.captureId),
  summary: str(x && x.summary).slice(0, 1900), key_concepts: arr('key_concepts'), definitions: arr('definitions'), formulas: arr('formulas'),
  worked_examples: arr('worked_examples'), important_points: arr('important_points'), unclear_points: arr('unclear_points'),
  homework: arr('homework'), deadlines: arr('deadlines'), next_lecture_preparation: arr('next_lecture_preparation'),
  confidence: Number((x && x.confidence) || 0), parseNote: note, course: req.course,
  tokens: { prompt: u.promptTokenCount || 0, output: u.candidatesTokenCount || 0 } } };
""", each=True)
iff("Có nội dung bài giảng?", [1760, Y],
    "={{ $json.ok && $json.is_lecture && $json.confidence >= 0.35 && !!($json.summary || $json.key_concepts.length || $json.important_points.length) }}")
patch_session("Ghi: không phải bài giảng", [1980, Y + 200],
              "={{ JSON.stringify({ properties: { State: { select: { name: 'Needs review' } },"
              " 'Processing Notes': { rich_text: [{ text: { content: ('Gemini (đọc bản nén chữ) đánh giá KHÔNG có nội dung bài giảng rõ ràng: ' + $json.title + ' (độ tin cậy ' + Math.round($json.confidence * 100) + '%). ' + $json.unclear_points.join('; ')).slice(0, 1900) } }] } } }) }}",
              page_expr="={{ 'https://api.notion.com/v1/pages/' + $('Gom dữ liệu phiên').item.json.sessionPageId }}")
notion("Tạo Lecture Note", [1980, Y], "POST", "https://api.notion.com/v1/pages",
       "={{ JSON.stringify({ parent: { database_id: '" + NOTES_DB + "' }, properties: Object.assign({"
       " 'Lecture': { title: [{ text: { content: $json.title } }] },"
       " 'Session': { relation: [{ id: $('Gom dữ liệu phiên').item.json.sessionPageId }] },"
       " 'Lecture Date': { date: { start: $('Gom dữ liệu phiên').item.json.startedAt } },"
       " 'Summary': { rich_text: [{ text: { content: $json.summary } }] },"
       " 'Review Status': { select: { name: 'Needs review' } },"
       " 'Analysis Key': { rich_text: [{ text: { content: $('Gom dữ liệu phiên').item.json.captureId + ':lecture-v2' } }] } },"
       " $('Gom dữ liệu phiên').item.json.audioUrl ? { 'Source Audio': { url: $('Gom dữ liệu phiên').item.json.audioUrl } } : {},"
       " ($json.course && $json.course.courseIds.length) ? { 'Course': { relation: $json.course.courseIds.map(id => ({ id })) } } : {}) }) }}")
code("Dựng nội dung ghi chú", [2200, Y], r"""
const g = $('Chuẩn hoá kết quả Gemini').item.json, s = $('Gom dữ liệu phiên').item.json, note = $json;
const rt = t => [{ type: 'text', text: { content: String(t ?? '').slice(0, 1900) } }];
const B = [];
const h2 = t => B.push({ object: 'block', type: 'heading_2', heading_2: { rich_text: rt(t) } });
const list = (t, a, kind = 'bulleted_list_item') => { if (!a || !a.length) return; h2(t); a.forEach(v => B.push({ object: 'block', type: kind, [kind]: { rich_text: rt(v) } })); };
const st = s.stats || {};
B.push({ object: 'block', type: 'callout', callout: { icon: { emoji: '🧭' }, rich_text: rt(
  (g.course ? `Môn: ${g.course.name}${g.course.location ? ' · ' + g.course.location : ''}. ` : '') + (g.summary || '')) } });
list('📌 Ý quan trọng', g.important_points); list('🧠 Khái niệm chính', g.key_concepts); list('📖 Định nghĩa', g.definitions);
list('∑ Công thức', g.formulas); list('✏️ Ví dụ / bài mẫu', g.worked_examples);
list('📝 Bài tập về nhà', g.homework, 'to_do'); list('⏰ Deadline được nhắc', g.deadlines, 'to_do');
list('➡️ Chuẩn bị buổi sau', g.next_lecture_preparation); list('❓ Chưa rõ — cần kiểm tra lại', g.unclear_points);
const chunks = []; const T = s.transcript || ''; for (let i = 0; i < T.length && chunks.length < 40; i += 1900) chunks.push(T.slice(i, i + 1900));
if (chunks.length) B.push({ object: 'block', type: 'toggle', toggle: { rich_text: rt('🎧 Bản chép lời đầy đủ (tự động, chạy trên máy — có thể sai chính tả)'),
  children: chunks.map(c => ({ object: 'block', type: 'paragraph', paragraph: { rich_text: rt(c) } })) } });
B.push({ object: 'block', type: 'paragraph', paragraph: { rich_text: rt(
  `Nguồn: ${st.speech_min} phút tiếng nói/${st.duration_min} phút · chép lời trên máy ${st.stt_min} phút · bản nén ${st.compact_chars} ký tự · ` +
  `${s.slides.length} ảnh slide · Gemini ~${g.tokens.prompt + g.tokens.output} token (không gửi audio) · độ tin cậy ${Math.round(g.confidence * 100)}%` +
  (g.parseNote ? ' · ' + g.parseNote : '')) } });
return { json: { noteId: note.id, noteUrl: note.url, children: B.slice(0, 98) } };
""", each=True)
notion("Ghi nội dung ghi chú", [2420, Y], "PATCH", "={{ 'https://api.notion.com/v1/blocks/' + $json.noteId + '/children' }}",
       "={{ JSON.stringify({ children: $json.children }) }}", onError="continueRegularOutput")
notion("Bàn giao University Inbox", [2640, Y], "POST", "https://api.notion.com/v1/pages",
       "={{ (() => { const g = $('Chuẩn hoá kết quả Gemini').item.json; const n = $('Dựng nội dung ghi chú').item.json;"
       " const ctx = ('Bài giảng: ' + g.title + (g.course ? ' — ' + g.course.name : '') + ' (' + ($('Gom dữ liệu phiên').item.json.startedAt || '').slice(0, 10) + ').'"
       " + (g.homework.length ? ' BTVN: ' + g.homework.join('; ') + '.' : '') + (g.deadlines.length ? ' Deadline: ' + g.deadlines.join('; ') + '.' : '')"
       " + ' Ghi chú đầy đủ: ' + n.noteUrl).slice(0, 1990);"
       " const props = { 'Upload': { title: [{ text: { content: ('Lecture Review — ' + g.title).slice(0, 190) } }] },"
       " 'Triage Status': { status: { name: 'Not started' } }, 'Context': { rich_text: [{ text: { content: ctx } }] } };"
       " if (g.course && g.course.courseIds.length) props['Detected Course'] = { relation: g.course.courseIds.map(id => ({ id })) };"
       " return JSON.stringify({ parent: { database_id: '" + INBOX_DB + "' }, properties: props }); })() }}")
patch_session("Hoàn tất phiên", [2860, Y],
              "={{ JSON.stringify({ properties: { State: { select: { name: 'Completed' } },"
              " 'Processed Note': { url: $('Dựng nội dung ghi chú').item.json.noteUrl },"
              " 'University Inbox Item': { relation: [{ id: $json.id }] },"
              " 'Transcript': { rich_text: [{ text: { content: String($('Gom dữ liệu phiên').item.json.compact || '').slice(0, 1900) } }] },"
              " 'Processing Notes': { rich_text: [{ text: { content: ('Xong: chép lời trên máy (' + ($('Gom dữ liệu phiên').item.json.stats.speech_min) + ' phút tiếng nói) → nén → Gemini ~'"
              " + ($('Chuẩn hoá kết quả Gemini').item.json.tokens.prompt + $('Chuẩn hoá kết quả Gemini').item.json.tokens.output) + ' token'"
              " + ($('Chuẩn hoá kết quả Gemini').item.json.course ? ' · môn ' + $('Chuẩn hoá kết quả Gemini').item.json.course.name : ' · không khớp tiết học nào') + '.').slice(0, 1900) } }] } } }) }}",
              page_expr="={{ 'https://api.notion.com/v1/pages/' + $('Gom dữ liệu phiên').item.json.sessionPageId }}")

chain("Nhận bản chép lời", "Tìm phiên theo Capture ID", "Gom dữ liệu phiên", "Audio dùng được?")
link("Audio dùng được?", "Tìm tiết học trùng giờ", 0)
link("Audio dùng được?", "Ghi: audio không dùng được", 1)
chain("Tìm tiết học trùng giờ", "Dựng yêu cầu Gemini (chữ)", "Gemini phân tích (Flash-Lite)")
link("Gemini phân tích (Flash-Lite)", "Chuẩn hoá kết quả Gemini", 0)
link("Gemini phân tích (Flash-Lite)", "Gemini phân tích (Flash dự phòng)", 1)
link("Gemini phân tích (Flash dự phòng)", "Chuẩn hoá kết quả Gemini")
link("Chuẩn hoá kết quả Gemini", "Có nội dung bài giảng?")
link("Có nội dung bài giảng?", "Tạo Lecture Note", 0)
link("Có nội dung bài giảng?", "Ghi: không phải bài giảng", 1)
chain("Tạo Lecture Note", "Dựng nội dung ghi chú", "Ghi nội dung ghi chú", "Bàn giao University Inbox", "Hoàn tất phiên")

nodes.append({"id": sid("sticky", "main"), "name": "Ghi chú luồng", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
              "position": [-60, -260], "parameters": {"width": 1500, "height": 220, "color": 6, "content":
              "## 🎙️ Lecture Analysis v2 (2/10) — audio KHÔNG đi tới Gemini\n"
              "A: phiên Uploaded → tải audio → **cổng âm thanh→chữ→nén trên máy** (PhoWhisper + LM Studio, cổng 8340).\n"
              "B: cổng gọi lại → audio kém = Needs review (0 token) · dùng được = gán môn theo thời khoá biểu → Gemini đọc BẢN NÉN + ảnh slide → Lecture Note + Inbox.\n"
              "Cứu hộ: Processing > 6 giờ mà cổng không còn xử lý → xếp hàng lại (tối đa 3 lần)."}})

for n in nodes:
    n["parameters"], _ = fix_tree(n["parameters"])
cur = api("GET", f"/workflows/{WID}")
body = {"name": cur["name"], "nodes": nodes, "connections": conns, "nodeGroups": [],
        "settings": {"executionOrder": "v1", "timezone": "Asia/Ho_Chi_Minh", "saveDataErrorExecution": "all",
                     "saveDataSuccessExecution": "all", "executionTimeout": 1800}}
if "--dry" in sys.argv:
    print(len(nodes), "nodes"); sys.exit()
activate = "--activate" in sys.argv
try:
    api("POST", f"/workflows/{WID}/deactivate")
except RuntimeError:
    pass
api("PUT", f"/workflows/{WID}", body)
if activate:
    api("POST", f"/workflows/{WID}/activate")
print("Lecture Analysis v2:", len(nodes), "nodes", "(active)" if activate else "(inactive)")
