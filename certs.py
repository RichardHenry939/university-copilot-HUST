# -*- coding: utf-8 -*-
"""Chứng chỉ ngoại ngữ (Claude 2026-10-03) — mục tiêu / đã có / đã hết hạn, quy đổi bậc, miễn học phần, chuẩn đầu ra.

Dữ liệu Notion (do certs_setup.py tạo, sửa được trong Notion):
  📚 Danh mục chứng chỉ ngoại ngữ (ĐHBK công nhận)  — mỗi dòng = 1 band của 1 chứng chỉ: Bậc, CEFR, hiệu lực (tháng), xét chuẩn đầu ra
  📏 Quy định miễn học phần ngoại ngữ (K70)          — FL1131..FL1135: miễn từ bậc; dòng CHUAN_DAU_RA: bậc tối thiểu khi xét tốt nghiệp
  🎫 Chứng chỉ ngoại ngữ của tôi (Home Dashboard)    — Mục: Mục tiêu | Đã có | Đã hết hạn | Đã xoá
Luật (Quy định ngoại ngữ từ K70, ĐHBK 2025):
  • TOEIC 4 kỹ năng: bậc = kỹ năng thấp nhất. • Miễn học phần: chứng chỉ phải còn hạn lúc nộp đơn (ghi điểm R).
  • Chuẩn đầu ra: tiếng Anh 4 kỹ năng, ≥ Bậc 3, cấp trong vòng 2 năm tính đến lúc xét, còn hiệu lực; không dùng TOEIC Placement.
  • Hết hạn = ngày cấp + hiệu lực (tháng) của danh mục; quên ngày cấp thì nhập thẳng ngày hết hạn. Hết hạn → tự sang "Đã hết hạn".
"""
import uc_config as cfg
import datetime as dt, json, time
from academic import Notion, P, rt, title, TZ

CATALOG = cfg.notion("cert_catalog")
RULES = cfg.notion("cert_rules")
MINE = cfg.notion("cert_mine")
TOEIC4 = "TOEIC 4 kỹ năng"
SKILLS = ["Nghe", "Đọc", "Nói", "Viết"]
MUC = ["Mục tiêu", "Đã có", "Đã hết hạn"]
_cat = {"at": 0, "rows": None, "rules": None}


def _today():
    return dt.datetime.now(TZ).date()

def _add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    import calendar
    return dt.date(d.year + y, mo + 1, min(d.day, calendar.monthrange(d.year + y, mo + 1)[1]))

def _d(s):
    return dt.date.fromisoformat(s[:10]) if s else None

def catalog(nt):
    """Danh mục + quy định (đệm 1 giờ — ít khi đổi)."""
    if _cat["rows"] is None or time.time() - _cat["at"] > 3600:
        rows = [{"id": r["id"], "band": (P(r, "Band") or "").removeprefix((P(r, "Chứng chỉ") or "") + " · "), "cert": P(r, "Chứng chỉ"), "lang": P(r, "Ngôn ngữ"),
                 "lv": P(r, "Bậc"), "lvn": P(r, "Bậc số"), "cefr": P(r, "CEFR"), "months": P(r, "Hiệu lực (tháng)"),
                 "grad": bool(P(r, "Xét chuẩn đầu ra")), "order": P(r, "Thứ tự") or 0, "note": P(r, "Ghi chú") or "", "src": P(r, "Nguồn") or ""}
                for r in nt.query(CATALOG)]
        rows.sort(key=lambda x: x["order"])
        rules = [{"code": P(r, "Mã"), "name": P(r, "Học phần"), "lv": P(r, "Miễn từ bậc"), "when": P(r, "Xếp lớp / đăng ký") or "",
                  "cond": P(r, "Điều kiện") or ""} for r in nt.query(RULES)]
        _cat.update({"rows": rows, "rules": rules, "at": time.time()})
    return _cat["rows"], _cat["rules"]

def _certs_view(rows):
    """Danh mục gọn cho giao diện: ngôn ngữ → chứng chỉ → band. TOEIC 4 kỹ năng gộp thành 1 chứng chỉ có 4 phần."""
    out = {}
    for r in rows:
        name = TOEIC4 if r["cert"].startswith(TOEIC4) else r["cert"]
        c = out.setdefault(name, {"name": name, "lang": r["lang"], "months": r["months"], "grad": r["grad"], "note": r["note"],
                                  "src": r["src"], "bands": [], "parts": {} if name == TOEIC4 else None})
        b = {"band": r["band"], "lv": r["lv"], "lvn": r["lvn"], "cefr": r["cefr"]}
        if name == TOEIC4: c["parts"].setdefault(r["cert"].split(" · ")[-1], []).append(b)
        else: c["bands"].append(b)
    return list(out.values())

