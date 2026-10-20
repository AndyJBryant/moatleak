"""Share-card hero, variant B: one circle per country, providers orbiting it (stdlib only)."""
import math

from moatleak.headlines import pct
from moatleak.report import svg
from moatleak.report.network import (
    GREY_TXT, _curve, _foot_extra, _pol, _rect_area, _rect_circle, _title, title_svg)

CARD, CARD_WIDE = "hero", "hero-wide"
GREY = svg.COLORS["GREY"]
_SLOTS = (-50, 50, -130, 130, 0, -90, 90, 180)  # degrees from "up", around the largest cluster
_MAX_COUNTRIES = 4
_ATTEMPTS = tuple((sc, extra, zig, var)
                  for var in ((1.0, 0), (0.8, 0), (0.8, 1), (0.65, 2), (1.0, 3))
                  for sc in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.42, 0.35)
                  for extra in (0, 18, 36) for zig in (0, 26))


def _trunc(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def _spec(wide):
    if wide:
        return {"w": 1200, "h": 630, "max_named": 6, "sub": False, "fs": 17, "fs_sub": 0,
                "rmin": 36, "rmax": 72, "nmax": 24}
    return {"w": 1080, "h": 1350, "max_named": 8, "sub": True, "fs": 22, "fs_sub": 16,
            "rmin": 60, "rmax": 120, "nmax": 34}


def _clusters(payload, sp):
    fp, total = payload["footprint"], payload["total_requests"] or 1
    groups: dict = {}
    for p in payload["providers"]:
        groups.setdefault(p["country"], []).append(p)
    cs = []
    keys = {c for c in groups if c is not None}
    if None in groups or (fp.get("undisclosed_share") or 0) > 0:
        keys.add(None)
    for c in keys:
        provs = groups.get(c, [])
        req = sum(p["requests"] for p in provs)
        share = fp.get("undisclosed_share") if c is None else fp["country_share"].get(c)
        if share is None:
            share = req / total
        if c is None:
            req = max(req, fp["countries"].get("unknown", 0) + fp["countries"].get("withheld", 0))
        else:
            req = max(req, fp["countries"].get(c, 0))
        named = provs[: sp["max_named"]]
        cs.append({"c": c, "share": share, "req": req, "named": named, "provs": provs,
                   "more": len(provs) - len(named), "col": svg.color(c), "other": False})
    real = sorted((k for k in cs if k["c"] is not None), key=lambda k: (-k["req"], k["c"]))
    if len(real) > _MAX_COUNTRIES:
        rest = real[_MAX_COUNTRIES:]
        provs = [p for k in rest for p in k["provs"]]
        named = provs[: sp["max_named"]]
        merged = {"c": "OTHER-GROUP", "share": sum(k["share"] for k in rest),
                  "req": sum(k["req"] for k in rest), "named": named, "provs": provs,
                  "more": len(provs) - len(named), "col": svg.COLORS["OTHER"], "other": True}
        cs = [k for k in cs if k["c"] is None or k in real[:_MAX_COUNTRIES]] + [merged]
    cs.sort(key=lambda k: (-k["share"], k["c"] is None, k["c"] or ""))
    return cs


def _build(payload, wide=False):
    sp = _spec(wide)
    w, h, fs, fsub = sp["w"], sp["h"], sp["fs"], sp["fs_sub"]
    note = svg.footnote(payload, _foot_extra(payload))
    if wide:
        tsize, tlines = _title(payload, 612, (44, 40, 36), 6)
        flines = len(svg.wrap(note, int(500 / (15 * 0.52))))
        top, bottom, bx0 = 90.0, h - 20.0, 560.0
        area = (bx0 + 20, top + 10, w - 30, bottom - 10)
        you = None
    else:
        tsize, tlines = _title(payload, w)
        flines = len(svg.wrap(note, int((w - 112) / (15 * 0.52))))
        top = 150 + (len(tlines) - 1) * tsize * 1.08 + 14 + 14
        bottom = h - 34 - (flines - 1) * 20 - 15 - 10
        bx0 = 40.0
        you = (w / 2, bottom - 54)
        area = (40.0, top + 10, w - 40.0, you[1] - 80)
    title_y0 = 140 if wide else 150
    clusters = _clusters(payload, sp)
    allp = payload["providers"]
    maxreq = max((p["requests"] for p in allp), default=1) or 1
    best = None
    for sc, extra, zig, var in _ATTEMPTS:
        g = _layout_try(payload, sp, clusters, area, you, (top, bottom, bx0), maxreq, sc, extra, zig, var)
        g["cstate"] = [(k["id"], k["r"], k["xy"]) for k in clusters]
        if best is None or g["fail"] < best["fail"]:
            best = g
        if g["fail"] == 0:
            break
    for k, (kid, kr, kxy) in zip(clusters, best["cstate"]):
        k["id"], k["r"], k["xy"] = kid, kr, kxy
    best.update({"w": w, "h": h, "wide": wide, "tsize": tsize, "tlines": tlines,
                 "title_y0": title_y0, "note": note, "you": you, "clusters": clusters,
                 "foot_w": 500 if wide else None})
    return best


def _layout_try(payload, sp, clusters, area, you, bounds, maxreq, sc, extra, zig, var=(1.0, 0)):
    w, h, fs, fsub = sp["w"], sp["h"], sp["fs"], sp["fs_sub"]
    top, bottom, bx0 = bounds
    ax0, ay0, ax1, ay1 = area
    smax = max((c["share"] for c in clusters), default=1) or 1
    tall = you is not None
    mid = ((ax0 + ax1) / 2, ay0 + (0.66 if tall else 0.60) * (ay1 - ay0))
    rx, ry = 0.34 * (ax1 - ax0), (0.76 if tall else 0.46) * (ay1 - ay0) * var[0]
    pos, rad, ang, halo, cinfo = {}, {}, {}, {}, []
    for i, k in enumerate(clusters):
        r = min(sp["rmax"], max(sp["rmin"], sp["rmax"] * math.sqrt(k["share"] / smax))) * (1 + sc) / 2
        if i == 0:
            x, y = mid
        else:
            a = _SLOTS[(i - 1 + var[1]) % len(_SLOTS)]
            f = 1 + 0.25 * ((i - 1 + var[1]) // len(_SLOTS))
            x, y = _pol(mid[0], mid[1], 1, a)
            x, y = mid[0] + (x - mid[0]) * rx * f, mid[1] + (y - mid[1]) * ry * f
        if k["c"] is None:
            r = max(r, 50.0 if sp["w"] < sp["h"] else 48.0)
        x = min(max(x, ax0 + r), ax1 - r)
        y = min(max(y, ay0 + r), ay1 - r)
        cid = f"country:{k['c'] or 'unknown'}"
        pos[cid], rad[cid] = (x, y), r
        k["id"], k["r"], k["xy"] = cid, r, (x, y)
    nodes = []  # (id, cluster, x, y, nr, label, sub, kind, req)
    for k in clusters:
        cx, cy = k["xy"]
        slots = list(k["named"]) + ([None] if k["more"] > 0 else [])
        n = len(slots)
        gap_dir = (math.degrees(math.atan2(you[0] - cx, -(you[1] - cy))) if you else 180.0)
        gap = 70.0
        for i, p in enumerate(slots):
            a = (gap_dir + gap / 2 + (i + 0.5) * (360 - gap) / n) % 360
            if p is None:
                nid, nr, name, sub, kind = f"more:{k['c'] or 'unknown'}", 9.0, f"+{k['more']} more", None, "more"
                req = 0
            else:
                nid = f"provider:{p['id']}"
                nr = max(9.0, sp["nmax"] * sc * math.sqrt(p["requests"] / maxreq))
                name = _trunc(p["name"], 22)
                sub = None
                if sp["sub"] and k["other"]:
                    if p["country"] not in (None, "", "withheld", "unknown"):
                        sub = _trunc(payload["country_names"].get(p["country"], p["country"]), 26)
                elif sp["sub"] and p["id"] != "unknown":
                    if p["parent_id"] is None:
                        sub = "parent unknown"
                    elif not p["parent_same_name"]:
                        sub = _trunc(p["parent"] or "", 26)
                kind, req = "provider", p["requests"]
            R = k["r"] + nr + 22 + extra + (zig if i % 2 else 0)
            x, y = _pol(cx, cy, R, a)
            pos[nid], rad[nid], ang[nid], halo[nid] = (x, y), nr, a, nr + 8
            nodes.append({"id": nid, "k": k, "p": p, "name": name, "sub": sub, "kind": kind, "req": req})
    # --- nodes must not touch each other, foreign clusters, or leave the canvas
    bad = 0
    for i, n in enumerate(nodes):
        (x, y), hr = pos[n["id"]], halo[n["id"]]
        if x - hr < ax0 - 30 or x + hr > w - 10 or y - hr < top or y + hr > bottom:
            bad += 1
        for m in nodes[i + 1:]:
            (x2, y2), h2 = pos[m["id"]], halo[m["id"]]
            if math.hypot(x - x2, y - y2) < hr + h2 + 4:
                bad += 1
        for k in clusters:
            if k is not n["k"] and math.hypot(x - k["xy"][0], y - k["xy"][1]) < hr + k["r"] + 6:
                bad += 1
        if you and math.hypot(x - you[0], y - you[1]) < hr + 60:
            bad += 1
    # --- labels: largest nodes first, each hugging its own node on the outward side
    labels, placed, fail = [], [], bad
    discs = [(pos[k["id"]], rad[k["id"]] + 5, k["id"]) for k in clusters]
    if you:
        discs.append((you, 58, "you"))
    discs += [(pos[n["id"]], halo[n["id"]] + 2, n["id"]) for n in nodes]
    order = sorted(nodes, key=lambda n: (-rad[n["id"]], n["id"]))
    for n in order:
        nid = n["id"]
        x0, y0 = pos[nid]
        size = fs if n["kind"] == "provider" else fs - 3
        weight = 800 if n["kind"] == "provider" else 700
        lw = svg.text_width(n["name"], size, weight)
        lh = size * 1.2
        if n["sub"]:
            lw = max(lw, svg.text_width(n["sub"], fsub, 600))
            lh += fsub * 1.25
        base = ang[nid]
        cands = []
        for da in (0, 25, -25, 50, -50, 80, -80, 110, -110, 150, -150, 180):
            t = math.radians(base + da)
            ex, ey = math.sin(t), -math.cos(t)
            for o in (0, 8, 16):
                d0 = halo[nid] + 6 + o
                ax, ay = x0 + ex * d0, y0 + ey * d0
                if abs(ex) < 0.35:
                    bx, anc = ax - lw / 2, "middle"
                    by = ay - lh if ey < 0 else ay
                else:
                    bx = ax if ex > 0 else ax - lw
                    anc = "start" if ex > 0 else "end"
                    by = ay - lh / 2 + ey * lh / 2
                cands.append((bx, by, lw, lh, anc))
        chosen, score = None, None
        for b in cands:
            if b[0] < bx0 or b[0] + lw > w - 40 or b[1] < top or b[1] + lh > bottom:
                continue
            nx = min(max(x0, b[0]), b[0] + lw)
            ny = min(max(y0, b[1]), b[1] + lh)
            if math.hypot(nx - x0, ny - y0) - rad[nid] > 40:
                continue
            over = sum(_rect_area(b, q) for q in placed)
            clash = any(_rect_circle(b, *c, r_) for c, r_, k_ in discs if k_ != nid) or \
                _rect_circle(b, x0, y0, halo[nid] + 2)
            if not over and not clash:
                chosen, score = b, 0
                break
            sc_ = over + (1e6 if clash else 0)
            if score is None or sc_ < score:
                chosen, score = b, sc_
        if chosen is None or score:
            fail += 1
        if chosen is None:
            chosen = cands[0]
        placed.append(chosen[:4])
        labels.append({"id": nid, "text": n["name"], "sub": n["sub"], "x": round(chosen[0], 1),
                       "y": round(chosen[1], 1), "w": round(lw, 1), "h": round(lh, 1),
                       "size": size, "weight": weight, "anchor": chosen[4], "kind": n["kind"]})
    return {"pos": pos, "rad": rad, "halo": halo, "nodes": nodes, "labels": labels, "fail": fail,
            "ang": ang, "sc": sc}


def _quad(p, q, bend, n=30):
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    cx, cy = mx - (q[1] - p[1]) * bend, my + (q[0] - p[0]) * bend
    return [((1 - t) ** 2 * p[0] + 2 * t * (1 - t) * cx + t * t * q[0],
             (1 - t) ** 2 * p[1] + 2 * t * (1 - t) * cy + t * t * q[1])
            for t in (i / n for i in range(n + 1))]


def _you_curves(g):
    """(from You, to cluster bottom, bend) per cluster: bent outward, clear of foreign provider nodes."""
    you, out = g["you"], []
    for k in g["clusters"]:
        cx, cy = k["xy"]
        q = (cx, cy + k["r"])
        side = -1 if cx < you[0] - 20 else (1 if cx > you[0] + 20 else 0)
        best = None
        for b in ((0.0,) if not side else tuple(side * m for m in (0.12, 0.2, 0.3, 0.4, 0.5, 0.6))):
            pts = _quad(you, q, b)
            hit = sum(1 for n in g["nodes"] if n["k"] is not k
                      for (x, y) in pts if math.hypot(x - g["pos"][n["id"]][0], y - g["pos"][n["id"]][1])
                      < g["halo"][n["id"]] + 6)
            hit += sum(1 for lb in g["labels"] for (x, y) in pts
                       if lb["x"] - 4 < x < lb["x"] + lb["w"] + 4 and lb["y"] - 4 < y < lb["y"] + lb["h"] + 4)
            if best is None or hit < best[0]:
                best = (hit, b)
            if not hit:
                break
        out.append((you, q, best[1]))
    return out


def clusters_layout(payload, w, h) -> dict:
    g = _build(payload, wide=w > h)
    nid = [k["id"] for k in g["clusters"]] + [n["id"] for n in g["nodes"]] + (["you"] if g["you"] else [])
    pos, rad = dict(g["pos"]), dict(g["rad"])
    if g["you"]:
        pos["you"], rad["you"] = g["you"], 52
    return {"nodes": [{"id": k, "x": round(pos[k][0], 1), "y": round(pos[k][1], 1),
                       "r": round(rad[k], 1)} for k in nid],
            "labels": [{k: lab[k] for k in ("id", "text", "sub", "x", "y", "w", "h", "kind")}
                       for lab in g["labels"]],
            "you_edges": [{"id": k["id"], "points": _quad(*cv)}
                          for k, cv in zip(g["clusters"], _you_curves(g))] if g["you"] else [],
            "sc": g["sc"], "fail": g["fail"]}


def clusters_svg(payload, wide=False) -> str:
    g = _build(payload, wide)
    pos, rad, sc = g["pos"], g["rad"], g["sc"]
    card = CARD_WIDE if wide else CARD
    fp = payload["footprint"]
    o = title_svg(g["tsize"], g["tlines"], g["title_y0"])
    emax = max((k["req"] for k in g["clusters"]), default=1) or 1
    if g["you"]:
        for k, cv in zip(g["clusters"], _you_curves(g)):
            sw = max(3.0, 22 * k["req"] / emax)
            o.append(f'<path d="{_curve(*cv)}" fill="none" '
                     f'stroke="{k["col"]}" stroke-opacity=".45" stroke-width="{sw:.1f}" '
                     'stroke-linecap="round"/>')
    pmax = max((n["req"] for n in g["nodes"]), default=1) or 1
    for n in g["nodes"]:
        k = n["k"]
        cx, cy = k["xy"]
        x, y = pos[n["id"]]
        sw = max(1.5, 8 * n["req"] / pmax)
        o.append(f'<path d="M{cx:.1f},{cy:.1f} L{x:.1f},{y:.1f}" stroke="{k["col"]}" '
                 f'stroke-opacity=".5" stroke-width="{sw:.1f}" stroke-linecap="round" fill="none"/>')
    for k in g["clusters"]:
        cx, cy = k["xy"]
        col = k["col"]
        r = k["r"]
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{svg.BG}"/>')
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" fill-opacity=".18" '
                 f'stroke="{col}" stroke-width="4"/>')
        if k["other"]:
            name = "Other countries"
        elif k["c"] is not None:
            name = payload["country_names"].get(k["c"], k["c"])
        if k["c"] is None:
            f1, f2, f3 = min(34, r * .45), max(13, min(17, r * .28)), min(26, r * .34)
            lines = (("??", f1, 900), (f"{pct(k['share'])}%", f3, 900),
                     ("unknown", f2, 700), ("/ withheld", f2, 700))
            tot = sum(sz * 1.12 for _, sz, _ in lines)
            ty = cy - tot / 2
            for txt, sz, wt in lines:
                ty += sz * 1.12
                o.append(f'<text x="{cx:.1f}" y="{ty - sz * .2:.1f}" font-size="{sz:.0f}" '
                         f'font-weight="{wt}" text-anchor="middle" fill="#5b5d69">{svg.esc(txt)}</text>')
        else:
            fn = max(11, min(26 * sc, 1.9 * r / (len(name) * 0.58)))
            fpct = min(44 * sc, r * .5)
            ink = svg.INK
            o.append(f'<text x="{cx:.1f}" y="{cy - fpct * .12:.1f}" font-size="{fn:.0f}" '
                     f'font-weight="800" text-anchor="middle" fill="{ink}">{svg.esc(name)}</text>')
            o.append(f'<text x="{cx:.1f}" y="{cy + fpct * .85:.1f}" font-size="{fpct:.0f}" '
                     f'font-weight="900" text-anchor="middle" fill="{col}">{svg.esc(pct(k["share"]) + "%")}</text>')
    for n in g["nodes"]:
        x, y = pos[n["id"]]
        p, r = n["p"], rad[n["id"]]
        c = p["country"] if p else n["k"]["c"]
        if n["kind"] == "more":
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{GREY}" fill-opacity=".6" '
                     f'stroke="#fff" stroke-width="2.5"/>')
            continue
        hr = g["halo"][n["id"]]
        if p["parent_id"]:
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{hr:.1f}" fill="{svg.color(c)}" '
                     f'fill-opacity=".10" stroke="{svg.color(c)}" stroke-width="2.5"/>')
        elif p["id"] != "unknown":
            o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{hr:.1f}" fill="#fff" fill-opacity=".5" '
                     f'stroke="{GREY}" stroke-width="2.5" stroke-dasharray="7 6"/>')
        conf = max(p["locations"], key=lambda l: l["requests"])["confidence"] if p["locations"] else None
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{svg.fill(c, conf, card)}" '
                 f'stroke="{svg.color(c)}" stroke-width="3"/>')
    if g["you"]:
        yx, yy = g["you"]
        o.append(f'<circle cx="{yx:.1f}" cy="{yy:.1f}" r="52" fill="{svg.INK}"/>')
        o.append(f'<text x="{yx:.1f}" y="{yy + 9:.1f}" font-size="28" font-weight="800" '
                 f'text-anchor="middle" fill="#fff">You</text>')
    for lab in g["labels"]:
        x = {"start": lab["x"], "end": lab["x"] + lab["w"], "middle": lab["x"] + lab["w"] / 2}[lab["anchor"]]
        col = GREY_TXT if lab["kind"] == "more" else svg.INK
        o.append(f'<text class="lab" x="{x:.1f}" y="{lab["y"] + lab["size"]:.1f}" '
                 f'font-size="{lab["size"]}" font-weight="{lab["weight"]}" '
                 f'text-anchor="{lab["anchor"]}" fill="{col}">{svg.esc(lab["text"])}</text>')
        if lab["sub"]:
            unk = lab["sub"] == "parent unknown"
            italic = ' font-style="italic"' if unk else ""
            o.append(f'<text class="lab" x="{x:.1f}" y="{lab["y"] + lab["size"] * 1.2 + 16:.1f}" '
                     f'font-size="16" font-weight="600" text-anchor="{lab["anchor"]}" '
                     f'fill="{GREY_TXT if unk else "#4a4b58"}"{italic}>'
                     f'{svg.esc(lab["sub"])}</text>')
    return svg.card(payload, card, g["w"], g["h"], "".join(o), foot_extra=_foot_extra(payload),
                    foot_w=g["foot_w"])
