"""Non-visual HTML sections: header, ledger, methodology, CTA."""
import base64
from importlib import resources

from moatleak.report.svg import COLORS, country_key, esc, safe_url, fmt_int, period_label, short_date

EMPTY_MESSAGE = "No AI usage with provider data was found in the scanned logs."


_MARK = ('<svg aria-hidden="true" viewBox="0 0 22 22" width="24" height="24">'
         '<path d="M11 11 L11 0 A11 11 0 0 1 22 11 Z" fill="#E5484D"/>'
         '<path d="M11 11 L22 11 A11 11 0 0 1 11 22 Z" fill="#3E8EF7"/>'
         '<path d="M11 11 L11 22 A11 11 0 0 1 0 11 Z" fill="#30A46C"/>'
         '<path d="M11 11 L0 11 A11 11 0 0 1 11 0 Z" fill="#F5C518"/>'
         '<circle cx="11" cy="11" r="5" fill="#14151F"/></svg>')


def _logo_uri(name: str) -> str:
    data = (resources.files("moatleak.report") / "assets" / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def header(payload: dict) -> str:
    out = ['<header id="header">',
           f'<div class="brand">{_MARK}<span class="brand__word">moatleak</span>'
           '<span class="brand__by">by</span>'
           f'<img class="brand__hl" alt="Horizen Labs" width="400" height="96" '
           f'src="{_logo_uri("horizen-labs-logo.png")}"></div>',
           '<h1>Your AI inference network</h1>']
    period = period_label(payload)
    if period:
        out.append(f'<p class="period">{esc(period)}</p>')
    if payload.get("empty"):
        out.append(f'<p class="empty">{esc(EMPTY_MESSAGE)}</p>')
    else:
        out.append('<h2 class="highlights">Highlights</h2><ul class="headlines">')
        for h in payload["headlines"]:
            foot = f'<small>{esc(h["footnote"])}</small>' if h.get("footnote") else ""
            out.append(f'<li>{esc(h["text"])}{foot}</li>')
        out.append("</ul>")
        e = payload["earlier"]
        if e["requests"] > 0:
            out.append(
                f'<p class="earlier">Before {esc(short_date(payload["period"][0]))}: '
                f'{fmt_int(e["requests"])} earlier requests since {esc(short_date(e["first"]))} '
                f'{esc(e["first"][:4])}; {fmt_int(e["unattributed_requests"])} of them have no recorded company.</p>')
    out.append("</header>")
    return "".join(out)


def _basis(p: dict, labels: dict) -> str:
    conf: dict = {}
    for loc in p["locations"]:
        conf[loc["confidence"]] = conf.get(loc["confidence"], 0) + loc["requests"]
    return ", ".join(f"{esc(labels.get(c, c))} {fmt_int(n)}"
                     for c, n in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0])))


def _country_cell(p: dict, names: dict) -> str:
    if p["country"]:
        return esc(names.get(p["country"], p["country"]))
    confs = {loc["confidence"] for loc in p["locations"]}
    return "withheld" if "withheld" in confs else "unknown"


