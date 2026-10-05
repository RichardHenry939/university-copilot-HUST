"""Dựng trang so sánh 2 model chép lời (đặt cạnh nhau theo mốc 30 giây, bấm để nghe đúng đoạn)."""
import html, json, re

A, B = "whisper-large-v3", "phowhisper-large"
ra = json.load(open(f"result_{A}.json", encoding="utf-8"))
rb = json.load(open(f"result_{B}.json", encoding="utf-8"))
meta = json.load(open("sample.json", encoding="utf-8"))
HALLU = re.compile(r"(subscribe|đăng ký kênh|đăng kí kênh|lalaschool|ghiền mì gõ|cảm ơn các bạn đã theo dõi|like và share)", re.I)
STEP = 30


def bucket(r):
    out = {}
    for s in r["segments"]:
        out.setdefault(int(s["start"] // STEP), []).append(s)
    return out


def cell(segs):
    if not segs:
        return '<span class="none">—</span>'
    parts = []
    for s in segs:
        t = html.escape(s["text"])
        cls = "hallu" if HALLU.search(s["text"]) else ""
        parts.append(f'<span class="seg {cls}"><b>{s["start"]:.0f}s</b> {t}</span>')
    return "<br>".join(parts)


def stats(r):
    segs = r["segments"]
    hallu = sum(1 for s in segs if HALLU.search(s["text"]))
    texts = [s["text"] for s in segs]
    rep = sum(1 for i in range(1, len(texts)) if texts[i] and texts[i] == texts[i - 1])
    rt = r["transcribe_s"] / r["audio_s"]
    return (f'<b>{len(segs)}</b> đoạn · <b>{sum(len(t) for t in texts)}</b> ký tự · bịa chữ kiểu "subscribe": <b>{hallu}</b> · '
            f'câu lặp liền nhau: <b>{rep}</b> · tốc độ: <b>{rt:.2f}×</b> thời lượng (bài 3h ≈ <b>{rt*3:.1f} giờ</b>)')


ba, bb = bucket(ra), bucket(rb)
n = int(ra["audio_s"] // STEP) + 1
rows = []
for i in range(n):
    if i not in ba and i not in bb:
        continue
    t = i * STEP
    rows.append(f'<tr><td class="t"><button onclick="play({t})">▶ {t//60}:{t%60:02d}</button></td>'
                f'<td>{cell(ba.get(i))}</td><td>{cell(bb.get(i))}</td></tr>')

start = meta["start_sec"]
page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>So sánh chép lời</title>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f7fb;--card:#fff;--ink:#1d2433;--mute:#6b7385;--line:#e3e6ef;--a:#2d55c8;--b:#0f8a5f;--bad:#cf3434;--badbg:#fdecec}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151c;--card:#1b2029;--ink:#e6e9f0;--mute:#98a0b3;--line:#2b3240;--badbg:#3a1d1f}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 'Be Vietnam Pro',system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 80px}}
h1{{font-size:24px;margin:0 0 4px}}.sub{{color:var(--mute);margin:0 0 18px}}
.player{{position:sticky;top:0;z-index:2;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:16px}}
audio{{width:100%}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.card h2{{margin:0 0 6px;font-size:16px}}.card.a h2{{color:var(--a)}}.card.b h2{{color:var(--b)}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}
th{{font-size:13px;color:var(--mute);position:sticky;top:92px;background:var(--card)}}
td.t{{width:86px}}button{{font:inherit;font-size:13px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:8px;padding:4px 8px;cursor:pointer}}
button:hover{{border-color:var(--a)}}button:focus-visible{{outline:2px solid var(--a);outline-offset:2px}}
.seg b{{color:var(--mute);font-weight:400;font-size:12px;margin-right:4px}}
.hallu{{background:var(--badbg);color:var(--bad);border-radius:4px;padding:0 3px}}.none{{color:var(--mute)}}
.legend{{color:var(--mute);font-size:13px;margin:8px 0 0}}
@media (max-width:760px){{.cards{{grid-template-columns:1fr}}th{{top:0}}td.t{{width:60px}}}}
</style></head><body><main>
<h1>Whisper large-v3 hay PhoWhisper-large?</h1>
<p class="sub">Cùng 10 phút bài giảng thật (23/9, từ phút {start//60}), cùng bộ lọc giọng nói, cùng máy, chạy CPU. Bấm ▶ ở mỗi dòng để nghe đúng đoạn đó rồi đọc hai cột.</p>
<div class="player"><audio id="au" controls preload="metadata" src="sample.wav"></audio></div>
<div class="cards"><div class="card a"><h2>Whisper large-v3 (OpenAI)</h2>{stats(ra)}</div>
<div class="card b"><h2>PhoWhisper-large (VinAI)</h2>{stats(rb)}</div></div>
<table><thead><tr><th>Mốc</th><th>Whisper large-v3</th><th>PhoWhisper-large</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="legend">Ô đỏ = câu model tự bịa khi im lặng hoặc ồn (kiểu "hãy subscribe kênh…"), không có trong audio.</p>
</main><script>const au=document.getElementById('au');function play(t){{au.currentTime=t;au.play();}}</script></body></html>"""
open("compare.html", "w", encoding="utf-8").write(page)
print("compare.html written,", len(rows), "rows")
