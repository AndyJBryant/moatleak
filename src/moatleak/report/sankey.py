"""In-report Sankey: tool -> access method -> company -> parent group -> country (stdlib only).

Tool/access/company columns come from payload["routes"]; company -> parent -> country from payload["network"].
"""
from moatleak.report import svg

_COLS = ("Tool", "Access method", "Company", "Parent group", "Country")
_X = (32, 210, 470, 654, 1020)
_NW, _GAP, _MIN, _Y0, _H = 8, 8, 3.0, 215, 1000
_MAX_GAP = 40
_LAB_H, _FS = 16, 15
_MAX_LABEL = (154, 236, 160, 360, 160)  # cols 0-2: next x - x - 24 (node + 8 gap each side); col 3 is 360 (the widest free span), also capped per layout
_LAST = len(_COLS) - 1
_UNKNOWN_PARENT = "parent:unknown"


def _graph(payload):
    """(nodes {id: dict}, flows {(src, dst): n}) built from payload routes + network."""
    net = payload.get("network") or {"nodes": [], "edges": []}
    src = {n["id"]: n for n in net["nodes"]}
    names = payload.get("country_names", {})
    nodes: dict = {}
    flows: dict = {}

    def add(a, b, n):
        flows[(a, b)] = flows.get((a, b), 0) + n

    def node(nid, col, label, code=None):
        nodes.setdefault(nid, {"id": nid, "col": col, "label": label, "code": code})

    def country(t):
        key = t.split(":", 1)[1]
        code = None if key in ("withheld", "unknown") else key
        node(t, 4, src[t]["label"] if t in src else names.get(key, key), code)

    ids = {x["name"]: x["id"] for x in payload.get("providers", [])}
    ids.setdefault("Unknown company", "unknown")
    for r in payload.get("routes") or []:
        n = r["requests"]
        if n <= 0:
            continue
        pid = f"provider:{ids.get(r['provider'], 'unknown')}"
        tid, aid = f"tool:{r['tool']}", f"access:{r['access']}"
        node(tid, 0, r["tool"])
        node(aid, 1, r["access"])
        sn = src.get(pid, {})
        node(pid, 2, sn.get("label", r["provider"]), sn.get("country"))
        add(tid, aid, n)
        add(aid, pid, n)
    for e in net["edges"]:
        s, t, n = e["source"], e["target"], e["requests"]
        if n <= 0 or s not in nodes:
            continue
        if s.startswith("provider:") and t.startswith("parent:"):
            node(t, 3, src[t]["label"])
            add(s, t, n)
        elif s.startswith("provider:") and t.startswith("country:"):
            country(t)
            if s == "provider:unknown":
                add(s, t, n)
            else:  # no known parent: flows through the single grey "Parent unknown" node
                node(_UNKNOWN_PARENT, 3, "Parent unknown")
                add(s, _UNKNOWN_PARENT, n)
                add(_UNKNOWN_PARENT, t, n)
        elif s.startswith("parent:") and t.startswith("country:"):
            country(t)
            add(s, t, n)
    return nodes, flows


def _stack(flows, nid, s, side):
    return sum(max(_MIN, n * s) for (a, b), n in flows.items() if (a if side == "out" else b) == nid)


def _need(flows, ids, s):
    tot = sum(max(_stack(flows, i, s, "in"), _stack(flows, i, s, "out"), _MIN) for i in ids)
    return tot + _GAP * (len(ids) - 1)


def _trim(text, limit):
    if svg.text_width(text, _FS) <= limit:
        return text
    while text and svg.text_width(text + "…", _FS) > limit:
        text = text[:-1]
    return text.rstrip() + "…"


def _spread(want, step, lo, hi):
    """Minimal (least-squares) shifts so consecutive tops are >= step apart, within [lo, hi]."""
    blocks = []  # [sum of (want - k*step), count, first index]
    for k, w in enumerate(want):
        blocks.append([w - k * step, 1, k])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            b = blocks.pop()
            blocks[-1][0] += b[0]
            blocks[-1][1] += b[1]
    out = []
    for sm, cnt, k0 in blocks:
        for k in range(k0, k0 + cnt):
            out.append(sm / cnt + k * step)
    n = len(out)
    shift = max(0.0, lo - out[0]) if n else 0.0
    out = [v + shift for v in out]
    over = max(0.0, out[-1] - hi) if n else 0.0
    return [v - over for v in out]


