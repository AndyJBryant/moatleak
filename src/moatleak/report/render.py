"""render(payload) -> one self-contained HTML string (no network, no external assets)."""
import html
import json
from importlib import resources
from string import Template

from moatleak.report import footprint, hero, receipt, sankey, sections, story, timeline
from moatleak.report.svg import period_label

# interim link until the project site exists; plain link, no user data
CTA_URL = "https://horizenlabs.io/?ref=moatleak"

# project site; used by "Copy text"
PROJECT_URL = "https://moatleak.ai/"

_TITLE = "moatleak · your AI inference network"


def render(payload: dict) -> str:
    if payload.get("empty"):
        parts = [sections.header(payload), sections.methodology(payload), sections.cta(payload, CTA_URL)]
    else:
        parts = [sections.header(payload), hero.section(payload), footprint.section(payload),
                 timeline.section(payload), story.section(payload), receipt.section(payload),
                 sankey.section(payload), sections.content(payload), sections.ledger(payload), sections.methodology(payload),
                 sections.cta(payload, CTA_URL)]
    period = period_label(payload)
    title = f"{_TITLE} · {period}" if period else _TITLE
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    tpl = (resources.files("moatleak.report") / "template.html").read_text(encoding="utf-8")
    tpl = tpl.replace("<body>", f'<body data-project-url="{html.escape(PROJECT_URL)}">', 1)
    return Template(tpl).substitute(title=html.escape(title), body="\n".join(parts), payload=data)
