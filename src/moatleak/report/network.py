"""Radial hero network (direction A): deterministic layout + SVG string (stdlib only)."""
import math
import re

from moatleak.headlines import pct
from moatleak.report import svg

CARD = "hero-radial"
GAP = 0.7  # angular gap between sectors, in provider units
MAX_NAMED = 16
# Up to this many companies the layout spends extra passes (re-settle + tangential labels); beyond it, large graphs skip them for speed.
DENSE_LAYOUT_MAX = 20
GREY_TXT = "#6b6d79"
_NUM = "#E5484D", "#3E8EF7", "#1f9a62"


def _pol(cx, cy, r, a):
    t = math.radians(a)
    return cx + r * math.sin(t), cy - r * math.cos(t)


def _cmean(pairs, default=0.0):
    sx = sum(w * math.sin(math.radians(a)) for a, w in pairs)
    sy = sum(w * math.cos(math.radians(a)) for a, w in pairs)
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return default
    return math.degrees(math.atan2(sx, sy)) % 360


def _spread(angles, sep):
    """Push neighbouring angles (dict id -> deg) apart until each gap >= sep degrees."""
    ids = sorted(angles, key=lambda k: angles[k])
    if len(ids) < 2:
        return
    base = angles[ids[0]]
    u = [(angles[k] - base) % 360 for k in ids]  # unwrapped, kept in cyclic order
    n = len(ids)
    for _ in range(600):
        moved = False
        for i in range(n):
            a, b = u[i], (u[i + 1] if i + 1 < n else u[0] + 360)
            if b - a < sep - 0.01:
                push = (sep - (b - a)) / 2
                u[i] -= push
                if i + 1 < n:
                    u[i + 1] += push
                else:
                    u[0] += push
                moved = True
        if not moved:
            break
    for k, v in zip(ids, u):
        angles[k] = (base + v) % 360


def _trunc(s, n=18):
    return s if len(s) <= n else s[: n - 1] + "…"


def _title_words(c):
    n, p, k = c["companies"], c["parent_groups"], c["countries"]
    out = [(w, None) for w in "Your prompts were processed by".split()]
    out += [(str(n), 0), ("company" if n == 1 else "companies", None)]
    if p:
        out[-1] = (out[-1][0] + ",", None)
        out += [("owned", None), ("by", None), (str(p), 1), ("group" if p == 1 else "groups", None)]
    if k:
        out[-1] = (out[-1][0] + ",", None)
        out += [("in", None), (str(k), 2), ("country" if k == 1 else "countries", None)]
    out[-1] = (out[-1][0] + ".", None)
    return out


def _title(payload, w, sizes=(60, 56, 52, 48, 44), max_lines=3):
    words = _title_words(payload["counts"])
    for size in sizes:
        lines, cur, cw = [], [], 0.0
        for word, k in words:
            ww = svg.text_width(word, size, 900)
            sp = svg.text_width(" ", size, 900)
            if cur and cw + sp + ww > w - 112:
                lines.append(cur)
                cur, cw = [], 0.0
            cw += (sp if cur else 0) + ww
            cur.append((word, k))
        lines.append(cur)
        if len(lines) <= max_lines:
            break
    return size, lines


def title_svg(tsize, tlines, y0=150) -> list[str]:
    """Title text elements (numbers coloured); shared by the radial and cluster cards."""
    o = []
    for i, line in enumerate(tlines):
        parts = []
        for j, (wd, k) in enumerate(line):
            sep = " " if j else ""
            parts.append(svg.esc(sep + wd) if k is None
                         else f'{sep}<tspan fill="{_NUM[k]}">{svg.esc(wd)}</tspan>')
        o.append(f'<text x="56" y="{y0 + i * tsize * 1.08:.1f}" font-size="{tsize}" '
                 f'font-weight="900" letter-spacing="-1.5" fill="{svg.INK}" '
                 f'xml:space="preserve">{"".join(parts)}</text>')
    return o


def _foot_extra(payload):
    note = payload["coverage_note"]
    sents = []
    for kind in ("countries", "extent"):
        for h in payload["headlines"]:
            if h["kind"] != kind:
                continue
            txt = h["footnote"].replace(note, "").strip()
            if kind == "countries":
                m = re.search(r"Location basis: .*?%\.", txt)
                txt = m.group(0) if m else ""
            if txt and txt not in sents:
                sents.append(txt)
    return " ".join(sents)


