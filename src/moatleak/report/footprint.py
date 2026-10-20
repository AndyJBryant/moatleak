"""Footprint card (200 tiles + legend + legal regimes) and its in-report section."""
from moatleak.headlines import pct
from moatleak.report import svg

GREY = svg.COLORS["GREY"]
_SUB = "#5b5d69"
_X0, _W = 56, 968
_COLS = 5
_MAX_COUNTRIES = 8
_TS, _GAP, _GY = 38, 4, 300
_PER_ROW = 20
_GX = (1080 - (_PER_ROW * (_TS + _GAP) - _GAP)) // 2


def _categories(payload) -> list[dict]:
    by: dict = {}
    for p in payload.get("providers", []):
        for loc in p.get("locations", []):
            n = loc["requests"]
            if n <= 0:
                continue
            c, conf = loc["country"], loc["confidence"]
            if c is None:
                key = (None, "withheld" if conf == "withheld" else "unknown")
            else:
                key = (c, "hatched" if conf == "hq_inferred" else "solid")
            by[key] = by.get(key, 0) + n
    tot: dict = {}
    for (c, kind), n in by.items():
        if c is not None:
            tot[c] = tot.get(c, 0) + n
    cats = []
    for c in sorted(tot, key=lambda c: (-tot[c], c)):
        for kind in ("hatched", "solid"):
            if by.get((c, kind)):
                cats.append({"key": f"{c}-{kind}", "country": c, "kind": kind, "requests": by[(c, kind)]})
    for kind in ("withheld", "unknown"):
        if by.get((None, kind)):
            cats.append({"key": kind, "country": None, "kind": kind, "requests": by[(None, kind)]})
    return cats


def tile_counts(payload, n=200) -> list[dict]:
    cats = _categories(payload)
    total = sum(c["requests"] for c in cats)
    if not cats or total <= 0:
        return []
    quota = [c["requests"] * n / total for c in cats]
    tiles = [int(q) for q in quota]
    by_rem = sorted(range(len(cats)), key=lambda i: (-(quota[i] - tiles[i]), i))
    for i in by_rem[: n - sum(tiles)]:
        tiles[i] += 1
    for i in range(len(cats)):
        if tiles[i] == 0:
            j = max(range(len(cats)), key=lambda k: (tiles[k], -k))
            tiles[j] -= 1
            tiles[i] = 1
    return [dict(c, tiles=t) for c, t in zip(cats, tiles)]


def _pct_dec(share: float) -> str:
    if share <= 0:
        return "0%"
    if share < 0.01:
        return "<0.1%" if share < 0.001 else f"{share * 100:.1f}%"
    return f"{pct(share)}%"


def _country_rows(payload, cats) -> list[dict]:
    names = payload.get("country_names", {})
    shares = payload["footprint"].get("country_share", {})
    rows = []
    for c in dict.fromkeys(k["country"] for k in cats if k["country"]):
        h = sum(k["requests"] for k in cats if k["country"] == c and k["kind"] == "hatched")
        s = sum(k["requests"] for k in cats if k["country"] == c and k["kind"] == "solid")
        basis = "all HQ-inferred" if s == 0 else "all documented" if h == 0 else f"{svg.fmt_int(s)} documented"
        conf = "hq_inferred" if s == 0 else "documented"
        rows.append({"country": c, "label": names.get(c, c), "n": h + s, "share": shares.get(c, 0.0),
                     "pct": f"{pct(shares.get(c, 0.0))}%", "basis": basis,
                     "fill": svg.fill(c, conf, "footprint")})
    if len(rows) > _MAX_COUNTRIES:
        keep, rest = rows[: _MAX_COUNTRIES - 1], rows[_MAX_COUNTRIES - 1:]
        share = sum(r["share"] for r in rest)
        keep.append({"country": "OTHER", "label": "Other countries", "n": sum(r["n"] for r in rest),
                     "share": share, "pct": f"{pct(share)}%", "basis": f"{len(rest)} countries",
                     "fill": svg.COLORS["OTHER"]})
        rows = keep
    return rows


