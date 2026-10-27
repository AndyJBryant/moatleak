"""Story slide cards ("Wrapped"): up to seven 1080x1350 dark-gradient SVG slides (stdlib only)."""
import re
from datetime import date

from moatleak.headlines import pct
from moatleak.report import svg

W, H = 1080, 1350
_X0, _COLW = 56, 950
_FOOT_W = 830  # keeps the footnote clear of the "i / N" index
_CHIP_H, _CHIP_GAP, _CHIP_CAP = 64, 14, 18
_TOP, _AREA_BOTTOM = 110, H - 130  # content is centred between the brand row and the index area
_NAME_MAX = 22
_WHITE = "#FFFFFF"
_SOFT = "rgba(255,255,255,.62)"
_BGS = [  # (stops, ...) ported from the approved mockup's 160deg gradients
    ("#171845", "#2b1b5a", "#4a1d5e"), ("#10243f", "#143a5e", "#1b4f6b"),
    ("#1c1830", "#32204f", "#5a2342"), ("#3a0f18", "#5e1a26", "#1c1a3d"),
    ("#0f2b2a", "#12405a", "#1c2e63"), ("#25262f", "#3a3b46", "#202233"),
    ("#141530", "#1d2252", "#2b1b5a")]
_STOP_AT = (0, 60, 100)
_STOP_AT_MID = (0, 70, 100)
_ACCENT = ["#8fd0ff", "#ffd84d", "#ff9ab0", "#ffffff", "#6cf0c2", "#cfd0d8", "#ffffff"]
_GREY = svg.COLORS["GREY"]


def _t(x, y, s, size, weight=600, fill=_WHITE, anchor="start", extra=""):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}"{extra}>{svg.esc(s)}</text>')


def _trunc(name: str) -> str:
    return name if len(name) <= _NAME_MAX else name[:_NAME_MAX - 1] + "…"


def _headline(payload, kind):
    return next((h for h in payload.get("headlines", []) if h.get("kind") == kind), None)


def _bg(cid, i):
    stops = _BGS[i % len(_BGS)]
    at = _STOP_AT if i % 2 == 0 else _STOP_AT_MID
    g = "".join(f'<stop offset="{o}%" stop-color="{c}"/>' for o, c in zip(at, stops))
    return (f"url(#{cid}-bg)",
            f'<linearGradient id="{cid}-bg" x1="0.17" y1="0" x2="0.83" y2="1">{g}</linearGradient>')


def _conf(p) -> str:
    locs = p.get("locations", [])
    same = [x for x in locs if x["country"] == p.get("country")]
    return (same or locs or [{"confidence": "unknown"}])[0]["confidence"]


def _foot_lines(payload, extra) -> int:
    return len(svg.wrap(svg.footnote(payload, extra), int(_FOOT_W / (15 * 0.52))))


def _limit(payload, extra) -> float:
    """Lowest y content may reach (above the footnote block)."""
    avail = min(_AREA_BOTTOM, H - 34 - (_foot_lines(payload, extra) - 1) * 20 - 15 - 24) - _TOP
    return 250 + avail  # layouts start at y~250, so this bounds the block height by `avail`


def _wrap_balanced(text, max_chars):
    """svg.wrap, re-wrapped narrower while the last line is a single word (and more than one line)."""
    lines = svg.wrap(text, max_chars)
    while len(lines) > 1 and len(lines[-1].split()) <= 1 and max_chars > 8:
        max_chars -= 1
        lines = svg.wrap(text, max_chars)
    return lines


def _big(pre, num, post, accent):
    """Template: pre line(s), huge number, post line. Returns (svg, next y)."""
    out, y = [], 300
    for i, line in enumerate(_wrap_balanced(pre, int(_COLW / (52 * 0.56)))):
        out.append(_t(_X0, y + i * 62, line, 52, 700, "rgba(255,255,255,.88)"))
        last = y + i * 62
    size = int(min(300, _COLW / (max(len(num), 1) * 0.6)))
    ny = last + 30 + int(size * 0.78)
    out.append(_t(_X0 - 6, ny, num, size, 900, accent, extra=' letter-spacing="-6"'))
    py = ny + 90
    out.append(_t(_X0, py, post, 72, 800))
    return "".join(out), py + 40


_Y_ATTR = re.compile(r'(<(?:text|rect|circle)\b[^>]*?\b)(c?y)="(-?[\d.]+)"')


