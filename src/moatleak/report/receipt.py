"""Receipt v2 and prompt-passport share cards (1080x1350, pure SVG) and their section."""
import math

from moatleak.headlines import pct
from moatleak.report import svg

_MONO = 'ui-monospace,"SF Mono",Menlo,Consolas,"DejaVu Sans Mono",monospace'
_PAPER, _SUB = "#FFFEFA", "#5b5d69"
_BASIS = {"hq_inferred": "HQ", "documented": "doc", "reported": "rep"}
_MAX_ROWS = 12
_NAME_MAX = 26  # longer provider names would run into the CTRY column
_SPECIAL = ("withheld", "unknown")


def _t(x, y, s, size, weight=400, anchor="start", fill=svg.INK, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c} x="{x:.0f}" y="{y:.0f}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}">{svg.esc(s)}</text>')


def _basis_note(payload) -> str:
    return next((h["footnote"] for h in payload.get("headlines", []) if h["kind"] == "countries"), "")


def _main_basis(p) -> str:
    by: dict = {}
    for loc in p.get("locations", []):
        by[loc["confidence"]] = by.get(loc["confidence"], 0) + loc["requests"]
    top = sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
    return _BASIS.get(top[0][0], "??") if top and p.get("country") else "??"


def _withheld(p) -> int:
    return sum(loc["requests"] for loc in p.get("locations", []) if loc["confidence"] == "withheld")


def _rows(payload) -> list[dict]:
    provs = payload.get("providers", [])
    shown, rest = (provs, []) if len(provs) <= _MAX_ROWS else (provs[:_MAX_ROWS - 1], provs[_MAX_ROWS - 1:])
    rows = []
    for p in shown:
        unk = p["id"] == "unknown"
        subs = ["—" if unk else (p["parent"] if p.get("parent_id") and p.get("parent") else "parent unknown")]
        if _withheld(p):
            subs.append(f"of which location withheld: {svg.fmt_int(_withheld(p))}")
        name = "??" if unk else p["name"]
        if len(name) > _NAME_MAX:
            name = name[:_NAME_MAX - 1] + "…"
        rows.append({"name": name, "subs": subs, "country": p.get("country"),
                     "basis": _main_basis(p), "n": p["requests"]})
    if rest:
        rows.append({"name": f"+{len(rest)} more companies", "subs": [], "country": None, "basis": None,
                     "n": sum(p["requests"] for p in rest)})
    return rows


def _count_line(label, d) -> str:
    items = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
    return f"{label}: " + " · ".join(f"{k} {svg.fmt_int(v)}" for k, v in items) if items else ""