def ledger(payload: dict) -> str:
    labels = payload["confidence_labels"]
    rows = []
    for p in payload["providers"]:
        if p["id"] == "unknown":
            name = "??"
        else:
            name = esc(p["name"])
        if p["parent"]:
            parent = esc(p["parent"])
            if safe_url(p.get("parent_source")):
                parent = f'<a href="{esc(p["parent_source"])}" rel="noopener">{parent}</a>'
        else:
            parent = "unknown"
        first = esc(short_date(p["first_seen"])) if p["first_seen"] else "—"
        rows.append(f"<tr><td>{name}</td><td>{parent}</td>"
                    f'<td>{_country_cell(p, payload["country_names"])}</td>'
                    f"<td>{_basis(p, labels)}</td>"
                    f'<td class="num">{fmt_int(p["requests"])}</td><td>{first}</td></tr>')
    return ('<section id="ledger"><h2>Every company that processed your prompts</h2>'
            '<div class="tablewrap"><table><thead><tr><th>Company</th><th>Parent group</th>'
            "<th>Country</th><th>Location basis</th><th>Requests</th><th>First seen</th></tr></thead>"
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def content(payload: dict) -> str:
    c = payload.get("content")
    if c is None:
        return ""
    n = fmt_int(c["scanned_conversations"])
    names = payload.get("country_names", {})
    out = ['<section id="content"><h2>What your prompts contained</h2>'
           f'<p>Local scan of {n} conversations in this period (regular expressions, taxonomy '
           f'v{esc(c["taxonomy_version"])}). No prompt text was stored or sent; only category labels.</p>']
    if c["scanned_conversations"] == 0:
        out.append("<p>No conversations in this period had prompt text to scan.</p>")
    elif not c["classes"]:
        out.append(f"<p>Nothing sensitive detected by the local scan in {n} conversations.</p>")
    for k in c["classes"]:
        cnt, early = k["conversations"], k.get("earlier_conversations", 0)
        bits = []
        if cnt > 0:
            bits.append(f'<b>{esc(k["label"])}</b>: {fmt_int(cnt)} conversation{"" if cnt == 1 else "s"}')
        else:
            bits.append(f'<b>{esc(k["label"])}</b>')
        if early > 0:
            bits.append(f'<small>+{fmt_int(early)} in earlier history (companies not recorded)</small>')
        if cnt > 0 and k["companies"]:
            chips = "".join(
                f'<span class="chip" style="display:inline-block;margin:2px 6px 2px 0;padding:2px 10px;'
                f'border-radius:12px;border:2px solid {_cc(x.get("country"))}">'
                f'{esc(x["name"])} ({esc(names.get(x["country"], x["country"]) if x.get("country") else "??")})</span>'
                for x in k["companies"])
            bits.append(f'<div>Conversations handled by: {chips}</div>')
        out.append(f'<div class="content-row" style="margin:12px 0">{"".join(bits)}</div>')
    out.append("</section>")
    return "".join(out)


def _cc(code) -> str:
    return COLORS[country_key(code)]


def methodology(payload: dict) -> str:
    labels, total = payload["confidence_labels"], payload["total_requests"]
    out = ['<section id="methodology"><h2>How this was measured</h2>']
    conf = payload["footprint"]["confidence"]
    if conf:
        out.append("<h3>Location confidence</h3><table><thead><tr><th>Basis</th><th>Requests</th>"
                   "<th>Share</th></tr></thead><tbody>")
        for c, n in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0])):
            share = f"{n / total * 100:.1f}%" if total else "0%"
            out.append(f'<tr><td>{esc(labels.get(c, c))}</td><td class="num">{fmt_int(n)}</td>'
                       f'<td class="num">{share}</td></tr>')
        out.append("</tbody></table>")
    out.append(f'<p>{esc(payload["coverage_note"])}</p>')
    out.append(f'<p>{esc(payload["timeline"]["footnote"])}</p>')
    if payload["withheld"]:
        out.append("<h3>Withheld locations</h3><ul>")
        for w in payload["withheld"]:
            dates = (esc(short_date(w["first"])) if w["first"] == w["last"]
                     else f'{esc(short_date(w["first"]))} – {esc(short_date(w["last"]))}')
            out.append(f'<li>{esc(w["provider"])}: {fmt_int(w["requests"])} requests via '
                       f'{esc(", ".join(w["tools"]))}, {dates}</li>')
        out.append("</ul>")
    if payload.get("content") is not None:
        c = payload["content"]
        out.append("<h3>Content scan (Tier 1)</h3><p>A local regular-expression scan of your prompts "
                   f'(taxonomy v{esc(c["taxonomy_version"])}); only category labels are kept, never prompt text. '
                   "The unit is a conversation: a conversation counts if any of its prompts matched; "
                   "it is listed under every company that handled that conversation in the period; a company that "
                   "served only earlier turns may not have seen the matching text.</p>")
    out.append("<p>Network clues such as IP geolocation are not location evidence.</p>"
               "<p>No card claims a datacenter.</p>")
    if payload["footprint"]["regimes"]:
        out.append("<h3>Legal regimes</h3><ul>")
        for r in payload["footprint"]["regimes"]:
            link = (f' <a href="{esc(r["source"])}" rel="noopener">source</a>' if safe_url(r.get("source")) else "")
            out.append(f'<li><b>{esc(r["name"])}</b>: {esc(r["summary"])}{link}</li>')
        out.append("</ul>")
    out.append(f'<p class="versions">moatleak {esc(payload["tool_version"])} · registry '
               f'{esc(payload["registry_version"])}</p></section>')
    return "".join(out)


def cta(payload: dict, url: str) -> str:
    return (
        '<section id="cta"><div class="cta-band">'
        '<p class="cta-by">moatleak by <img alt="Horizen Labs" width="400" height="96" '
        f'src="{_logo_uri("horizen-labs-logo-white.png")}"></p>'
        '<h2>Deploy Sovereign AI at your company.</h2>'
        '<p class="cta-body">moatleak shows where your prompts go today. '
        'Horizen Labs helps companies decide where they go next.</p>'
        f'<p><a class="cta-btn" href="{esc(url)}" target="_blank" rel="noopener">'
        'Get Sovereign AI at your company</a></p>'
        '<p class="cta-small">Opens a contact form hosted by Pipedrive. '
        'Nothing from your report is sent.</p></div></section>')
