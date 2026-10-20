"""Growth timeline card (first-seen grid) and its animated in-report section."""
import math
from datetime import date, timedelta

from moatleak.report import svg

INK = svg.INK
_SUB = "#6b6d79"
_RED = "#C0392B"
_LX, _BANDW, _TOP = 56, 64, 280
_CX0 = 400
_MIN_ROW, _MAX_ROW, _MAX_CELL = 24, 62, 38
_NAME_MAX = 18

_CSS = ("<style>@media (prefers-reduced-motion: no-preference){#card-timeline .tl-row{"
        "animation:tlin .5s ease-out both;animation-delay:calc(var(--i)*.25s)}}"
        "@keyframes tlin{from{opacity:0;transform:translateX(-12px)}to{opacity:1}}</style>")


def _t(x, y, s, size, weight, anchor="start", fill=INK, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<text{c} x="{x:.0f}" y="{y:.0f}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill}">{svg.esc(s)}</text>')


def _columns(days) -> tuple[list[dict], bool]:
    """Daily columns, or ISO-week buckets when the period is longer than 60 days."""
    if len(days) <= 60:
        return [{"start": d, "days": [d]} for d in days], False
    cols: dict = {}
    for d in days:
        dt = date.fromisoformat(d)
        mon = (dt - timedelta(days=dt.weekday())).isoformat()
        cols.setdefault(mon, []).append(d)
    return [{"start": v[0], "days": v} for v in cols.values()], True


def _headline(payload, kind):
    return next((h for h in payload.get("headlines", []) if h.get("kind") == kind), None)


def _rows(payload) -> list[dict]:
    fs = payload["timeline"].get("first_seen", {})
    rows = [p for p in payload.get("providers", []) if fs.get(p["name"])]
    rows.sort(key=lambda p: (fs[p["name"]], -p["requests"], p["name"]))
    return rows


def _conf(p) -> str:
    locs = p.get("locations", [])
    same = [x for x in locs if x["country"] == p.get("country")]
    return (same or locs or [{"confidence": "unknown"}])[0]["confidence"]


def _big(payload, rows, first_seen) -> str:
    g = _headline(payload, "growth")
    head = (f'<text x="56" y="240" fill="{INK}"><tspan font-size="76" font-weight="900" letter-spacing="-2">'
            "{n}</tspan><tspan font-size=\"34\" font-weight=\"800\"> {w}</tspan>{small}</text>")
    if not g:
        n = payload.get("counts", {}).get("companies", len(rows))
        return head.format(n=svg.esc(n), w="companies served you", small="")
    dates = [first_seen[n] for n in g["names"] if n in first_seen]
    small = ""
    if dates:
        d = (date.fromisoformat(max(dates)) - date.fromisoformat(min(dates))).days + 1
        small = (f'<tspan font-size="26" font-weight="600" fill="{_SUB}"> in {d} day'
                 f'{"" if d == 1 else "s"}</tspan>')
    return head.format(n=svg.esc(g["value"]), w="new companies", small=small)


def _callouts(payload, y, width=968):
    """Boxes for growth + session_spread headlines: (svg, bottom y)."""
    out = []
    for kind in ("growth", "session_spread"):
        h = _headline(payload, kind)
        if not h:
            continue
        lines = svg.wrap(h["text"], int((width - 40) / (20 * 0.56)))
        foot = svg.wrap(h["footnote"], int((width - 40) / (15 * 0.52))) if kind == "session_spread" and h.get("footnote") else []
        bh = 22 + len(lines) * 26 + (len(foot) * 19 + 6 if foot else 0) + 10
        out.append((y, bh, lines, foot))
        y += bh + 12
    return out, y


def _callouts_svg(boxes) -> str:
    out = []
    for y, bh, lines, foot in boxes:
        out.append(f'<rect x="56" y="{y:.0f}" width="968" height="{bh}" rx="14" fill="#FFFFFF" '
                   f'stroke="{INK}" stroke-opacity=".12"/>')
        for i, ln in enumerate(lines):
            out.append(_t(76, y + 34 + i * 26, ln, 20, 800))
        for i, ln in enumerate(foot):
            out.append(_t(76, y + 34 + len(lines) * 26 - 4 + 6 + i * 19, ln, 15, 500, fill="#4a4b58"))
    return "".join(out)


def timeline_svg(payload) -> str:
    tl = payload["timeline"]
    days = tl.get("days", [])
    first_seen = tl.get("first_seen", {})
    data_start = tl.get("data_start") or (days[0] if days else None)
    rows = _rows(payload)
    cols, weekly = _columns(days)
    ncol = max(len(cols), 1)
    cw = min(_MAX_CELL, (1024 - _CX0) / ncol)
    header_h = 100 if weekly else 60
    ry0 = _TOP + header_h
    big = _big(payload, rows, first_seen)

    extra = " ".join(x for x in ((_headline(payload, "growth") or {}).get("footnote", ""),
                                 tl.get("footnote", "")) if x)
    n_foot = len(svg.wrap(svg.footnote(payload, extra), int(968 / (15 * 0.52))))
    foot_top = 1350 - 34 - (n_foot - 1) * 20 - 20
    dashed = data_start and any(first_seen.get(p["name"]) == data_start for p in rows)
    keys = [("Darker cell = more requests that day"),
            ("Solid outline = first day the company served you")]
    if dashed:
        keys.append(f"Dashed outline = already serving you when per-call data starts ({svg.short_date(data_start)})")
    boxes, _ = _callouts(payload, 0)
    call_h = (boxes[-1][0] + boxes[-1][1]) if boxes else 0
    avail = foot_top - ry0 - len(keys) * 24 - 16 - call_h - 24
    if not rows:
        rh, shown = _MAX_ROW, []
    else:
        rh = min(_MAX_ROW, avail / len(rows))
        shown = rows
        if rh < _MIN_ROW:
            rh = _MIN_ROW
            fit = max(int((avail - 26) // _MIN_ROW), 1)
            shown = rows[:fit]
    more = len(rows) - len(shown)
    gh = max(rh * len(shown), 230) if shown else 0
    def val(c, name):
        return sum(tl.get("daily_matrix", {}).get(d, {}).get(name, 0) for d in c["days"])

    mx = max((val(c, p["name"]) for c in cols for p in shown), default=0) or 1
    parts = []
    # header: day / week labels, month labels, month dividers
    step = max(math.ceil((18 if weekly else 22) / cw), 1)
    prev = None
    for j, c in enumerate(cols):
        x = _CX0 + j * cw
        ym = c["start"][:7]
        if ym != prev:
            dt = date.fromisoformat(c["start"])
            span = 1
            while j + span < len(cols) and cols[j + span]["start"][:7] == ym:
                span += 1
            label = svg._MONTHS[dt.month - 1]
            if j == 0 or dt.month == 1:
                if span * cw >= 100:
                    label += f" {dt.year}"
            parts.append(_t(x, ry0 - header_h + 16, label, 17, 800, fill=_SUB))
            if j:
                parts.append(f'<path d="M{x:.1f},{ry0 - header_h + 2} L{x:.1f},{ry0 - 4}" stroke="{INK}" '
                             f'stroke-opacity=".3"/>')
            prev = ym
        if j % step == 0:
            if weekly:
                parts.append(f'<text class="tl-day" transform="translate({x + cw / 2 + 5:.1f},{ry0 - 8}) rotate(-90)" '
                             f'font-size="14" font-weight="700" fill="#3a3b48">'
                             f'{svg.esc("w/c " + svg.short_date(c["start"]))}</text>')
            else:
                parts.append(_t(x + cw / 2, ry0 - 10, str(int(c["start"][-2:])), 17, 700, "middle",
                                "#3a3b48", "tl-day"))
    # coverage band
    if shown and data_start:
        bx = _CX0 - _BANDW - 6
        parts.append(f'<rect x="{bx}" y="{ry0}" width="{_BANDW}" height="{gh:.0f}" rx="8" '
                     f'fill="url(#timeline-hatch-GREY)" stroke="{svg.COLORS["GREY"]}" stroke-width="2" '
                     f'stroke-dasharray="6 5"/>')
        lab = f"no per-call provider data before {svg.short_date(data_start)}"
        lines = svg.wrap(lab, max(int(gh * 0.92 / (15 * 0.56)), 8))[:3]
        for i, ln in enumerate(lines):
            tx = bx + _BANDW / 2 + 5 + (i - (len(lines) - 1) / 2) * 17
            parts.append(f'<text class="lab" transform="translate({tx:.1f},{ry0 + gh / 2:.1f}) rotate(-90)" '
                         f'text-anchor="middle" font-size="15" font-weight="800" fill="#3a3b48" '
                         f'style="stroke-width:6px">{svg.esc(ln)}</text>')
    for i, p in enumerate(shown):
        y0 = ry0 + i * rh
        fs = first_seen[p["name"]]
        col = svg.color(p.get("country"))
        name = p["name"] if len(p["name"]) <= _NAME_MAX else p["name"][: _NAME_MAX - 1] + "…"
        early = bool(data_start and fs < data_start)
        sub = f"first seen {svg.short_date(fs)}" if early else f"{svg.fmt_int(p['requests'])} prompts"
        g = [f'<g class="tl-row" id="timeline-row-{i}" style="--i:{i}">',
             f'<circle cx="{_LX + 11}" cy="{y0 + rh / 2 - 4:.1f}" r="11" '
             f'fill="{svg.fill(p.get("country"), _conf(p), "timeline")}" stroke="{col}" stroke-width="2.5"/>',
             _t(_LX + 32, y0 + rh / 2 - 2, name, 22 if rh >= 40 else 17, 800),
             _t(_LX + 32, y0 + rh / 2 + (17 if rh >= 40 else 12), sub, 15.5 if rh >= 40 else 12, 600,
                fill=_RED if early else _SUB)]
        for j, c in enumerate(cols):
            v = val(c, p["name"])
            x = _CX0 + j * cw
            if v:
                op = 0.22 + 0.78 * math.sqrt(v / mx)
                g.append(f'<rect x="{x + 2:.1f}" y="{y0 + 3:.1f}" width="{cw - 4:.1f}" height="{rh - 6:.1f}" '
                         f'rx="6" fill="{col}" fill-opacity="{op:.2f}"/>')
            else:
                g.append(f'<rect x="{x + 2:.1f}" y="{y0 + 3:.1f}" width="{cw - 4:.1f}" height="{rh - 6:.1f}" '
                         f'rx="6" fill="{INK}" fill-opacity=".045"/>')
            if fs in c["days"]:
                dash = ' stroke-dasharray="6 4"' if fs == data_start else ""
                g.append(f'<rect class="tl-first" x="{x + .5:.1f}" y="{y0 + 1.5:.1f}" width="{cw - 1:.1f}" '
                         f'height="{rh - 3:.1f}" rx="7" fill="none" stroke="{INK}" stroke-width="3.5"{dash}/>')
        if early:
            bx = _CX0 - _BANDW - 12
            g.append(f'<path class="tl-arrow" d="M{bx},{y0 + rh / 2:.1f} h{_BANDW + 14} m-12,-9 l12,9 l-12,9" '
                     f'stroke="{_RED}" stroke-width="4" fill="none" stroke-linecap="round" '
                     f'stroke-linejoin="round"/>')
        g.append("</g>")
        parts.append("".join(g))
    y = ry0 + gh
    if more:
        parts.append(_t(_LX, y + 20, f"+{more} more companies (see the table below)", 17, 700, fill=_SUB))
        y += 26
    for k in keys:
        y += 24
        parts.append(_t(_LX, y + 6, k, 17, 600, fill=_SUB))
    boxes, _ = _callouts(payload, y + 24)
    parts.append(_callouts_svg(boxes))
    return svg.card(payload, "timeline", 1080, 1350, big + "".join(parts), foot_extra=extra,
                    title="Your network keeps growing")


def section(payload: dict) -> str:
    if payload.get("empty") or not payload.get("total_requests"):
        return ""
    return ('<section id="timeline"><h2>Your network keeps growing</h2>' + _CSS
            + svg.figure("timeline", timeline_svg(payload)) + "</section>")