def _lvlabel(lvn):
    if lvn is None: return ""
    return f"Bậc {lvn:g}"

def evaluate(c, rows, rules, today):
    """c: dict một chứng chỉ của tôi -> thêm bậc, hết hạn, còn hiệu lực, miễn, đạt chuẩn."""
    cat = [r for r in rows if (r["cert"] == c["cert"]) or (c["cert"] == TOEIC4 and r["cert"].startswith(TOEIC4))]
    months = cat[0]["months"] if cat else None
    english = bool(cat and cat[0]["lang"] == "Tiếng Anh")
    grad_ok_type = bool(cat and cat[0]["grad"])
    lvn = None
    if c["cert"] == TOEIC4:
        parts = c.get("parts") or {}
        vals = []
        for sk in SKILLS:
            m = next((r for r in cat if r["cert"].endswith(sk) and r["band"] == parts.get(sk)), None)
            vals.append(m["lvn"] if m else None)
        lvn = min(vals) if all(v is not None for v in vals) else None
    else:
        m = next((r for r in cat if r["band"] == c["band"]), None)
        lvn = m["lvn"] if m else None
    issued, expiry = _d(c.get("issued")), _d(c.get("expiry"))
    if not expiry and issued and months: expiry = _add_months(issued, int(months))
    if not issued and expiry and months: issued_est = _add_months(expiry, -int(months))
    else: issued_est = issued
    valid = c["muc"] == "Đã có" and (expiry is None or expiry >= today)
    exempt = sorted(r["code"] for r in rules if r["code"] != "CHUAN_DAU_RA" and english and valid and lvn is not None and lvn >= (r["lv"] or 99))
    need = next((r["lv"] for r in rules if r["code"] == "CHUAN_DAU_RA"), 3.1)
    grad = bool(valid and english and grad_ok_type and lvn is not None and lvn >= need and
                (issued_est is None or issued_est >= _add_months(today, -24)))
    days_left = (expiry - today).days if expiry else None
    return {**c, "lvn": lvn, "lvLabel": _lvlabel(lvn), "cefr": (cat and next((r["cefr"] for r in cat if r["lvn"] == lvn), None)) or None,
            "expiry": expiry.isoformat() if expiry else None, "issued": issued.isoformat() if issued else None,
            "noExpiry": months is None and not c.get("expiry"), "daysLeft": days_left, "valid": valid, "english": english,
            "exempt": exempt, "grad": grad, "lang": cat[0]["lang"] if cat else c.get("lang")}

def _mine(nt):
    out = []
    for r in nt.query(MINE):
        muc = P(r, "Mục")
        if muc not in MUC: continue
        try: parts = json.loads(P(r, "Chi tiết") or "{}")
        except Exception: parts = {}
        out.append({"id": r["id"], "muc": muc, "cert": P(r, "Chứng chỉ"), "band": P(r, "Band") or "", "parts": parts,
                    "issued": P(r, "Ngày cấp"), "expiry": P(r, "Ngày hết hạn"), "forgot": bool(P(r, "Quên ngày cấp")),
                    "note": P(r, "Ghi chú") or "", "_row": r})
    return out

