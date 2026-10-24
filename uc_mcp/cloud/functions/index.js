// (v1.00.34) Connector MCP của UC trên Firebase — CHỈ ĐỌC.
// Máy bạn tự gửi bản tóm tắt lên (uc_mcp/push.py, mỗi 10 phút) qua POST /api/push (khoá PUSH_KEY).
// Claude gọi MCP ở POST /m/<MCP_KEY>: đường dẫn bí mật dài, sai khoá -> 404 như trang không tồn tại.
// Quá STALE_MIN phút không có bản mới -> coi là máy đang tắt: trả bản cuối làm báo cáo sơ bộ, ghi rõ thời điểm.
// Khoá đọc từ functions/.env (không đưa lên repo).
const crypto = require('crypto');
const { onRequest } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');

admin.initializeApp();
const db = admin.firestore();
const DOC = db.collection('uc').doc('snapshot');
const STALE_MIN = 20;
const PROTOS = ['2025-06-18', '2025-03-26', '2024-11-05'];
const OFFLINE = 'Máy tính đang tắt (hoặc UC không chạy): không có dữ liệu mới. Hãy nói rõ với người dùng là máy đang tắt. ' +
  'Phần "ban_so_bo" là bản UC gửi lần cuối (xem "lan_cuoi"), chỉ dùng làm báo cáo sơ bộ; muốn mới hơn thì đọc Notion (Academic Work, Calendar).';
const STATUS_VN = { co_lich: 'có lịch thi', du_kien: 'dự kiến', chua_lich: 'có thi, chưa có lịch', chua_co: 'chưa có thông báo', khong_thi: 'không thi giữa kỳ' };
const NO_ARGS = { type: 'object', properties: {} };
const TOOLS = [
  { name: 'uc_status', description: 'Máy tính có đang chạy University Copilot không, và UC gửi dữ liệu lần cuối lúc nào.', inputSchema: NO_ARGS },
  { name: 'uc_today', description: 'Tổng quan từ UC: thi giữa kỳ từng môn, hạn đang mở (cờ môn có thi giữa kỳ), việc hôm nay.', inputSchema: NO_ARGS },
  { name: 'uc_deadlines', description: 'Các hạn nộp còn mở, sắp hết hạn trước. Tham số days (mặc định 21).',
    inputSchema: { type: 'object', properties: { days: { type: 'integer', default: 21 } } } },
  { name: 'uc_exams', description: 'Thi giữa kỳ: lịch chính thức (FAMI) và trạng thái từng môn (dự kiến / chưa có lịch / không thi).', inputSchema: NO_ARGS },
  { name: 'uc_briefing', description: 'Báo cáo sơ bộ một trang. Khi máy tắt: báo máy đang tắt kèm bản cuối.', inputSchema: NO_ARGS },
];

function same(a, b) {
  const A = Buffer.from(String(a || '')), B = Buffer.from(String(b || ''));
  return A.length > 0 && A.length === B.length && crypto.timingSafeEqual(A, B);
}

function liveDeadlines(snap, days) {   // tính lại số phút còn lại tại lúc đọc (bản tóm tắt có thể cũ vài phút)
  const now = Date.now();
  return (snap.han_tat_ca || []).map(x => ({ ...x, con_phut: x.han ? Math.round((Date.parse(x.han) - now) / 60000) : x.con_phut }))
    .filter(x => x.con_phut >= 0 && (days == null || x.con_phut <= days * 1440))
    .sort((a, b) => a.con_phut - b.con_phut);
}

function toolData(name, args, snap) {
  const t = snap.today || {};
  if (name === 'uc_today') return { ...t, han_dang_mo: liveDeadlines(snap).slice(0, 30) };
  if (name === 'uc_deadlines') { const h = liveDeadlines(snap, Number(args.days) || 21); return { so_luong: h.length, han: h }; }
  if (name === 'uc_exams') return { lich_thi_giua_ki: t.lich_thi_giua_ki || [], thi_giua_ki_tung_mon: t.thi_giua_ki_tung_mon || [] };
  if (name === 'uc_briefing') return { bao_cao: snap.bao_cao || '' };
  return {};
}