def _gap(b, cx, cy, r):
    """Distance from circle (cx, cy, r) edge to the rect b=(x, y, w, h); < 0 when they overlap."""
    nx = min(max(cx, b[0]), b[0] + b[2])
    ny = min(max(cy, b[1]), b[1] + b[3])
    return math.hypot(nx - cx, ny - cy) - r


def _rect_circle(b, cx, cy, r):
    return _gap(b, cx, cy, r) < 0


def _hits_band(b, cx, cy, r_in, r_out):
    """True when rect b intersects the annulus r_in..r_out around (cx, cy)."""
    nx = min(max(cx, b[0]), b[0] + b[2])
    ny = min(max(cy, b[1]), b[1] + b[3])
    near = math.hypot(nx - cx, ny - cy)
    far = max(math.hypot(px - cx, py - cy) for px in (b[0], b[0] + b[2]) for py in (b[1], b[1] + b[3]))
    return near < r_out and far > r_in


def _rect_area(a, b):
    ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return ox * oy if ox > 0 and oy > 0 else 0.0


LABEL_EDGE_CLEARANCE = 8.0  # px between an access/tool label box and any foreign edge


def _seg_hits(p, q, b, pad=3.0):
    n = max(2, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 2))
    return any(b[0] - pad <= p[0] + (q[0] - p[0]) * k / n <= b[0] + b[2] + pad
               and b[1] - pad <= p[1] + (q[1] - p[1]) * k / n <= b[1] + b[3] + pad
               for k in range(n + 1))


def _seg_near_rect(p, q, b, pad=0.0):
    """Exact: True iff segment p-q meets rectangle b=(x, y, w, h) grown by pad (borders count).
    Liang-Barsky clip, O(1)."""
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[0] + b[2] + pad, b[1] + b[3] + pad
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for d, lo in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if d == 0:
            if lo < 0:
                return False
            continue
        t = lo / d
        if d < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


def _poly_box(pts, pad):
    return (min(p[0] for p in pts) - pad, max(p[0] for p in pts) + pad,
            min(p[1] for p in pts) - pad, max(p[1] for p in pts) + pad)


def _poly_near_rect(pts, box, b, pad):
    """box = _poly_box(pts, pad) (precomputed); True iff any polyline segment is within pad of b."""
    if not (box[0] <= b[0] + b[2] and box[1] >= b[0] and box[2] <= b[1] + b[3] and box[3] >= b[1]):
        return False
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[0] + b[2] + pad, b[1] + b[3] + pad
    for i in range(len(pts) - 1):
        (ax, ay), (cx, cy) = pts[i], pts[i + 1]
        if (ax < x0 and cx < x0) or (ax > x1 and cx > x1) or (ay < y0 and cy < y0) or (ay > y1 and cy > y1):
            continue  # segment bbox misses the box: cheap reject before the exact clip
        if _seg_near_rect((ax, ay), (cx, cy), b, pad):
            return True
    return False


def _bend(layer):
    return 0.1 if layer == "provider" else 0.0


def _curve_pts(p, q, bend, n=16):
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    c = (mx - (q[1] - p[1]) * bend, my + (q[0] - p[0]) * bend)
    return [((1 - k) ** 2 * p[0] + 2 * (1 - k) * k * c[0] + k * k * q[0],
             (1 - k) ** 2 * p[1] + 2 * (1 - k) * k * c[1] + k * k * q[1])
            for k in (i / n for i in range(n + 1))]