def receipt_svg(payload) -> str:
    x0, x1 = 90, 990
    cx = (x0 + x1) / 2
    px, pr = x0 + 40, x1 - 40
    rows = _rows(payload)
    c = payload["counts"]
    total = (f"Companies that processed your prompts: {c['companies']} · Countries: {c['countries']} · "
             f"Undisclosed: {pct(payload['footprint'].get('undisclosed_share', 0))}%")
    total_lines = svg.wrap(total, 40)
    note = f"{_basis_note(payload)} HQ = location inferred from HQ, doc = documented.".strip()
    note_lines = svg.wrap(note, 92)
    tool_lines = [(cls, ln) for cls, line in (("tools", _count_line("Tools", payload.get("tools", {}))),
                                              ("access", _count_line("Access", payload.get("access", {}))))
                  if line for ln in svg.wrap(line, 66)]
    foot_lines = len(svg.wrap(svg.footnote(payload), int(968 / (15 * 0.52))))
    bottom = 1350 - 34 - (foot_lines - 1) * 20 - 30
    top = 108
    fixed = 190 + 20 + len(tool_lines) * 24 + 34 + len(total_lines) * 30 + 24 + len(note_lines) * 17 + 20
    extra = sum(20 * (len(r["subs"]) - 1) for r in rows)
    rh = max(min(62, (bottom - top - fixed - extra) / max(len(rows), 1)), 40)
    out = [f'<defs><filter id="receipt-shadow" x="-5%" y="-3%" width="110%" height="106%">'
           f'<feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#14151F" flood-opacity=".18"/>'
           f'</filter></defs>',
           f'<style>svg .rcpt text{{font-family:{_MONO}}}</style>']
    g = [f'<rect x="{x0}" y="{top}" width="{x1 - x0}" height="{bottom - top}" fill="{_PAPER}" '
         f'filter="url(#receipt-shadow)"/>']
    y = top + 56
    g.append(f'<g transform="translate({cx - 16:.0f} {y - 22})" opacity=".9"><circle cx="16" cy="16" r="13" '
             f'fill="none" stroke="{svg.INK}" stroke-width="3"/><circle cx="16" cy="16" r="5" fill="{svg.INK}"/></g>')
    y += 40
    g.append(_t(cx, y, "YOUR AI INFERENCE RECEIPT", 28, 800, "middle"))
    y += 30
    meta = f"{svg.period_label(payload)} · {payload.get('days', 0)} days · {svg.fmt_int(payload['total_requests'])} prompts"
    g.append(_t(cx, y, meta, 18, 400, "middle", _SUB))
    y += 24
    rule = f'<line x1="{px}" x2="{pr}" y1="{{y}}" y2="{{y}}" stroke="{svg.INK}" stroke-width="2" stroke-dasharray="8 6"/>'
    g.append(rule.format(y=y))
    y += 28
    g.append(_t(px, y, "SERVED BY / OWNED BY", 15, 700, fill=_SUB))
    g.append(_t(pr - 190, y, "CTRY", 15, 700, "middle", _SUB))
    g.append(_t(pr, y, "PROMPTS", 15, 700, "end", _SUB))
    y += 14
    g.append(rule.format(y=y))
    y += 12
    for r in rows:
        ry = y + 24
        g.append(_t(px, ry, r["name"], 22, 800, cls="rn"))
        for i, sub in enumerate(r["subs"]):
            g.append(_t(px, ry + 20 + i * 20, sub, 15, 400, fill=_SUB, cls="rs"))
        if r["basis"] is not None:
            code = r["country"] or "??"
            g.append(_t(pr - 190, ry, code, 22, 800, "middle", svg.color(r["country"]), "cc"))
            g.append(_t(pr - 190, ry + 16, r["basis"], 12, 400, "middle", _SUB, "basis"))
        g.append(_t(pr, ry, svg.fmt_int(r["n"]), 22, 700, "end", cls="rc"))
        y += rh + 20 * (len(r["subs"]) - 1)
    g.append(rule.format(y=y))
    y += 28
    for cls, ln in tool_lines:
        g.append(_t(px, y, ln, 17, 400, cls=cls))
        y += 24
    y += 4
    g.append(f'<line x1="{px}" x2="{pr}" y1="{y}" y2="{y}" stroke="{svg.INK}" stroke-width="2"/>'
             f'<line x1="{px}" x2="{pr}" y1="{y + 5}" y2="{y + 5}" stroke="{svg.INK}" stroke-width="2"/>')
    y += 34
    for ln in total_lines:
        g.append(_t(cx, y, ln, 22, 800, "middle", cls="total"))
        y += 30
    y += 4
    for ln in note_lines:
        g.append(_t(cx, y, ln, 13, 400, "middle", _SUB, "note"))
        y += 17
    body = "".join(out) + f'<g class="rcpt">{"".join(g)}</g>'
    return svg.card(payload, "receipt", 1080, 1350, body)


# ---------------------------------------------------------------- passport
_PX0, _PX1, _PY0, _PY1 = 56, 1024, 205, 1165
_SX0, _SX1, _SY0, _SY1 = 76, 1004, 330, 1095
_BY0, _BY1 = _PY0 + 116, _PY1 - 56  # between subtitle and bottom line
_ROT = (-8, 6, -3, 9, -6, 4, -10, 2, 7, -4)


def _passport_items(payload) -> list[dict]:
    fp = payload["footprint"]
    shares = fp.get("country_share", {})
    counts = fp.get("countries", {})
    names = payload.get("country_names", {})
    total = max(payload.get("total_requests", 0), 1)
    items = []
    for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if code in _SPECIAL or n <= 0:
            continue
        items.append({"kind": "country", "country": code, "label": names.get(code, code),
                      "share": shares.get(code, n / total), "n": n})
    und = fp.get("undisclosed_share", 0)
    if und > 0:
        items.append({"kind": "undisclosed", "country": None, "label": "??", "share": und,
                      "n": round(und * total)})
    return items


def _place(items, scale) -> list[dict] | None:
    placed = []
    cxm, cym = (_SX0 + _SX1) / 2, (_SY0 + _SY1) / 2
    for k, it in enumerate(sorted(items, key=lambda i: (-i["share"], i["kind"], str(i["country"])))):
        r = max(80, min(220, 280 * math.sqrt(it["share"]))) * scale
        if it["kind"] == "undisclosed":
            r = max(r, 100)
        best = None
        y = _SY0 + r
        while y <= _SY1 - r:
            x = _SX0 + r
            while x <= _SX1 - r:
                if all(math.hypot(x - q["x"], y - q["y"]) >= r + q["r"] + 12 for q in placed):
                    d = math.hypot(x - cxm, (y - cym) * 1.2)
                    if best is None or d < best[0]:
                        best = (d, x, y)
                x += 8
            y += 8
        if best is None:
            return None
        placed.append(dict(it, x=best[1], y=best[2], r=r, rot=_ROT[k % len(_ROT)]))
    return placed


