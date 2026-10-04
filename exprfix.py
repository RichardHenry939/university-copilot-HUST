"""Fix n8n expressions whose JS contains '}}' (n8n 2.x ends the expression there)."""
def fix_expr(s):
    if not isinstance(s, str) or not s.startswith("=") or "{{" not in s:
        return s, False
    out, i, n, changed = [], 0, len(s), False
    while i < n:
        if s.startswith("{{", i):
            out.append("{{"); i += 2; depth = 0; q = None
            while i < n:
                c = s[i]
                if q:
                    out.append(c)
                    if c == "\\" and i + 1 < n: out.append(s[i+1]); i += 2; continue
                    if c == q: q = None
                    i += 1; continue
                if c in "'\"`": q = c; out.append(c); i += 1; continue
                if c == "{": depth += 1; out.append(c); i += 1; continue
                if c == "}":
                    if depth == 0 and s.startswith("}}", i):
                        out.append("}}"); i += 2; break
                    depth = max(0, depth - 1); out.append(c); i += 1
                    if i < n and s[i] == "}":
                        out.append(" "); changed = True
                    continue
                out.append(c); i += 1
        else:
            out.append(s[i]); i += 1
    return "".join(out), changed

def fix_tree(v, hits=None, path=""):
    if hits is None: hits = []
    if isinstance(v, str):
        nv, ch = fix_expr(v)
        if ch: hits.append(path)
        return nv, hits
    if isinstance(v, list):
        r = []
        for k, x in enumerate(v):
            nx, _ = fix_tree(x, hits, f"{path}[{k}]"); r.append(nx)
        return r, hits
    if isinstance(v, dict):
        r = {}
        for k, x in v.items():
            nx, _ = fix_tree(x, hits, f"{path}.{k}"); r[k] = nx
        return r, hits
    return v, hits