def _legend_items(payload, cats) -> list[dict]:
    items = [dict(r, stroke=svg.color(r["country"])) for r in _country_rows(payload, cats)]
    shares = payload["footprint"].get("country_share", {})
    for kind, label in (("unknown", "Unknown ??"), ("withheld", "Withheld")):
        n = sum(k["requests"] for k in cats if k["kind"] == kind)
        if n:
            share = shares.get(kind, n / max(payload["total_requests"], 1))
            items.append({"country": None, "label": label, "n": n, "pct": _pct_dec(share), "basis": "",
                          "fill": GREY, "stroke": GREY})
    return items


def legend_layout(payload, top: float = 0) -> list[dict]:
    """Legend boxes (x, y, w, h, col) + the text lines drawn in each: (text, size, weight)."""
    cats = tile_counts(payload)
    items = _legend_items(payload, cats)
    if not items:
        return []
    colw = min(_W / min(len(items), _COLS), 250)
    tw = colw - 42 - 8
    out, y = [], top
    for r0 in range(0, len(items), _COLS):
        row = []
        for ci, it in enumerate(items[r0: r0 + _COLS]):
            lab = svg.wrap(it["label"], max(int(tw / (19 * 0.56)), 4))
            sub = [f"{svg.fmt_int(it['n'])} prompts"] + ([it["basis"]] if it["basis"] else [])
            sub = [ln for s in sub for ln in svg.wrap(s, max(int(tw / (15 * 0.56)), 4))]
            h = 54 + (len(lab) - 1) * 22 + 21 + (len(sub) - 1) * 19 + 8
            texts = [(it["pct"], 38, 900)] + [(ln, 19, 700) for ln in lab] + [(ln, 15, 500) for ln in sub]
            row.append(dict(it, x=_X0 + ci * colw, y=y, w=colw, h=h, col=ci, lab=lab, sub=sub, texts=texts))
        y += max(b["h"] for b in row) + 14
        out.extend(row)
    return out


def _tile_xy(i):
    r, c = divmod(i, _PER_ROW)
    return _GX + c * (_TS + _GAP), _GY + r * (_TS + _GAP)


def _t(x, y, s, size, weight, anchor="start", fill=svg.INK):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}">{svg.esc(s)}</text>')


def _tiles_svg(payload, cats) -> tuple[str, float]:
    out, seq = [], []
    for c in cats:
        seq += [c] * c["tiles"]
    for i, c in enumerate(seq):
        x, y = _tile_xy(i)
        if c["country"] is None:
            f = st = GREY
        else:
            f = svg.fill(c["country"], "hq_inferred" if c["kind"] == "hatched" else "documented", "footprint")
            st = svg.color(c["country"])
        out.append(f'<rect class="tile" x="{x}" y="{y}" width="{_TS}" height="{_TS}" rx="6" fill="{f}" '
                   f'stroke="{st}" stroke-width="2.5"/>')
    gy_end = _GY + 10 * (_TS + _GAP) - _GAP
    last_row = {}
    for i, c in enumerate(seq):
        if i // _PER_ROW == 9:
            last_row[c["kind"]] = i
    ptrs = sorted(((k, last_row[k]) for k in ("withheld", "unknown") if k in last_row), key=lambda kv: kv[1])
    for rank, (kind, i) in enumerate(ptrs):  # left-most pointer gets the short line
        x, y = _tile_xy(i)
        cx = x + _TS / 2
        drop = 21 + 30 * rank
        out.append(f'<path d="M{cx:.0f},{y + _TS + 4} L{cx:.0f},{gy_end + drop}" stroke="{GREY}" stroke-width="2.5"/>')
        out.append(_t(cx - 8, gy_end + drop + 7, "?? unknown" if kind == "unknown" else "withheld",
                      20, 800, "end", _SUB))
    out.append(_t(_GX, gy_end + 32, f"1 tile = {payload['total_requests'] / 200:.1f} prompts", 19, 700,
                  "start", "#4a4b58"))
    out.append(_t(_GX, gy_end + 56, "hatched = location inferred from HQ · solid = documented or reported",
                  16, 500, "start", "#6b6d79"))
    return "".join(out), gy_end + 70


def _legend_svg(items) -> str:
    out = []
    for it in items:
        x, y = it["x"], it["y"]
        out.append(f'<g><rect x="{x:.0f}" y="{y:.0f}" width="30" height="30" rx="6" fill="{it["fill"]}" '
                   f'stroke="{it["stroke"]}" stroke-width="2.5"/>')
        out.append(_t(x + 42, y + 28, it["pct"], 38, 900))
        ly = y + 54
        for ln in it["lab"]:
            out.append(_t(x + 42, ly, ln, 19, 700, fill="#3a3b48"))
            ly += 22
        sy = ly - 1
        for ln in it["sub"]:
            out.append(_t(x + 42, sy, ln, 15, 500, fill="#6b6d79"))
            sy += 19
        out.append("</g>")
    return "".join(out)


