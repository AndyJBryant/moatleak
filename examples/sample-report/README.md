# Sample report

A real report generated from the maintainer's own Hermes and Claude Code logs, covering 22 Sep – 7 Oct 2026. It was produced with:

```
moatleak scan --no-models --scan-content
```

Open [`report.html`](report.html) in a browser. It is a single offline file.

## What it contains

- Counts of prompts, companies, parent groups and countries, with dates, first-seen dates and daily activity.
- The tools (Hermes, Claude Code) and access methods (OpenRouter, Anthropic API (direct)) with their counts.
- A one-line summary of older history before the per-call window (request count and start date).
- The content scan shows category counts only (for example "Personal data 3").

## What it does not contain

- No prompts or matched text.
- No model names (`--no-models`).
- No session, request or message ids, and no file paths.

## Note

The call-to-action and project links in this sample currently point to Horizen Labs (horizenlabs.io) until the project site exists.

## Thumbnails

[![Hero card](hero.png)](report.html)
[![Sankey card](sankey.png)](report.html)

Other cards exported from the same report: [`hero-wide.png`](hero-wide.png), [`hero-radial.png`](hero-radial.png), [`footprint.png`](footprint.png), [`story-content.png`](story-content.png).