def _bounds(b):
    """Vertical extent (top, bottom) of the drawn elements in an SVG fragment."""
    top, bot = [], []
    for m in re.finditer(r'<(text|rect)\b[^>]*>', b):
        tag = m.group(0)
        y = float(re.search(r'\by="(-?[\d.]+)"', tag).group(1))
        if m.group(1) == "text":
            size = float(re.search(r'font-size="([\d.]+)"', tag).group(1))
            top.append(y - 0.8 * size)
            bot.append(y + 0.25 * size)
        else:
            top.append(y)
            bot.append(y + float(re.search(r'height="([\d.]+)"', tag).group(1)))
    return min(top), max(bot)


def _centre(b, limit):
    """Shift the block so it is centred between the brand row and the footnote/index area,
    but never so far down that it passes `limit` (the lowest y content may reach)."""
    top, bot = _bounds(b)
    dy = min((_TOP + _AREA_BOTTOM) / 2 - (top + bot) / 2, limit - bot)
    dy = max(dy, 0)  # overflowing content starts at its normal top, never shifted up into the header
    return _Y_ATTR.sub(lambda m: f'{m.group(1)}{m.group(2)}="{float(m.group(3)) + dy:.1f}"', b)


def _chip(x, y, label, width, dot, stroke, sub=None):
    parts = [f'<rect class="chip" x="{x:.0f}" y="{y:.0f}" width="{width:.0f}" height="{_CHIP_H}" rx="32" '
             f'fill="rgba(255,255,255,.08)" stroke="{stroke}" stroke-width="3"/>']
    tx = x + 20
    if dot:
        parts.append(f'<circle cx="{x + 34:.0f}" cy="{y + 32:.0f}" r="12" fill="{dot}"/>')
        tx = x + 58
    parts.append(_t(tx, y + 42, label, 30, 700))
    if sub:
        parts.append(_t(tx + svg.text_width(label, 30, 700) + 10, y + 42, sub, 24, 500, _SOFT))
    return "".join(parts)


def _chip_w(label, dot, sub=None) -> float:
    w = 40 + (38 if dot else 0) + svg.text_width(label, 30, 700)
    return w + (10 + svg.text_width(sub, 24, 500) if sub else 0)


def _flow(items, y0, limit, cid):
    """items: (label, dot|None, stroke, sub|None). Left-to-right, wrapping in a 950 px column.
    Caps at 18 chips, then '+k more'; drops further chips until everything fits above `limit`."""
    n = min(len(items), _CHIP_CAP)
    while True:
        shown = list(items[:n])
        if n < len(items):
            shown.append((f"+{len(items) - n} more", None, "rgba(255,255,255,.45)", None))
        x, y, out = _X0, y0, []
        for label, dot, stroke, sub in shown:
            w = _chip_w(label, dot, sub)
            if x > _X0 and x + w > _X0 + _COLW:
                x, y = _X0, y + _CHIP_H + _CHIP_GAP
            out.append(_chip(x, y, label, w, dot, stroke, sub))
            x += w + _CHIP_GAP
        bottom = y + _CHIP_H
        if bottom <= limit or n <= 0:
            return "".join(out), bottom
        n -= 1


def _prov_chip(p, cid, sub=None):
    if p.get("id") == "unknown" or p.get("country") is None:
        label, dot, stroke = ("??" if p.get("id") == "unknown" else _trunc(p["name"])), _GREY, _GREY
    else:
        label, dot = _trunc(p["name"]), svg.fill(p["country"], _conf(p), cid)
        stroke = svg.color(p["country"])
    return (label, dot, stroke, sub)


def _s_volume(payload):
    d = payload.get("days") or 0
    pre = f"In {d} day{'' if d == 1 else 's'} you sent"
    e = payload.get("earlier") or {}

    def body(cid, _p):
        b, y = _big(pre, svg.fmt_int(payload["total_requests"]), "prompts to AI.", _ACCENT[0])
        if e.get("requests", 0) > 0 and e.get("first"):
            small = (f"Plus {svg.fmt_int(e['requests'])} earlier prompts since {svg.short_date(e['first'])}; "
                     f"for {svg.fmt_int(e.get('unattributed_requests', 0))} of them the serving company "
                     "wasn't recorded.")
            b += "".join(_t(_X0, y + 20 + i * 36, ln, 26, 500, _SOFT)
                         for i, ln in enumerate(svg.wrap(small, int(_COLW / (26 * 0.53)))))
        return b, "", payload
    return "volume", body