def _regimes_differ(payload) -> bool:
    fp = payload["footprint"]
    shares = fp.get("country_share", {})
    return any(r["country"] in shares and abs(r["share"] - shares[r["country"]]) > 1e-9
               for r in fp.get("regimes", []))


def _foot_extra(payload) -> str:
    base = next((h["footnote"] for h in payload.get("headlines", []) if h["kind"] == "countries"), "")
    extra = "Regime shares include requests whose location was withheld." if _regimes_differ(payload) else ""
    return f"{base} {extra}".strip()


def _regimes_svg(payload, y, foot_top) -> str:
    regs = payload["footprint"].get("regimes", [])
    if not regs:
        return ""
    row_h = 74
    room = foot_top - y - 30
    if len(regs) <= min(4, room // row_h):
        shown = regs
    else:
        shown = regs[:max(min(4, (room - 24) // row_h), 1)]
    more = len(regs) - len(shown)
    out = [_t(_X0, y + 10, "Who can legally demand them", 28, 900)]
    y += 30
    for r in shown:
        c = svg.color(r["country"])
        out.append(f'<rect x="{_X0}" y="{y + 4}" width="6" height="62" rx="3" fill="{c}"/>')
        out.append(_t(_X0 + 26, y + 52, f"{pct(r['share'])}%", 40, 900, fill=c))
        out.append(_t(_X0 + 170, y + 20, r["name"], 20, 800))
        for i, ln in enumerate(svg.wrap(r.get("summary", ""), 88)[:2]):
            out.append(_t(_X0 + 170, y + 43 + i * 21, ln, 16, 500, fill="#4a4b58"))
        y += row_h
    if more:
        out.append(_t(_X0 + 170, y + 14, f"+{more} more regimes (listed in the report)", 17, 700, fill=_SUB))
    return "".join(out)


def footprint_svg(payload) -> str:
    cats = tile_counts(payload)
    tiles, y = _tiles_svg(payload, cats)
    items = legend_layout(payload, top=y + 14)
    legend = _legend_svg(items)
    y = max((it["y"] + it["h"] for it in items), default=y) + 14
    c = len({k["country"] for k in cats if k["country"]})
    undis = payload["footprint"].get("undisclosed_share", 0)
    big = (f'<text x="{_X0}" y="240" fill="{svg.INK}"><tspan font-size="76" font-weight="900" '
           f'letter-spacing="-2">{c}</tspan><tspan font-size="34" font-weight="800"> '
           f'{"country" if c == 1 else "countries"}</tspan>')
    if undis > 0:
        big += (f'<tspan font-size="26" font-weight="600" fill="{_SUB}"> · '
                f'{svg.esc(pct(undis))}% undisclosed</tspan>')
    big += "</text>"
    extra = _foot_extra(payload)
    n_foot = len(svg.wrap(svg.footnote(payload, extra), int((1080 - 112) / (15 * 0.52))))
    foot_top = 1350 - 34 - (n_foot - 1) * 20 - 20
    regimes = _regimes_svg(payload, y + 6, foot_top)
    return svg.card(payload, "footprint", 1080, 1350, big + tiles + legend + regimes,
                    foot_extra=extra, title="Where your prompts went")


def section(payload: dict) -> str:
    if payload.get("empty") or not payload.get("total_requests"):
        return ""
    regs = payload["footprint"].get("regimes", [])
    out = ('<section id="footprint"><h2>Where your prompts went</h2>'
           + svg.figure("footprint", footprint_svg(payload)))
    if regs:
        out += "<h3>Laws that can compel access</h3><ul>"
        for r in regs:
            link = f' <a href="{svg.esc(r["source"])}" rel="noopener">source</a>' if svg.safe_url(r.get("source")) else ""
            out += (f"<li><strong>{svg.esc(r['name'])}</strong> — {svg.esc(pct(r['share']))}% of prompts. "
                    f"{svg.esc(r.get('summary', ''))}{link}</li>")
        out += "</ul>"
    return out + "</section>"