def sankey_layout(payload) -> dict:
    nodes, flows = _graph(payload)
    if not flows:
        return {"nodes": [], "flows": [], "labels": [], "hidden": [], "scale": 0.0}
    for nid, nd in nodes.items():
        nd["requests"] = max(sum(n for (a, _), n in flows.items() if a == nid),
                             sum(n for (_, b), n in flows.items() if b == nid))
    ids_of = [[i for i, nd in nodes.items() if nd["col"] == c] for c in range(5)]
    # S2: country column first, then companies grouped by country, then barycentre columns
    withheld = [i for i in ids_of[4] if i.endswith(":withheld")]
    cc = sorted((i for i in ids_of[4] if i not in withheld),
                key=lambda i: (nodes[i]["code"] is None, -nodes[i]["requests"], nodes[i]["label"]))
    crank = {nodes[i]["code"]: k for k, i in enumerate(cc) if nodes[i]["code"] is not None}
    comp = sorted(ids_of[2], key=lambda i: (i == "provider:unknown", crank.get(nodes[i]["code"], len(cc)),
                                            -nodes[i]["requests"], nodes[i]["label"]))
    rank = {i: k for k, i in enumerate(comp)}
    rank.update({i: k for k, i in enumerate(cc)})

    def bary(i, other):
        fl = [(n, rank[o]) for (a, b), n in flows.items() for o in ((b if a == i else a),)
              if (a == i or b == i) and o in other and o in rank]
        tot = sum(n for n, _ in fl)
        return sum(n * r for n, r in fl) / tot if tot else 0.0

    par = sorted(ids_of[3], key=lambda i: (bary(i, set(comp)), nodes[i]["label"]))
    acc = sorted(ids_of[1], key=lambda i: (bary(i, set(comp)), nodes[i]["label"]))
    rank.update({i: k for k, i in enumerate(acc)})
    rt = sorted(ids_of[0], key=lambda i: (bary(i, set(acc)), nodes[i]["label"]))
    # Withheld goes next to its sources: before the first known country whose barycentre is greater
    srank = {i: k for k, i in enumerate(par)}
    for i, k in rank.items():
        if i in comp:
            srank.setdefault(i, k)

    def src_bary(i):
        fl = [(n, srank[a]) for (a, b), n in flows.items() if b == i and a in srank]
        tot = sum(n for n, _ in fl)
        return sum(n * r for n, r in fl) / tot if tot else None

    known = [i for i in cc if nodes[i]["code"] is not None]
    pos = len(known)  # just before "Unknown" by default
    for w in withheld:
        bw = src_bary(w)
        if bw is not None:
            pos = next((k for k, i in enumerate(known) if (src_bary(i) or 0.0) > bw), len(known))
        cc = cc[:pos] + [w] + cc[pos:]
        known = [i for i in cc if nodes[i]["code"] is not None]
        pos += 1
    cols = [rt, acc, comp, par, cc]
    lo, hi = 0.0, 100.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if all(_need(flows, ids, mid) <= _H for ids in cols if ids):
            lo = mid
        else:
            hi = mid
    s = lo
    out_nodes = []
    for c, ids in enumerate(cols):
        hs = {i: max(_stack(flows, i, s, "in"), _stack(flows, i, s, "out"), _MIN) for i in ids}
        gap = min(_MAX_GAP, (_H - sum(hs.values())) / (len(ids) - 1)) if len(ids) > 1 else 0.0
        y = float(_Y0)
        for nid in ids:
            nd = nodes[nid]
            nd.update(x=_X[c], y=y, w=_NW, h=hs[nid])
            y += hs[nid] + max(gap, _GAP)
            out_nodes.append(nd)
    # S1: order bands by the far node's centre
    def cy(i):
        return nodes[i]["y"] + nodes[i]["h"] / 2
    cur_out = {i: nodes[i]["y"] for i in nodes}
    cur_in = dict(cur_out)
    out_pos, in_pos = {}, {}
    for (a, b), n in sorted(flows.items(), key=lambda kv: (cy(kv[0][1]), nodes[kv[0][1]]["label"], kv[0][1])):
        out_pos[(a, b)] = cur_out[a]
        cur_out[a] += max(_MIN, n * s)
    for (a, b), n in sorted(flows.items(), key=lambda kv: (cy(kv[0][0]), nodes[kv[0][0]]["label"], kv[0][0])):
        in_pos[(a, b)] = cur_in[b]
        cur_in[b] += max(_MIN, n * s)
    out_flows = []
    for (a, b), n in sorted(flows.items(), key=lambda kv: (nodes[kv[0][0]]["col"], out_pos[kv[0]], kv[0])):
        h = max(_MIN, n * s)
        na, nb = nodes[a], nodes[b]
        # colour = destination country; mid-chart flows follow their company's country
        code = nb["code"] if nb["col"] in (2, 4) else na["code"]
        if code is None and na["col"] == 2:
            code = na["code"]
        x0, x1 = na["x"] + _NW, nb["x"]
        y0, y1, xm = out_pos[(a, b)], in_pos[(a, b)], (x0 + x1) / 2
        d = (f"M{x0:.1f} {y0:.1f}C{xm:.1f} {y0:.1f} {xm:.1f} {y1:.1f} {x1:.1f} {y1:.1f}"
             f"L{x1:.1f} {y1 + h:.1f}C{xm:.1f} {y1 + h:.1f} {xm:.1f} {y0 + h:.1f} {x0:.1f} {y0 + h:.1f}Z")
        out_flows.append({"source": a, "target": b, "requests": n, "d": d, "y0": y0, "y1": y1, "code": code,
                          "color": svg.color(code)})
    labels, hidden = [], []
    cwid = [svg.text_width(f"{_trim(n['label'], _MAX_LABEL[4] - svg.text_width(' · ' + svg.fmt_int(n['requests']), _FS))} · {svg.fmt_int(n['requests'])}", _FS)\
            for n in out_nodes if n["col"] == 4]
    maxlab = list(_MAX_LABEL)
    if cwid:  # parent labels must end >= 12 px before the widest country label
        maxlab[3] = min(maxlab[3], _X[4] - 8 - max(cwid) - 12 - (_X[3] + _NW + 8))
    step, top, bot = _LAB_H + 2, float(_Y0), float(_Y0 + _H)
    for c in range(5):
        col = [n for n in out_nodes if n["col"] == c]
        keep = list(col)
        while len(keep) * step - 2 > bot - top:  # cannot fit: drop the smallest node's label
            drop = min(keep, key=lambda n: (n["requests"], n["id"]))
            keep.remove(drop)
            hidden.append(f"{drop['label']} {svg.fmt_int(drop['requests'])}")
        want = [n["y"] + n["h"] / 2 - _LAB_H / 2 for n in keep]
        tops = _spread(want, step, top, bot - _LAB_H)
        for nd, ty in zip(keep, tops):
            num = svg.fmt_int(nd["requests"])
            text = f"{_trim(nd['label'], maxlab[c] - svg.text_width(' · ' + num, _FS))} · {num}"
            w = svg.text_width(text, _FS)
            lx = nd["x"] - 8 - w if c == _LAST else nd["x"] + _NW + 8
            mid, nmid = ty + _LAB_H / 2, nd["y"] + nd["h"] / 2
            leader = None
            if abs(ty - (nmid - _LAB_H / 2)) > 3:
                ex = nd["x"] - 3 if c == _LAST else nd["x"] + _NW + 3
                leader = (ex, nmid, lx + w + 3 if c == _LAST else lx - 3, mid)
            labels.append({"id": nd["id"], "text": text, "anchor": "end" if c == _LAST else "start",
                           "x": lx, "w": w, "y": ty, "h": _LAB_H, "leader": leader})
    return {"nodes": out_nodes, "flows": out_flows, "labels": labels, "hidden": hidden, "scale": s}