def _s_companies(payload):
    n = payload["counts"]["companies"]
    extent = _headline(payload, "extent")
    extra = (extent or {}).get("footnote", "")

    def body(cid, p):
        b, y = _big("They were processed by", svg.fmt_int(n), "company." if n == 1 else "companies.",
                    _ACCENT[1])
        provs = sorted(payload.get("providers", []), key=lambda q: -q["requests"])
        chips, _ = _flow([_prov_chip(q, cid) for q in provs], y, _limit(payload, extra), cid)
        return b + chips, extra, payload
    return "extent", body


def _parents(payload):
    nodes = [n for n in payload["network"]["nodes"] if n["layer"] == "parent"]
    return sorted(nodes, key=lambda n: (-n["requests"], n["label"]))


def _s_groups(payload):
    counts = payload["counts"]
    if not counts.get("parent_groups"):
        return None
    extent = _headline(payload, "extent")
    extra = (extent or {}).get("footnote", "")
    unknown = [q["name"] for q in payload["providers"]
               if q.get("parent_id") is None and q.get("id") != "unknown"]
    c = counts.get("countries", 0)

    def body(cid, p):
        post = f"groups, in {c} countr{'y' if c == 1 else 'ies'}."
        if counts["parent_groups"] == 1:
            post = post.replace("groups", "group", 1)
        b, y = _big("Owned by", svg.fmt_int(counts["parent_groups"]), post, _ACCENT[2])
        small = []
        if unknown:
            k = len(unknown)
            small = svg.wrap(f"Parent group unknown for {'1 company' if k == 1 else f'{k} companies'}: "
                             f"{', '.join(unknown)}.", int(_COLW / (24 * 0.53)))
        names = payload.get("country_names", {})
        codes = []
        for n in _parents(payload):
            if n.get("country") and n["country"] not in codes:
                codes.append(n["country"])
        badge_rows, bx, by, badges = 1, _X0, 0, []
        for code in codes:
            lab = names.get(code, code)
            w = 40 + svg.text_width(lab, 24, 700)
            if bx > _X0 and bx + w > _X0 + _COLW:
                bx, by, badge_rows = _X0, by + 54, badge_rows + 1
            badges.append((bx, by, lab, w, code))
            bx += w + 12
        badge_h = (by + 44 + 20) if badges else 0
        small_h = len(small) * 32 + 12
        limit = _limit(payload, extra) - badge_h - small_h
        chips = []
        for nd in _parents(payload):
            col = svg.color(nd.get("country"))
            chips.append((_trunc(nd["label"]), col, col, None))
        out, bottom = _flow(chips, y, limit, cid)
        b += out
        by0 = bottom + 24
        for bx, by, lab, w, code in badges:
            b += (f'<rect class="badge" x="{bx:.0f}" y="{by0 + by:.0f}" width="{w:.0f}" height="44" rx="22" '
                  f'fill="{svg.color(code)}"/>'
                  + _t(bx + 20, by0 + by + 30, lab, 24, 700, svg.INK if svg.country_key(code) == "EU" else _WHITE))
        sy = by0 + (by + 44 + 36 if badges else 12)
        b += "".join(_t(_X0, sy + i * 32, ln, 24, 500, _SOFT) for i, ln in enumerate(small))
        return b, extra, payload
    return "extent", body


def _s_punch(payload):
    h = _headline(payload, "countries")
    if not h:
        return None
    fp = payload["footprint"]
    share = fp.get("country_share", {})
    inv = {v: k for k, v in payload.get("country_names", {}).items()}
    top = [(inv[n], n) for n in h["names"][:3] if n in inv and inv[n] in share]
    if not top:
        return None

    def body(cid, p):
        out, k = [], len(top)
        cw = _COLW / k
        size = int(min(210, (cw - 20) / 1.9))
        for i, (code, name) in enumerate(top):
            x = _X0 + i * cw
            out.append(_t(x, 400, f"{pct(share[code])}%", size, 900, svg.color(code), extra=' letter-spacing="-4"'))
            out.append(_t(x, 450, name, 30, 700, "rgba(255,255,255,.88)"))
        segs = sorted(((c, s) for c, s in share.items() if c not in ("withheld", "unknown") and s > 0),
                      key=lambda kv: (-kv[1], kv[0]))
        segs.append(("grey", fp.get("undisclosed_share", 0)))
        x, y = _X0, 520
        out.append(f'<clipPath id="{cid}-barclip"><rect x="{_X0}" y="{y}" width="{_COLW}" height="40" rx="20"/></clipPath>'
                   f'<g clip-path="url(#{cid}-barclip)"><rect x="{_X0}" y="{y}" width="{_COLW}" height="40" '
                   f'fill="rgba(255,255,255,.1)"/>')
        for code, s in segs:
            if s <= 0:
                continue
            w = _COLW * s
            out.append(f'<rect class="seg" x="{x:.1f}" y="{y}" width="{w:.1f}" height="40" '
                       f'fill="{_GREY if code == "grey" else svg.color(code)}"/>')
            x += w
        out.append("</g>")
        if fp.get("undisclosed_share", 0) > 0:
            out.append(_t(_X0, y + 76, "Grey: location undisclosed", 22, 500, _SOFT))
        for i, ln in enumerate(svg.wrap(h["text"], int(_COLW / (44 * 0.56)))):
            out.append(_t(_X0, y + 150 + i * 56, ln, 44, 700))
        return "".join(out), h.get("footnote", ""), payload
    return "countries", body