def _pt_seg(c, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = vx * vx + vy * vy
    k = 0.0 if L == 0 else max(0.0, min(1.0, ((c[0] - a[0]) * vx + (c[1] - a[1]) * vy) / L))
    return math.hypot(c[0] - a[0] - k * vx, c[1] - a[1] - k * vy)


def _violations(pos, rad, elist, margin=6.0, cap=None):
    """(source, target, node) for every drawn edge passing within rad+margin of a non-endpoint
    tool/access/company node. elist = [(source, target, bend)]."""
    out = []
    obst = [k for k in pos if k.startswith(("tool:", "access:", "provider:"))]
    for a, b, bend in elist:
        if a not in pos or b not in pos:
            continue
        pts = _curve_pts(pos[a], pos[b], bend)
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        for k in obst:
            if k in (a, b):
                continue
            lim = rad[k] + margin
            if not (x0 - lim <= pos[k][0] <= x1 + lim and y0 - lim <= pos[k][1] <= y1 + lim):
                continue
            if min(_pt_seg(pos[k], pts[i], pts[i + 1]) for i in range(len(pts) - 1)) < rad[k] + margin:
                out.append((a, b, k))
                if cap and len(out) >= cap:
                    return out
    return out


def _edge_clearance_violations(layout):
    """Test/QA helper over radial_layout() output."""
    pos = {n["id"]: (n["x"], n["y"]) for n in layout["nodes"]}
    rad = {n["id"]: n["r"] for n in layout["nodes"]}
    return _violations(pos, rad, [tuple(e) for e in layout["edge_geom"]])


def _label_crossings(pos, labels, elist, pad=LABEL_EDGE_CLEARANCE):
    """(label id, source, target) for every drawn edge crossing an access/tool label box
    while not being incident to that label's own node."""
    out = []
    polys = [(a, c, pts, _poly_box(pts, pad)) for a, c, bend in elist if a in pos and c in pos
             for pts in (_curve_pts(pos[a], pos[c], bend),)]
    for lab in labels:
        if lab["kind"] not in ("access", "tool"):
            continue
        b = (lab["x"], lab["y"], lab["w"], lab["h"])
        for a, c, pts, box in polys:
            if lab["id"] not in (a, c) and _poly_near_rect(pts, box, b, pad):
                out.append((lab["id"], a, c))
    return out


def _label_edge_crossings(layout):
    """Test/QA helper over radial_layout() output."""
    pos = {n["id"]: (n["x"], n["y"]) for n in layout["nodes"]}
    return _label_crossings(pos, layout["labels"], [tuple(e) for e in layout["edge_geom"]])


def _build(payload, w=1080, h=1350):
    net = payload["network"]
    nodes = {n["id"]: n for n in net["nodes"]}
    edges = net["edges"]
    provs = sorted((n for n in nodes.values() if n["layer"] == "provider"),
                   key=lambda n: (-n["requests"], n["label"]))
    prov_ids = {n["id"] for n in provs}
    rank = {n["id"]: i + 1 for i, n in enumerate(provs)}

    # --- text blocks that determine the drawable area
    tsize, tlines = _title(payload, w)
    title_bottom = 150 + (len(tlines) - 1) * tsize * 1.08 + 14
    legend = []
    for n in provs:
        if rank[n["id"]] > MAX_NAMED:
            legend.append(f"{rank[n['id']]} {n['label']}")
        elif len(n["label"]) > 18:
            legend.append(n["label"])
    cols = rows = 0
    bottom = h - 34 - 2 * 20 - 15 - 8
    if legend:
        mx = max(len(t) for t in legend)
        cols = max(1, min(3, int((w - 112) // (mx * 7.4 + 24))))
        rows = math.ceil(len(legend) / cols)
        bottom -= rows * 17 + 12
    top = title_bottom + 10
    R4 = min((bottom - top) / 2 - 18, 470, (w - 40) / 2 - 15)
    s = R4 / 470
    cx, cy = w / 2, (top + bottom) / 2
    R1, R2, R3 = 120 * s, 300 * s, 390 * s
    rmax = (44 if len(provs) <= 10 else 36 if len(provs) <= 16 else 28) * s

    def nr(req, mx, scale=1.0):
        return max(7.0, rmax * scale * math.sqrt(req / mx)) if mx else 7.0

    # --- sectors
    groups: dict = {}
    for n in provs:
        groups.setdefault(n.get("country"), []).append(n)
    order = sorted((c for c in groups if c is not None),
                   key=lambda c: (-sum(n["requests"] for n in groups[c]), c))
    if None in groups:
        order.append(None)
    units = len(provs) + GAP * len(order)
    deg = 360 / units if units else 0
    a = GAP * deg / 2
    ang, sectors = {}, []
    for c in order:
        a0 = a
        for i, n in enumerate(groups[c]):
            ang[n["id"]] = a + (i + 0.5) * deg
        a += len(groups[c]) * deg
        sectors.append((c, a0 + 0.1 * deg, a - 0.1 * deg, sum(n["requests"] for n in groups[c])))
        a += GAP * deg
    pmax = max((n["requests"] for n in provs), default=0)
    pos, rad = {"you": (cx, cy)}, {"you": 46 * s}
    for n in provs:
        pos[n["id"]] = _pol(cx, cy, R2, ang[n["id"]])
        rad[n["id"]] = nr(n["requests"], pmax)

    # --- parents (drawn only when they add information) and unknown-parent markers
    attached: dict = {}
    for n in provs:
        if n.get("parent_id"):
            attached.setdefault(f"parent:{n['parent_id']}", []).append(n)
    parent_drawn, markers = {}, {}
    ppmax = max((nodes[k]["requests"] for k in attached if k in nodes), default=0)
    for pid in sorted(attached):
        if pid not in nodes:
            continue
        grp = attached[pid]
        label = nodes[pid]["label"]
        if len(grp) >= 2 or any(label.casefold() != g["label"].casefold() for g in grp):
            parent_drawn[pid] = grp
            ang[pid] = _cmean([(ang[g["id"]], g["requests"]) for g in grp], ang[grp[0]["id"]])
            pos[pid] = _pol(cx, cy, R3, ang[pid])
            rad[pid] = nr(nodes[pid]["requests"], ppmax, 0.62)
    for n in provs:
        if not n.get("parent_id") and n["id"] != "provider:unknown":
            mid = f"marker:{n['id']}"
            markers[mid] = n
            ang[mid] = ang[n["id"]]
            pos[mid] = _pol(cx, cy, R3, ang[mid])
            rad[mid] = 10 * s

    # --- access methods + tools
    ew = {(e["source"], e["target"]): e["requests"] for e in edges}
    accesses = sorted((n for n in nodes.values() if n["layer"] == "access"),
                      key=lambda n: (-n["requests"], n["label"]))
    elist = [(e["source"], e["target"], _bend(nodes[e["target"]]["layer"]))
             for e in edges if e["source"] in nodes or e["source"] == "you"]
    elist = [x for x in elist if x[1] in nodes]
    fallbacks: list = []
    OFFS = [0.0] + [v * k for k in range(4, 44, 4) for v in (1, -1)]
    r_ac = 195 * s
    mean_ac = {}
    for i, ac in enumerate(accesses):
        mean_ac[ac["id"]] = _cmean([(ang[e["target"]], e["requests"]) for e in edges
                                    if e["source"] == ac["id"] and e["target"] in prov_ids],
                                   360 * i / max(1, len(accesses)))

    WIDE = [0.0] + [v * k for k in range(8, 128, 8) for v in (1, -1)]

    def settle(nid, base, r0, rd, facs, cap=4, offs=OFFS):
        """First (offset, radius-factor) candidate with no drawn edge too close to a foreign node."""
        best = None
        for off in offs:
            for f in facs:
                a_ = (base + off) % 360
                pos[nid], rad[nid], ang[nid] = _pol(cx, cy, r0 * f, a_), rd, a_
                tooclose = any(math.hypot(pos[nid][0] - pos[k][0], pos[nid][1] - pos[k][1])
                               < rd + rad[k] + 16 for k in pos if k not in (nid, "you")
                               and k.startswith(("tool:", "access:", "provider:")))
                tooclose = tooclose or (nid.startswith("access:") and any(
                    k.startswith("access:") and k != nid and k in pos
                    and math.hypot(pos[nid][0] - pos[k][0], pos[nid][1] - pos[k][1]) < 150 * s for k in pos))
                if tooclose or math.hypot(pos[nid][0] - cx, pos[nid][1] - cy) < rd + rad["you"] + 8:
                    continue
                v = len(_violations(pos, rad, elist, cap=cap))
                if v == 0:
                    return
                if best is None or v < best[0]:
                    best = (v, pos[nid], a_)
        if best:
            pos[nid], ang[nid] = best[1], best[2]
        else:
            pos[nid], ang[nid] = _pol(cx, cy, r0, base), base
        rad[nid] = rd

    plan = {}
    for ac in accesses:
        plan[ac["id"]] = (mean_ac[ac["id"]], r_ac, 22 * s, (1.0, 1.18, 0.85))
        settle(ac["id"], *plan[ac["id"]])
    tools = sorted((n for n in nodes.values() if n["layer"] == "tool"),
                   key=lambda n: (-n["requests"], n["label"]))
    for i, t_ in enumerate(tools):
        pr = [(ang[e["target"]], e["requests"]) for e in edges
              if e["source"] == t_["id"] and e["target"] in nodes and nodes[e["target"]]["layer"] == "access"]
        plan[t_["id"]] = (_cmean(pr, 360 * i / max(1, len(tools))), R1, 24 * s, (1.0, 1.18, 0.85, 1.35, 0.75))
        pos[t_["id"]], rad[t_["id"]], ang[t_["id"]] = (0, 0), 0, 0
    for t_ in tools:
        del pos[t_["id"]]
    for t_ in tools:
        settle(t_["id"], *plan[t_["id"]])
    for _ in range(2 if len(provs) <= DENSE_LAYOUT_MAX else 0):  # re-place movable nodes that still sit on a foreign edge
        bad = {x for v in _violations(pos, rad, elist) for x in v if x in plan}
        if not bad:
            break
        for nid in [k for k in plan if k in bad]:
            settle(nid, *plan[nid], cap=None, offs=WIDE)
    for v in _violations(pos, rad, elist):
        fallbacks.append(f"edge:{v[0]}>{v[1]}@{v[2]}")

    # --- labels (greedy, deterministic; radially outside the node, nudged on collision)
    fs_p, fs_pa, fs_t, fs_b = max(13, 20 * s), max(12, 17.5 * s), 16, 13
    arc_half = 15 * s
    labels: list = []
    placed: list = []

    near_ids = [k for k in pos if k != "you"]

    def own_nearest(b, node_id):
        """Hard rule: the label box is closer to its own node than to any other node."""
        mine = _gap(b, *pos[node_id], rad[node_id])
        return all(mine < _gap(b, *pos[k], rad[k]) - 0.5 for k in near_ids if k != node_id)

    epolys = []  # per drawn edge, once per layout: (source, target, polyline, padded bbox)
    for a_, b_, bd in elist:
        if a_ in pos and b_ in pos:
            pts = _curve_pts(pos[a_], pos[b_], bd)
            epolys.append((a_, b_, pts, _poly_box(pts, LABEL_EDGE_CLEARANCE)))
    foreign: dict = {}  # node id -> edges not incident to it (once per node, not per candidate)

    def crosses(b, node_id, final=False):
        if not final and len(provs) > DENSE_LAYOUT_MAX:  # dense: too slow to search; recorded below instead
            return False
        if node_id not in foreign:
            foreign[node_id] = [e for e in epolys if node_id not in (e[0], e[1])]
        return any(_poly_near_rect(pts, box, b, LABEL_EDGE_CLEARANCE) for _, _, pts, box in foreign[node_id])

    def place(lid, text, size, weight, node_id, kind, italic=False, away=False, clear_own=False,
              minsz=13, tang=0):
        x0, y0 = pos[node_id]
        r0 = rad[node_id]
        a_ = math.radians(ang.get(node_id, 0.0))
        dx, dy = math.sin(a_), -math.cos(a_)
        tx, ty = -dy, dx

        def attempt(size, wide):
            lw = svg.text_width(text, size, weight)
            lhh = size * 1.2
            dirs = [(sg * dx, sg * dy) for sg in ((-1, 1) if away else (1, -1))]
            if wide:
                dirs += [(tx, ty), (-tx, -ty)]
            if tang:  # tool labels: beside the disc (tangential), outward last, never on the hub side
                k_ = math.sqrt(0.5)
                dirs = [(tang * tx, tang * ty), (-tang * tx, -tang * ty), (dx, dy)]
                dirs += [(k_ * (sg * tx + dx), k_ * (sg * ty + dy)) for sg in (tang, -tang)]
            cands = []
            for ex, ey in dirs:
                for o in ((0, 22, 44, 66) if wide else (0, 22, 44)):
                    for t in ((0, 1, -1, 2, -2, 3, -3, 4, -4) if wide else (0, 1, -1, 2, -2)):
                        d0 = r0 + 8 + o
                        ax, ay = x0 + ex * d0 + tx * t * lhh, y0 + ey * d0 + ty * t * lhh
                        if abs(ex) < 0.3:
                            bx = ax - lw / 2
                            by = ay - lhh if ey < 0 else ay
                        else:
                            bx = ax if ex > 0 else ax - lw
                            by = ay - lhh / 2 + ey * lhh / 2
                        cands.append((bx, by, lw, lhh))
            if wide:  # last resort: fine scan around the node, closest-to-node first
                st = 4
                scan = [(x0 + i * st - lw / 2 - 90, y0 + j * st - lhh / 2 - 60, lw, lhh)
                        for i in range(int((lw + 180) / st) + 1) for j in range(int(120 / st) + 1)]
                cands += sorted(scan, key=lambda b: _gap(b, x0, y0, r0))
            best = None
            for stage in (0, 1, 2):
                for b in cands:
                    if b[0] < 8 or b[0] + lw > w - 8 or b[1] < top or b[1] + lhh > bottom:
                        continue
                    if _hits_band(b, cx, cy, R4 - arc_half - 2, R4 + arc_half + 2):
                        continue
                    own_gap = _gap(b, x0, y0, r0)
                    if tang and (_gap(b, cx, cy, rad["you"]) < 12 or any(
                            _seg_near_rect(pos[a_], pos[b_], b, 3.0) for a_, b_, _ in elist if a_ == "you")):
                        continue
                    if (clear_own and own_gap < 2) or own_gap > ((80 if tang else 60) if wide else 40) or not own_nearest(b, node_id):
                        continue
                    xing = kind in ("access", "tool") and crosses(b, node_id)
                    if xing and stage < 2:
                        continue
                    over = sum(_rect_area(b, q) for q in placed) + (1e6 if xing else 0)
                    inside = all(math.hypot(px - cx, py - cy) <= R4 - 18
                                 for px in (b[0], b[0] + lw) for py in (b[1], b[1] + lhh))
                    clear = not any(_gap(b, *pos[k], rad[k] + 2) < 0 for k in pos if k != node_id)
                    if stage == 0 and over == 0 and clear and inside:
                        best = (*b, 0)
                        break
                    if stage == 1 and over == 0 and clear:
                        best = (*b, 0)
                        break
                    if stage == 2 and (best is None or over < best[4]):
                        best = (*b, over)
                if best:
                    break
            return best, size, lw, lhh, cands

        best = fb = None
        for sz, wide in ((size, False), (size, True), (minsz, True), (13, True)):
            cur, size_used, lw_, lhh_, cands = attempt(sz, wide)
            if cur and (fb is None or cur[4] < fb[0][4]):
                fb = (cur, size_used, lw_, lhh_, cands)
            if cur and cur[4] == 0:
                break
        if fb:
            best, size, lw, lhh, cands = fb
        if best is None:
            fallbacks.append(lid)
            size = min(size, 13)
            lw = svg.text_width(text, size, weight)
            lhh = size * 1.2
            bx0 = min(max(cands[0][0], 8), max(8, w - 8 - lw))
            by0 = min(max(cands[0][1], top), max(top, bottom - lhh))
            best = (bx0, by0, lw, lhh, 0)
        b = best[:4]
        placed.append(b)
        if kind in ("access", "tool") and crosses(b, node_id, True):
            fallbacks.append(f"label-edge:{lid}")
        labels.append({"id": lid, "text": text, "x": round(b[0], 1), "y": round(b[1], 1),
                       "w": round(lw, 1), "h": round(lhh, 1), "size": size, "weight": weight,
                       "italic": italic, "kind": kind})

    for ac in accesses:
        oth = [pos[u["id"]] for u in accesses if u is not ac]
        ox = sum(p_[0] for p_ in oth) / len(oth) if oth else cx
        oy = sum(p_[1] for p_ in oth) / len(oth) if oth else cy
        a_ = math.radians(ang[ac["id"]])
        dot = (pos[ac["id"]][0] - ox) * math.cos(a_) + (pos[ac["id"]][1] - oy) * math.sin(a_)
        place(ac["id"], ac["label"], fs_t, 900, ac["id"], "access", away=True, clear_own=True,
              minsz=15 if len(provs) <= MAX_NAMED else 13, tang=(1 if dot >= 0 else -1) if len(provs) <= DENSE_LAYOUT_MAX else 0)
    for t in tools:
        oth = [pos[u["id"]] for u in tools if u is not t]
        ox = sum(p_[0] for p_ in oth) / len(oth) if oth else cx
        oy = sum(p_[1] for p_ in oth) / len(oth) if oth else cy
        a_ = math.radians(ang[t["id"]])
        dot = (pos[t["id"]][0] - ox) * math.cos(a_) + (pos[t["id"]][1] - oy) * math.sin(a_)
        place(t["id"], _trunc(t["label"]), fs_t, 900, t["id"], "tool", minsz=15,
              tang=1 if dot >= 0 else -1)
    for n in provs:
        if rank[n["id"]] <= MAX_NAMED:
            place(n["id"], _trunc(n["label"]), fs_p, 800, n["id"], "provider")
    for n in provs:
        if rank[n["id"]] > MAX_NAMED:
            place(n["id"], str(rank[n["id"]]), fs_b, 800, n["id"], "badge")
    for pid in parent_drawn:
        place(pid, _trunc(nodes[pid]["label"]), fs_pa, 600, pid, "parent")
    for mid in markers:
        place(mid, "parent unknown", fs_pa, 600, mid, "marker", italic=True)

    return {"w": w, "h": h, "cx": cx, "cy": cy, "s": s, "R": (R1, R2, R3, R4), "nodes": nodes,
            "pos": pos, "rad": rad, "labels": labels, "sectors": sectors, "provs": provs,
            "tools": tools, "accesses": accesses, "fallbacks": fallbacks, "parent_drawn": parent_drawn, "markers": markers,
            "tsize": tsize, "tlines": tlines, "legend": legend, "cols": cols, "rows": rows,
            "legend_top": bottom + 12, "edges": edges, "elist": elist}


def radial_layout(payload, w=1080, h=1350) -> dict:
    g = _build(payload, w, h)
    return {"nodes": [{"id": k, "x": round(g["pos"][k][0], 1), "y": round(g["pos"][k][1], 1),
                       "r": round(g["rad"][k], 1)} for k in g["pos"]],
            "labels": [{k: lab[k] for k in ("id", "text", "x", "y", "w", "h", "kind", "size", "weight")}
                       for lab in g["labels"]],
            "fallbacks": list(g["fallbacks"]),
            "edge_geom": [(a, b, bd) for a, b, bd in g["elist"]],
            "arc": {"cx": g["cx"], "cy": g["cy"], "r": g["R"][3], "half": 15 * g["s"]}}


def _curve(p, q, bend):
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    dx, dy = q[0] - p[0], q[1] - p[1]
    return f"M{p[0]:.1f},{p[1]:.1f} Q{mx - dy * bend:.1f},{my + dx * bend:.1f} {q[0]:.1f},{q[1]:.1f}"


def radial_svg(payload) -> str:
    g = _build(payload)
    nodes, pos, rad, s = g["nodes"], g["pos"], g["rad"], g["s"]
    cx, cy = g["cx"], g["cy"]
    R1, R2, R3, R4 = g["R"]
    o = []
    o.extend(title_svg(g["tsize"], g["tlines"]))
    for r in (R2, R3):
        o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{svg.INK}" '
                 'stroke-opacity=".07" stroke-width="1.5" stroke-dasharray="3 7"/>')
    emax = max((e["requests"] for e in g["edges"]), default=1)

    def edge(a, b, req, colr, bend, op, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        sw = max(1.2, 14 * s * req / emax)
        o.append(f'<path d="{_curve(pos[a], pos[b], bend)}" fill="none" stroke="{colr}" '
                 f'stroke-opacity="{op}" stroke-width="{sw:.1f}" stroke-linecap="round"{d}/>')

    for e in g["edges"]:
        a, b, req = e["source"], e["target"], e["requests"]
        if a not in pos or b not in pos or b not in nodes:
            continue
        lb = nodes[b]["layer"]
        if lb in ("tool", "access"):
            edge(a, b, req, svg.INK, 0, 0.25)
        elif lb == "provider":
            edge(a, b, req, svg.color(nodes[b].get("country")), 0.1, 0.5)
        elif lb == "parent":
            edge(a, b, req, svg.color(nodes[b].get("country")), 0, 0.55)
    for mid, n in g["markers"].items():
        edge(n["id"], mid, n["requests"], svg.COLORS["GREY"], 0, 1, "6 6")
    for i, (c, a0, a1, req) in enumerate(g["sectors"]):
        p0, p1 = _pol(cx, cy, R4, a0), _pol(cx, cy, R4, a1)
        large = 1 if (a1 - a0) > 180 else 0
        if not 90 < ((a0 + a1) / 2) % 360 < 270:
            d = f"M{p0[0]:.1f},{p0[1]:.1f} A{R4:.1f},{R4:.1f} 0 {large} 1 {p1[0]:.1f},{p1[1]:.1f}"
        else:
            d = f"M{p1[0]:.1f},{p1[1]:.1f} A{R4:.1f},{R4:.1f} 0 {large} 0 {p0[0]:.1f},{p0[1]:.1f}"
        o.append(f'<path id="{CARD}-arc-{i}" d="{d}" fill="none" stroke="{svg.color(c)}" '
                 f'stroke-width="{30 * s:.1f}" stroke-linecap="butt"/>')
        fp = payload["footprint"]
        if c is None:
            share, name = fp.get("undisclosed_share"), "??"
        else:
            share, name = fp["country_share"].get(c), payload["country_names"].get(c, c).upper()
        if share is None:
            share = req / payload["total_requests"] if payload["total_requests"] else 0
        fsz = max(14, 22 * s)
        arc_len = math.radians(a1 - a0) * R4 - 10
        lab = ""
        for cand in (f"{name} · {pct(share)}%", f"{c or '??'} · {pct(share)}%"):
            if svg.text_width(cand, fsz, 800) + 2.5 * s * len(cand) <= arc_len:
                lab = cand
                break
        if lab:
            fg = svg.INK if svg.country_key(c) == "EU" else "#fff"
            o.append(f'<text font-size="{fsz:.0f}" font-weight="800" letter-spacing="{2.5 * s:.1f}" '
                     f'fill="{fg}" dy="{fsz * 0.35:.1f}"><textPath href="#{CARD}-arc-{i}" '
                     f'startOffset="50%" text-anchor="middle">{svg.esc(lab)}</textPath></text>')
    for n in g["provs"]:
        x, y = pos[n["id"]]
        c = n.get("country")
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad[n["id"]]:.1f}" '
                 f'fill="{svg.fill(c, n.get("confidence"), CARD)}" stroke="{svg.color(c)}" '
                 f'stroke-width="{3 * s:.1f}"/>')
    for pid in g["parent_drawn"]:
        x, y = pos[pid]
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad[pid]:.1f}" '
                 f'fill="{svg.color(nodes[pid].get("country"))}" stroke="#fff" '
                 f'stroke-width="{2.5 * s:.1f}"/>')
    for mid in g["markers"]:
        x, y = pos[mid]
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad[mid]:.1f}" fill="#fff" '
                 f'stroke="{svg.COLORS["GREY"]}" stroke-width="{2.5 * s:.1f}" stroke-dasharray="4 3"/>')
    for t in g["tools"]:
        x, y = pos[t["id"]]
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad[t["id"]]:.1f}" fill="#fff" '
                 f'stroke="{svg.INK}" stroke-width="{3 * s:.1f}"/>')
    for ac in g["accesses"]:
        x, y = pos[ac["id"]]
        r = rad[ac["id"]]
        o.append(f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r:.1f}" height="{2 * r:.1f}" '
                 f'rx="{10 * s:.1f}" fill="{svg.INK}"/>')
    o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad["you"]:.1f}" fill="{svg.INK}"/>')
    o.append(f'<text x="{cx:.1f}" y="{cy + 8 * s:.1f}" font-size="{max(17, 24 * s):.0f}" '
             'font-weight="800" text-anchor="middle" fill="#fff">You</text>')
    for lab in g["labels"]:
        fill = {"parent": "#3a3b48", "marker": GREY_TXT}.get(lab["kind"], svg.INK)
        it = ' font-style="italic"' if lab["italic"] else ""
        o.append(f'<text class="lab" x="{lab["x"] + lab["w"] / 2:.1f}" y="{lab["y"] + lab["size"]:.1f}" '
                 f'font-size="{lab["size"]:.1f}" font-weight="{lab["weight"]}" text-anchor="middle" '
                 f'fill="{fill}"{it}>{svg.esc(lab["text"])}</text>')
    if g["legend"]:
        colw = (g["w"] - 112) / g["cols"]
        for i, t in enumerate(g["legend"]):
            col, row = divmod(i, g["rows"])
            o.append(f'<text x="{56 + col * colw:.1f}" y="{g["legend_top"] + 12 + row * 17:.1f}" '
                     f'font-size="13" fill="#3a3b48">{svg.esc(t)}</text>')
    return svg.card(payload, CARD, g["w"], g["h"], "".join(o), foot_extra=_foot_extra(payload))