async function callTool(name, args) {
  if (!TOOLS.some(t => t.name === name)) return null;
  const doc = await DOC.get();
  const at = doc.exists ? doc.get('at') : null;
  const age = at ? (Date.now() - Date.parse(at)) / 60000 : Infinity;
  const online = age <= STALE_MIN;
  if (name === 'uc_status') return { online, lan_cuoi: at, phut_truoc: Number.isFinite(age) ? Math.round(age) : null };
  if (!doc.exists) return { online: false, thong_bao: OFFLINE, lan_cuoi: null, ban_so_bo: null };
  const snap = doc.get('data') || {};
  const data = toolData(name, args || {}, snap);
  if (online) return { online: true, lan_cuoi: at, ...data };
  return { online: false, thong_bao: OFFLINE, lan_cuoi: at, ban_so_bo: data };
}

async function rpc(msg) {
  const { id, method, params = {} } = msg || {};
  if (id === undefined || id === null) return null;   // thông báo: không trả lời
  const ok = result => ({ jsonrpc: '2.0', id, result });
  const err = (code, message) => ({ jsonrpc: '2.0', id, error: { code, message } });
  try {
    if (method === 'initialize') {
      const v = PROTOS.includes(params.protocolVersion) ? params.protocolVersion : PROTOS[1];
      return ok({ protocolVersion: v, capabilities: { tools: {} }, serverInfo: { name: 'uc', version: '1.1.0' },
        instructions: 'Dữ liệu học tập cá nhân của chủ UC, chỉ đọc. Luôn xem trường online; khi false thì nói rõ máy đang tắt.' });
    }
    if (method === 'tools/list') return ok({ tools: TOOLS });
    if (method === 'ping') return ok({});
    if (method === 'tools/call') {
      const out = await callTool(params.name, params.arguments);
      if (out === null) return err(-32602, 'không có công cụ ' + params.name);
      return ok({ content: [{ type: 'text', text: JSON.stringify(out, null, 1) }], isError: false });
    }
    return err(-32601, 'không hỗ trợ ' + method);
  } catch (e) {
    return ok({ content: [{ type: 'text', text: 'Lỗi: ' + (e && e.message) }], isError: true });
  }
}

exports.ucmcp = onRequest({ region: 'asia-southeast1', maxInstances: 2, memory: '256MiB', timeoutSeconds: 30, invoker: 'public' }, async (req, res) => {
  res.set('X-Robots-Tag', 'noindex, nofollow, noarchive');
  res.set('Cache-Control', 'no-store');
  const path = req.path || '/';

  if (path === '/api/push') {
    if (req.method !== 'POST' || !same(req.get('X-UC-Push'), process.env.PUSH_KEY)) return res.status(404).send('Not found');
    const data = req.body;
    if (!data || typeof data !== 'object' || !data.at) return res.status(400).json({ loi: 'thiếu dữ liệu' });
    await DOC.set({ at: data.at, data, received: admin.firestore.FieldValue.serverTimestamp() });
    return res.status(200).json({ ok: true });
  }

  const m = path.match(/^\/m\/([A-Za-z0-9_-]+)\/?$/);
  if (!m || !same(m[1], process.env.MCP_KEY)) return res.status(404).send('Not found');
  if (req.method === 'GET') return res.status(405).set('Allow', 'POST').json({ loi: 'dùng POST' });
  if (req.method === 'DELETE') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).end();

  const body = req.body;
  if (Array.isArray(body)) {
    const outs = (await Promise.all(body.map(rpc))).filter(Boolean);
    return outs.length ? res.status(200).json(outs) : res.status(202).end();
  }
  const out = await rpc(body);
  return out ? res.status(200).json(out) : res.status(202).end();
});

exports._test = { rpc, liveDeadlines, toolData, same, STATUS_VN };
