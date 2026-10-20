"""Rank country-neutral headlines from a findings Summary."""
from dataclasses import dataclass
from datetime import date, timedelta

COUNTRY_NAMES = {
    "US": "United States", "CN": "China", "SG": "Singapore", "FR": "France",
    "GB": "United Kingdom", "DE": "Germany", "IE": "Ireland", "NL": "Netherlands",
    "LU": "Luxembourg", "SE": "Sweden", "FI": "Finland", "CH": "Switzerland",
    "CA": "Canada", "JP": "Japan", "KR": "South Korea", "IN": "India", "TW": "Taiwan",
    "HK": "Hong Kong", "IL": "Israel", "AU": "Australia", "AE": "United Arab Emirates",
    "EU": "European Union",
}

CONF_LABELS = {
    "reported": "reported by provider", "documented": "documented",
    "hq_inferred": "HQ-inferred", "withheld": "withheld", "unknown": "unknown",
}


@dataclass
class Headline:
    kind: str
    text: str
    value: int
    names: list[str]
    footnote: str


def country_name(code: str) -> str:
    return COUNTRY_NAMES.get(code, code)


COUNTRY_ARTICLE = {"US", "GB", "NL", "AE", "EU"}


def country_phrase(code: str) -> str:
    return ("the " if code in COUNTRY_ARTICLE else "") + country_name(code)


def pct(share: float) -> str:
    return "<1" if 0 < share < 0.005 else str(round(share * 100))


def _by_requests(counter) -> list[str]:
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def _countries(s):
    known = {k: v for k, v in s.countries.items() if k not in ("withheld", "unknown")}
    if not known or not s.total_requests:
        return None
    order = _by_requests(known)[:3]
    top = s.country_share[order[0]]
    if top < 0.20:
        return None
    ps = [pct(s.country_share[c]) for c in order]
    nm = [country_name(c) for c in order]
    ph = [country_phrase(c) for c in order]
    text = f"{ps[0]}% of your prompts were processed by companies headquartered in {ph[0]}"
    if len(order) == 2:
        text += f", {ps[1]}% in {ph[1]}"
    elif len(order) == 3:
        text += f", {ps[1]}% in {ph[1]} and {ps[2]}% in {ph[2]}"
    text += "."
    basis = ", ".join(f"{CONF_LABELS.get(c, c)} {pct(s.confidence[c] / s.total_requests)}%"
                      for c in _by_requests(s.confidence))
    return Headline("countries", text, round(top * 100), nm,
                    f"Location basis: {basis}. {s.coverage_note}")


def _extent(s):
    if s.n_providers < 3:
        return None
    n, p, c = s.n_providers, s.n_parents_known, s.n_countries_known
    clauses = [f"{n} companies."]
    if p:
        clauses.append("1 parent group." if p == 1 else f"{p} parent groups.")
    if c:
        clauses.append("1 country." if c == 1 else f"{c} countries.")
    names = _by_requests(s.providers)
    unknown = [x for x in names if s.provider_info.get(x, {}).get("parent_id") is None]
    foot = ""
    if unknown:
        k = len(unknown)
        foot += (f"Parent group unknown for {'1 company' if k == 1 else f'{k} companies'}: "
                 f"{', '.join(unknown)}. ")
    foot += "A company not owned by another group counts as its own parent group. " + s.coverage_note
    return Headline("extent", " ".join(clauses), n, names, foot)


def _names(s, registry):
    rec = [x for x in _by_requests(s.providers)
           if registry.providers[s.provider_info[x]["provider_id"]].get("recognisable", False)]
    shown = []  # (label, provider, is_parent)
    seen = set()
    for x in rec:
        info = s.provider_info[x]
        is_parent = info["parent_id"] is not None and info["parent_id"] != info["provider_id"]
        label = (info.get("parent_display") or info["parent"]) if is_parent else x
        if label in seen:
            continue
        seen.add(label)
        shown.append((label, x, is_parent))
        if len(shown) == 3:
            break
    if not shown:
        return None
    labels = [t[0] for t in shown]
    text = "Including " + (", ".join(labels[:-1]) + " and " + labels[-1] if len(labels) > 1
                           else labels[0]) + "."
    sentences = " ".join(f"{x} is owned by {s.provider_info[x]['parent']}."
                         for label, x, par in shown if par)
    foot = (sentences + " Ownership from the moatleak registry (sourced).").lstrip()
    return Headline("names", text, len(labels), labels, foot)


def _spread(s):
    m = s.max_session_spread
    if not m or m["n_providers"] < 2:
        return None
    c = m["n_countries"]
    text = f"One conversation was split across {m['n_providers']} companies" + \
        (f" in {c} countries" if c >= 2 else "") + "."
    foot = (f"{s.multi_provider_sessions} of {s.sessions_with_provider} conversations with "
            f"per-call provider data used more than one company. {s.coverage_note}")
    return Headline("session_spread", text, m["n_providers"], list(m["providers"]), foot)


def _growth(s):
    # Strict count: companies first seen on the window's first day may have served the user
    # before per-call data starts, so they are not "new".
    dates = {n: date.fromisoformat(d) for n, d in s.first_seen.items() if d > s.period[0]}
    if len(dates) < 3:
        return None
    best = None
    for start in sorted(set(dates.values())):
        members = [n for n, d in dates.items() if start <= d <= start + timedelta(days=13)]
        if best is None or len(members) > len(best):
            best = members
    members = best
    k = len(members)
    if k < 3:
        return None
    members.sort(key=lambda n: (dates[n], n))
    d = (dates[members[-1]] - dates[members[0]]).days + 1
    already = sorted(n for n, fd in s.first_seen.items() if fd == s.period[0])
    foot = (f"Not counted: {', '.join(already)}, already serving you on {s.period[0]}, "
            f"when per-call provider data starts. {s.coverage_note}" if already else s.coverage_note)
    return Headline("growth", f"{k} new companies joined your network in {d} days.", k, members, foot)


def _withheld(s):
    cands = {n: w for n, w in s.withheld.items() if w["requests"] >= 20}
    if not cands:
        return None
    name = sorted(cands, key=lambda n: (-cands[n]["requests"], n))[0]
    w = cands[name]
    return Headline("withheld", f"{name} withheld the location of {w['requests']} of your prompts.",
                    w["requests"], [name],
                    f"{', '.join(w['tools'])}, {w['first']} to {w['last']}: "
                    "the provider reported the location as not available.")


def headlines(summary, registry) -> list[Headline]:
    if not summary.total_requests:
        return []
    out = (_countries(summary), _extent(summary), _names(summary, registry),
           _spread(summary), _growth(summary), _withheld(summary))
    return [h for h in out if h is not None]