def sankey_svg(payload) -> str:
    lay = sankey_layout(payload)
    body = ['<g id="sankey-flows">']
    for i, f in enumerate(lay["flows"]):
        body.append(f'<path id="sankey-flow-{i}" d="{f["d"]}" fill="{f["color"]}" fill-opacity=".35"/>')
    body.append("</g>")
    for c, name in enumerate(_COLS):
        body.append(f'<text id="sankey-head-{c}" x="{_X[c] + (_NW if c == _LAST else 0)}" y="{_Y0 - 14}" '
                    f'font-size="14" font-weight="800" letter-spacing="1" fill="#5b5d69" '
                    f'text-anchor="{"end" if c == _LAST else "start"}">{svg.esc(name.upper())}</text>')
    for i, n in enumerate(lay["nodes"]):
        body.append(f'<rect id="sankey-node-{i}" x="{n["x"]}" y="{n["y"]:.1f}" width="{_NW}" '
                    f'height="{n["h"]:.1f}" fill="{svg.INK}"/>')
    for i, lb in enumerate(lay["labels"]):
        if lb["leader"]:
            x0, y0, x1, y1 = lb["leader"]
            body.append(f'<line id="sankey-leader-{i}" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                        f'stroke="#8B8D98" stroke-width=".75"/>')
        x = lb["x"] + lb["w"] if lb["anchor"] == "end" else lb["x"]
        body.append(f'<text id="sankey-label-{i}" class="lab" x="{x:.1f}" y="{lb["y"] + 12:.1f}" '
                    f'font-size="{_FS}" font-weight="600" fill="{svg.INK}" text-anchor="{lb["anchor"]}">'
                    f'{svg.esc(lb["text"])}</text>')
    if lay["hidden"]:
        for i, t in enumerate(svg.wrap("Also: " + ", ".join(dict.fromkeys(lay["hidden"])), 130)[:2]):
            body.append(f'<text id="sankey-also-{i}" x="56" y="{_Y0 + _H + 14 + i * 16}" font-size="14" '
                        f'fill="#5b5d69">{svg.esc(t)}</text>')
    return svg.card(payload, "sankey", 1080, 1350, "".join(body),
                    foot_extra="Band width = number of requests. Access method = how the tool reached the company.",
                    title="How your prompts flowed")


def section(payload: dict) -> str:
    if payload.get("empty") or not payload.get("total_requests") or not sankey_layout(payload)["flows"]:
        return ""
    return ('<section id="sankey"><h2>How your prompts flowed</h2>'
            + svg.figure("sankey", sankey_svg(payload)) + "</section>")