def build(nt, sync=True):
    rows, rules = catalog(nt)
    today = _today()
    items = []
    for c in _mine(nt):
        row = c.pop("_row")
        e = evaluate(c, rows, rules, today)
        if sync:   # hết hạn -> tự chuyển mục; ghi kết quả tính vào Notion để xem được cả ở Home Dashboard
            want_muc = "Đã hết hạn" if e["muc"] == "Đã có" and e["expiry"] and _d(e["expiry"]) < today else e["muc"]
            want = {"Mục": want_muc, "Bậc": e["lvLabel"], "Bậc số": e["lvn"], "Miễn học phần": ", ".join(e["exempt"]) or "—",
                    "Đạt chuẩn đầu ra": e["grad"], "Ngày hết hạn": e["expiry"] if not c.get("expiry") else c["expiry"][:10]}
            have = {"Mục": P(row, "Mục"), "Bậc": P(row, "Bậc"), "Bậc số": P(row, "Bậc số"), "Miễn học phần": P(row, "Miễn học phần"),
                    "Đạt chuẩn đầu ra": bool(P(row, "Đạt chuẩn đầu ra")), "Ngày hết hạn": (P(row, "Ngày hết hạn") or "")[:10] or None}
            if want != have:
                nt.patch(row["id"], {"Mục": {"select": {"name": want_muc}}, "Bậc": rt(e["lvLabel"]), "Bậc số": {"number": e["lvn"]},
                                     "Miễn học phần": rt(want["Miễn học phần"]), "Đạt chuẩn đầu ra": {"checkbox": e["grad"]},
                                     "Ngày hết hạn": {"date": {"start": want["Ngày hết hạn"]} if want["Ngày hết hạn"] else None}})
                if want_muc != e["muc"]: e = evaluate({**c, "muc": want_muc}, rows, rules, today)
        items.append(e)
    valid_en = [x for x in items if x["valid"] and x["english"] and x["lvn"] is not None]
    best = max(valid_en, key=lambda x: x["lvn"], default=None)
    exempt = sorted({code for x in items for code in x["exempt"]})
    grad_cert = max((x for x in items if x["grad"]), key=lambda x: x["lvn"], default=None)
    need = next((r["lv"] for r in rules if r["code"] == "CHUAN_DAU_RA"), 3.1)
    return {"items": sorted(items, key=lambda x: (MUC.index(x["muc"]), -(x["lvn"] or 0))),
            "catalog": _certs_view(rows), "rules": rules,
            "summary": {"best": best and {"cert": best["cert"], "band": best["band"] or "4 kỹ năng", "lv": best["lvLabel"], "cefr": best["cefr"], "expiry": best["expiry"]},
                        "exempt": exempt, "gradOk": bool(grad_cert), "gradCert": grad_cert and f"{grad_cert['cert']} {grad_cert['band'] or ''}".strip(),
                        "gradNeed": "Bậc 3" if need == 3.1 else _lvlabel(need)}}


def save(post, a):
    """Thêm / sửa / xoá (Mục → Đã xoá) một chứng chỉ của tôi."""
    nt = Notion(post)
    rows, _ = catalog(nt)
    if a.get("action") == "delete":
        if not a.get("id"): return {"ok": False, "loi": "thiếu id"}
        nt.patch(a["id"], {"Mục": {"select": {"name": "Đã xoá"}}})
        return {"ok": True}
    muc = a.get("muc")
    if muc not in ("Mục tiêu", "Đã có"): return {"ok": False, "loi": "Chọn mục: Mục tiêu hoặc Đã có."}
    view = {c["name"]: c for c in _certs_view(rows)}
    c = view.get(a.get("cert"))
    if not c: return {"ok": False, "loi": "Chọn loại chứng chỉ."}
    parts, band = {}, ""
    if c["name"] == TOEIC4:
        parts = {sk: (a.get("parts") or {}).get(sk) for sk in SKILLS}
        bad = [sk for sk in SKILLS if parts[sk] not in [b["band"] for b in c["parts"].get(sk, [])]]
        if bad: return {"ok": False, "loi": "Chọn band cho đủ 4 kỹ năng (thiếu: " + ", ".join(bad) + ")."}
    else:
        band = a.get("band") or ""
        if band not in [b["band"] for b in c["bands"]]: return {"ok": False, "loi": "Chọn band điểm."}
    issued = a.get("issued") or None
    expiry = a.get("expiry") or None
    forgot = bool(a.get("forgot"))
    today = _today()
    if muc == "Đã có":
        if forgot:
            if not expiry and c["months"]: return {"ok": False, "loi": "Đã bấm quên ngày cấp: nhập ngày hết hạn."}
            issued = None
        else:
            if not issued: return {"ok": False, "loi": "Nhập ngày cấp (hoặc bấm 'Quên ngày cấp')."}
            if _d(issued) > today: return {"ok": False, "loi": "Ngày cấp không thể ở tương lai."}
            expiry = None
    label = f"{c['name']} · {band}" if band else f"{c['name']} · " + " / ".join(f"{k} {v}" for k, v in parts.items())
    props = {"Tên": title(label), "Mục": {"select": {"name": muc}}, "Chứng chỉ": {"select": {"name": c["name"]}},
             "Ngôn ngữ": {"select": {"name": c["lang"]}}, "Band": rt(band), "Chi tiết": rt(json.dumps(parts, ensure_ascii=False) if parts else ""),
             "Ngày cấp": {"date": {"start": issued} if issued else None}, "Ngày hết hạn": {"date": {"start": expiry} if expiry else None},
             "Quên ngày cấp": {"checkbox": forgot}, "Ghi chú": rt(a.get("note") or "")}
    if a.get("id"): nt.patch(a["id"], props)
    else: nt.create(MINE, props)
    return {"ok": True}