def _centre(placed):
    """Rigidly shift the stamp group so its bounding box is centred in the page body."""
    x0 = min(q["x"] - q["r"] for q in placed)
    x1 = max(q["x"] + q["r"] for q in placed)
    y0 = min(q["y"] - q["r"] for q in placed)
    y1 = max(q["y"] + q["r"] for q in placed)
    dx = (_PX0 + _PX1) / 2 - (x0 + x1) / 2
    dy = (_BY0 + _BY1) / 2 - (y0 + y1) / 2
    dx = max(_PX0 - x0, min(_PX1 - x1, dx))
    dy = max(_BY0 - y0, min(_BY1 - y1, dy))
    return [dict(q, x=q["x"] + dx, y=q["y"] + dy) for q in placed]


def passport_layout(payload) -> list[dict]:
    """Stamp circles: kind, country, label, share, n, x, y, r, rot. Shrinks stamps until all fit."""
    items = _passport_items(payload)
    scale = 1.0
    while items:
        placed = _place(items, scale)
        if placed is not None:
            return _centre(placed)
        scale *= 0.92
    return []


def _fit(text, size, width, weight=800):
    return max(min(size, width / max(svg.text_width(text, 1, weight), 0.1)), 9)


def _name_size(name, r) -> int:
    size = math.floor(min(r * 0.2, 1.3 * r / max(svg.text_width(name, 1, 800), 0.1)))
    while size > 1 and svg.text_width(name, size, 800) > 1.3 * r:
        size -= 1
    return max(size, 1)


def _stamp(s) -> str:
    r = s["r"]
    und = s["kind"] == "undisclosed"
    col = svg.COLORS["GREY"] if und else svg.color(s["country"])
    dash = ' stroke-dasharray="14 9"' if und else ""
    pc = f"{svg.esc(pct(s['share']))}%"
    if und:
        small = f"{pc} undisclosed"
        parts = [_t(0, r * 0.22, "??", round(r * 0.62), 900, "middle", col, "stamp-undis"),
                 _t(0, r * 0.52, f"{pct(s['share'])}% undisclosed",
                    max(round(_fit(small, r * 0.2, r * 1.15, 600)), 14), 700, "middle", col)]
    else:
        name = s["label"].upper()
        parts = [_t(0, -r * 0.38, name, _name_size(name, r), 800, "middle", col, "stamp-name"),
                 f'<text x="0" y="{r * 0.2:.0f}" font-size="{round(r * 0.5)}" font-weight="900" '
                 f'text-anchor="middle" fill="{col}">{pc}</text>',
                 _t(0, r * 0.5, f"{svg.fmt_int(s['n'])} prompts", round(max(r * 0.14, 13)), 700, "middle", col)]
    return (f'<g transform="translate({s["x"]:.0f} {s["y"]:.0f}) rotate({s["rot"]})" opacity=".92">'
            f'<circle r="{r:.0f}" fill="{col}" fill-opacity=".06" stroke="{col}" stroke-width="6"{dash}/>'
            f'<circle r="{r - 14:.0f}" fill="none" stroke="{col}" stroke-width="2"{dash}/>'
            + "".join(parts) + "</g>")


def passport_svg(payload) -> str:
    lay = passport_layout(payload)
    page = (f'<rect x="{_PX0}" y="{_PY0}" width="{_PX1 - _PX0}" height="{_PY1 - _PY0}" rx="28" '
            f'fill="#F3E9D2" stroke="#D8C9A3" stroke-width="3"/>')
    guil = "".join(f'<path d="M{_PX0 + 20} {_PY0 + 60 + i * 42} Q{(_PX0 + _PX1) / 2} {_PY0 + 20 + i * 42} '
                   f'{_PX1 - 20} {_PY0 + 60 + i * 42}" fill="none" stroke="#D8C9A3" stroke-width="1" '
                   f'opacity=".6"/>' for i in range(0, 20))
    c = payload["counts"]
    head = (_t(_PX0 + 40, _PY0 + 62, "PROMPT PASSPORT", 40, 900, fill="#3a3326", cls="ptitle")
            + _t(_PX0 + 40, _PY0 + 96, f"{svg.period_label(payload)} · {svg.fmt_int(payload['total_requests'])} prompts",
                 20, 600, fill="#6b6249"))
    nc = c["countries"]
    bottom = _t(_PX0 + 40, _PY1 - 22, f"{nc} {'country' if nc == 1 else 'countries'} · "
                f"{c['companies']} {'company' if c['companies'] == 1 else 'companies'}", 26, 800, fill="#3a3326",
                cls="pbottom")
    body = page + guil + head + "".join(_stamp(s) for s in lay) + bottom
    return svg.card(payload, "passport", 1080, 1350, body, foot_extra=_basis_note(payload))


def section(payload: dict) -> str:
    if payload.get("empty") or not payload.get("total_requests"):
        return ""
    return ('<section id="receipt"><h2>Your receipt</h2>'
            + svg.figure("receipt", receipt_svg(payload))
            + svg.figure("passport", passport_svg(payload)) + "</section>")