def _days_span(dates):
    return (date.fromisoformat(max(dates)) - date.fromisoformat(min(dates))).days + 1


def _s_growth(payload):
    g = _headline(payload, "growth")
    if not g:
        return None
    fs = payload.get("timeline", {}).get("first_seen", {})
    names = [n for n in g["names"] if fs.get(n)]
    if not names:
        return None
    d = _days_span([fs[n] for n in names])
    by = {q["name"]: q for q in payload["providers"]}

    def body(cid, p):
        b, y = _big(f"{g['value']} new companies joined your network in", str(d),
                    "day." if d == 1 else "days.", _ACCENT[4])
        items = [_prov_chip(by[n], cid, svg.short_date(fs[n])) if n in by
                 else (_trunc(n), _GREY, _GREY, svg.short_date(fs[n])) for n in names]
        out, _ = _flow(items, y, _limit(payload, g.get("footnote", "")), cid)
        return b + out, g.get("footnote", ""), payload
    return "growth", body


def _s_withheld(payload):
    h = _headline(payload, "withheld")
    if not h:
        return None
    name = h["names"][0] if h["names"] else ""
    w = next((x for x in payload.get("withheld", []) if x["provider"] == name), None)

    def body(cid, p):
        b, y = _big(f"{name} withheld the location of", svg.fmt_int(h["value"]),
                    "of your prompts.", _ACCENT[5])
        for i in range(24):
            b += (f'<rect x="{_X0 + (i % 12) * 78}" y="{y + 10 + (i // 12) * 78}" width="64" height="64" '
                  f'rx="10" fill="{_GREY}" fill-opacity=".55"/>')
        sy = y + 10 + 2 * 78 + 30
        if w:
            small = (f"{', '.join(w['tools'])}, {svg.short_date(w['first'])} to "
                     f"{svg.short_date(w['last'])} {w['last'][:4]}: "
                     "the provider reported the location as not available.")
            b += "".join(_t(_X0, sy + i * 34, ln, 26, 500, _SOFT)
                         for i, ln in enumerate(svg.wrap(small, int(_COLW / (26 * 0.53)))))
        pl = dict(payload)
        if w:
            pl["period"] = [w["first"], w["last"]]
        return b, "", pl
    return "withheld", body


def _s_regimes(payload):
    regs = payload.get("footprint", {}).get("regimes", [])
    if not regs:
        return None

    def body(cid, p):
        out = []
        ty = 280
        for i, ln in enumerate(svg.wrap("Who can legally demand them", 28)):
            out.append(_t(_X0, ty + i * 66, ln, 56, 900))
            last = ty + i * 66
        y = last + 70
        for r in regs[:5]:
            c = svg.color(r.get("country"))
            name = r["name"] if len(r["name"]) <= 40 else r["name"][:39] + "…"
            out.append(_t(_X0, y, name, 30, 700))
            out.append(_t(_X0 + _COLW, y, f"{pct(r['share'])}%", 40, 900, c, anchor="end"))
            out.append(f'<rect x="{_X0}" y="{y + 16}" width="{_COLW}" height="10" rx="5" '
                       f'fill="rgba(255,255,255,.12)"/>'
                       f'<rect x="{_X0}" y="{y + 16}" width="{max(_COLW * r["share"], 4):.1f}" height="10" '
                       f'rx="5" fill="{c}"/>')
            y += 90
        if len(regs) > 5:
            out.append(_t(_X0, y, f"+{len(regs) - 5} more", 26, 600, _SOFT))
            y += 50
        return "".join(out), "", payload
    return "regimes", body


