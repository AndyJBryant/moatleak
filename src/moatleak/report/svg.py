"""Shared SVG helpers: palette, card-scoped ids, standalone share-card frame (stdlib only)."""
import html

COLORS = {"CN": "#E5484D", "US": "#3E8EF7", "EU": "#F5C518", "OTHER": "#30A46C", "GREY": "#8B8D98"}
INK = "#14151F"
BG = "#F6F4EE"
FONT_STACK = '-apple-system,"Segoe UI",Inter,Roboto,"Helvetica Neue",Arial,sans-serif'
EU_CODES = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_NONE = (None, "", "withheld", "unknown")


def country_key(code) -> str:
    if code in _NONE:
        return "GREY"
    if code in ("CN", "US"):
        return code
    return "EU" if code in EU_CODES else "OTHER"


def color(code) -> str:
    return COLORS[country_key(code)]


def fill(code, confidence, scope) -> str:
    if confidence == "hq_inferred" and code not in _NONE:
        return f"url(#{scope}-hatch-{country_key(code)})"
    return color(code)


def hatch_defs(scope: str) -> str:
    """45-degree stripe patterns, ids prefixed with the card id (hidden SVGs don't resolve foreign ids)."""
    return "".join(
        f'<pattern id="{scope}-hatch-{k}" width="10" height="10" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><rect width="10" height="10" fill="{v}" fill-opacity=".20"/>'
        f'<rect width="5" height="10" fill="{v}"/></pattern>' for k, v in COLORS.items())


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fmt_int(n) -> str:
    return f"{int(n):,}"


def short_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {_MONTHS[int(m) - 1]}"


def period_label(payload) -> str:
    a, b = payload.get("period") or [None, None]
    if not a or not b:
        return ""
    ya, yb = a[:4], b[:4]
    if a == b:
        return f"{short_date(a)} {ya}"
    if ya == yb:
        return f"{short_date(a)} – {short_date(b)} {yb}"
    return f"{short_date(a)} {ya} – {short_date(b)} {yb}"


def wrap(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines


def text_width(text: str, size: float, weight: int = 600) -> float:
    """Approximate rendered width: average glyph ~0.56*size at weight 600, ~0.6*size at 800+.
    Only for collision checks; not exact."""
    return len(text) * size * (0.6 if weight >= 800 else 0.56)


def footnote(payload, extra: str = "") -> str:
    note = payload["coverage_note"]
    if extra and note in extra:
        return extra
    return f"{extra} {note}".strip()


_STYLE = (f"svg text{{font-family:{FONT_STACK}}}"
          f"text.lab{{paint-order:stroke;stroke:{BG};stroke-width:5px;stroke-linejoin:round}}")
_DOT = ("<g>" + "".join(
    f'<path d="M11 11 L{x} {y} A11 11 0 0 1 {x2} {y2} Z" fill="{COLORS[k]}"/>'
    for k, (x, y, x2, y2) in {"CN": (11, 0, 22, 11), "US": (22, 11, 11, 22),
                              "OTHER": (11, 22, 0, 11), "EU": (0, 11, 11, 0)}.items())
    + f'<circle cx="11" cy="11" r="5" fill="{INK}"/></g>')


def card(payload, card_id, w, h, body, *, foot_extra="", dark=False, title=None, foot_w=None,
         background=None) -> str:
    """background: optional (fill, extra_defs) replacing the flat page fill (e.g. a gradient)."""
    fg = "#FFFFFF" if dark else INK
    sub = "rgba(255,255,255,.62)" if dark else "#5b5d69"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'class="card-svg" data-card="{esc(card_id)}">',
        f"<style>{_STYLE}</style><defs>{hatch_defs(card_id)}{background[1] if background else ''}</defs>",
        f'<rect width="{w}" height="{h}" fill="{background[0] if background else INK if dark else BG}"/>',
        f'<g transform="translate(56 48)">{_DOT}<text x="34" y="19" font-size="30" font-weight="900" '
        f'letter-spacing="-.5" fill="{fg}">moatleak</text></g>',
        f'<text x="{w - 56}" y="70" text-anchor="end" font-size="21" font-weight="600" '
        f'fill="{fg}">{esc(period_label(payload))}</text>',
    ]
    if title:
        size = 54
        for i, line in enumerate(wrap(title, int((w - 112) / (size * 0.6)))):
            parts.append(f'<text x="56" y="{150 + i * 60}" font-size="{size}" font-weight="900" '
                         f'letter-spacing="-1.5" fill="{fg}">{esc(line)}</text>')
    parts.append(body)
    lines = wrap(footnote(payload, foot_extra), int((foot_w or w - 112) / (15 * 0.52)))
    y0 = h - 34 - (len(lines) - 1) * 20
    for i, line in enumerate(lines):
        parts.append(f'<text x="56" y="{y0 + i * 20}" font-size="15" fill="{sub}">{esc(line)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def safe_url(u) -> bool:
    """Only http(s) sources become links (log/registry-derived strings must not yield javascript: hrefs)."""
    return isinstance(u, str) and u.startswith(("https://", "http://"))


def figure(card_id, svg, caption="") -> str:
    m = svg[: svg.index(">")]
    w = m.split(' width="')[1].split('"')[0]
    h = m.split(' height="')[1].split('"')[0]
    cap = f"<figcaption>{esc(caption)}</figcaption>" if caption else ""
    return (f'<figure class="card" id="card-{esc(card_id)}" data-w="{w}" data-h="{h}">'
            f"{svg}{cap}</figure>")