_CONTENT_BG = 2  # index into _BGS used for the content slide's background
_PRIORITY = ("credential", "financial", "personal_data", "infrastructure")


def _s_content(payload):
    c = payload.get("content")
    cls = [x for x in (c or {}).get("classes", []) if x.get("conversations", 0) > 0]
    if not cls:
        return None
    rank = {k: i for i, k in enumerate(_PRIORITY)}
    pick = min(enumerate(cls), key=lambda t: (rank.get(t[1]["category"], len(_PRIORITY)), t[0]))[1]
    n, comps = pick["conversations"], pick.get("companies", [])
    names = payload.get("country_names", {})
    codes = []
    for x in comps:
        if x.get("country") and x["country"] not in codes:
            codes.append(x["country"])
    unknown = any(not x.get("country") for x in comps)
    k = len(comps)
    who = f"{k} compan{'y' if k == 1 else 'ies'}"
    cn = [names.get(x, x) for x in codes]
    if len(cn) > 3:  # keep the block clear of the footer
        shown = ", ".join(cn[:3]) + f" and {len(cn) - 3} more"
    else:
        shown = ", ".join(cn)
    if codes:
        sub = f"These conversations were handled by {who} in {len(codes)} countr{'y' if len(codes) == 1 else 'ies'}: " \
              + shown + (", plus an undisclosed location." if unknown else ".")
    else:
        sub = f"These conversations were handled by {who} in an undisclosed location."
    extra = "Local regex scan; no prompt text stored or sent."
    note = f"{pick['label']} identified using basic heuristics; nothing was stored or sent by moatleak."

    def body(cid, _p):
        out = [_t(_X0, 300, "In this period,", 52, 700, "rgba(255,255,255,.88)")]
        size = int(min(300, _COLW / (max(len(svg.fmt_int(n)), 1) * 0.6)))
        ny = 330 + int(size * 0.78)
        out.append(_t(_X0 - 6, ny, svg.fmt_int(n), size, 900, _ACCENT[2], extra=' letter-spacing="-6"'))
        y = ny + 90
        lines = _wrap_balanced(f"of your conversations contained {pick['label'].lower()}.", int(_COLW / (56 * 0.56)))
        for i, ln in enumerate(lines):
            out.append(_t(_X0, y + i * 66, ln, 56, 800))
        y += len(lines) * 66 + 20
        note_lines = svg.wrap(note, int(_COLW / (32 * 0.53)))
        for i, ln in enumerate(note_lines):
            out.append(_t(_X0, y + 10 + i * 40, ln, 30, 600, "rgba(255,255,255,.88)"))
        y += 10 + len(note_lines) * 40 + 20
        for i, ln in enumerate(svg.wrap(sub, int(_COLW / (32 * 0.53)))):
            out.append(_t(_X0, y + i * 42, ln, 32, 500, _SOFT))
        return "".join(out), extra, payload
    return "content", body


def slides(payload) -> list[tuple[str, str]]:
    if payload.get("empty") or not payload.get("total_requests"):
        return []
    full = [_s_volume, _s_companies, _s_groups, _s_punch, _s_growth, _s_withheld, _s_regimes]
    chosen = [(idx, b) for idx, b in ((i, f(payload)) for i, f in enumerate(full)) if b]
    cb = _s_content(payload)
    if cb:  # before the regimes slide (which stays last)
        at = len(chosen) - 1 if chosen and chosen[-1][1][0] == "regimes" else len(chosen)
        chosen.insert(at, (_CONTENT_BG, cb))  # hard-coded background index
    n = len(chosen)
    out = []
    num = 0
    for i, (bg_idx, (kind, body)) in enumerate(chosen, 1):
        if kind == "content":
            cid = "story-content"
        else:
            num += 1
            cid = f"story-{num}"
        b, extra, pl = body(cid, payload)
        b = _centre(b, _limit(pl, extra))
        b += _t(W - _X0, H - 34, f"{i} / {n}", 24, 700, _SOFT, "end")
        svg_str = svg.card(pl, cid, W, H, b, foot_extra=extra, dark=True, foot_w=_FOOT_W,
                           background=_bg(cid, bg_idx))
        svg_str = svg_str.replace(' class="card-svg"', f' class="card-svg" data-headline="{kind}"', 1)
        out.append((cid, svg_str))
    return out


def section(payload: dict) -> str:
    cards = slides(payload)
    if not cards:
        return ""
    return ('<section id="story"><h2>Your AI footprint, slide by slide</h2>'
            + "".join(svg.figure(cid, s) for cid, s in cards) + "</section>")
