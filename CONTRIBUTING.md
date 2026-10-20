# Contributing to moatleak

## Dev setup

Python 3.11 or newer.

```
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
scripts/check.sh
```

`scripts/check.sh` runs pytest, then a privacy scan over tracked files (home-directory
paths, real-looking ids, non-`@example.com` emails, key patterns) and a second
key-pattern scan. It must pass before you open a PR. Stage your files first: the scan
covers tracked and staged files only.

## Ground rules

- `src/` uses the standard library only. Dev tooling is pytest only.
- Network code lives only in `src/moatleak/connectors/`. A test enforces that
  `scan` and `sources` never import it.
- Test fixtures are synthetic. No real logs, ids, prompts or paths. Emails use
  `@example.com`. Key-like strings are built at runtime by concatenation, never
  written out whole.
- Use conventional commit messages (`feat:`, `fix:`, `docs:`, `test:`).

## Registry contributions

The registry is one TOML file per provider in
[`src/moatleak/data/providers/`](src/moatleak/data/providers/). Copy the structure
of an existing file such as `deepinfra.toml`. The file name must equal `id`
(lowercase letters, digits, hyphens). Example with invented values:

```toml
id = "example-inference"
display_name = "Example Inference"
openrouter_names = ["Example Inference"]
openrouter_slug = "example-inference"
aliases = ["Example Inference, Inc."]
legal_entity = "Example Inference, Inc."
parent = "Example Inference, Inc."   # independent
parent_id = "example-inference"      # independent
parent_display_name = "Example Inf." # max 24 characters
ultimate_parent_country = "US"
hq = { country = "US", subdivision = "US-CA" }
serving_regions = [ { region = "US", basis = "vendor_docs" } ]
cloud_host = "self"
legal_regimes = ["US-CLOUD-ACT", "US-FISA-702"]
retention = "Short factual summary of the stated retention policy."
recognisable = false
last_verified = "2026-01-01"

[[sources]]
url = "https://example.com/privacy"
claim = "legal_entity"
checked = "2026-01-01"
evidence = "provided by Example Inference, Inc., a Delaware corporation"
```

Rules:

- Every non-"unknown" value among `legal_entity`, `parent`, `ultimate_parent_country`,
  `hq`, `serving_regions`, `cloud_host` and `retention` needs a `[[sources]]` entry
  with `url`, `claim` (the field name; `parent_id` is also allowed), `checked`
  (YYYY-MM-DD) and `evidence`. `evidence` is a verbatim quote found at that URL.
- `serving_regions[].basis` is one of `openrouter_api`, `vendor_docs`, `hq`.
- Prefer primary sources: company filings and the vendor's own legal pages, not press.
- Use `"unknown"` rather than a guess.
- Never infer a parent. An investor is not a parent. A parent needs a source that
  shows ownership or control. An independent company lists itself as its own parent,
  with a source naming the legal entity and its HQ.
- `legal_regimes` must equal the regimes that follow from `hq.country` and
  `ultimate_parent_country`: US gives `US-CLOUD-ACT` and `US-FISA-702`; CN gives
  `CN-NIL-ART7` and `CN-DSL`; an EU member state gives `EU-GDPR`; SG gives `SG-PDPA`;
  `unknown` gives none. Take the union of both countries. A test checks this.
- A country not listed above needs a regime entry in `src/moatleak/data/regimes.toml`, an
  entry in the `REGIMES_FOR` map in `tests/test_registry_seed.py`, and a name in
  `COUNTRY_NAMES` in `src/moatleak/headlines.py`. Open an issue or PR discussion first.
- Country codes are ISO-2 (or `"unknown"`); `subdivision` looks like `US-CA`.

Check your change. The lint returns a list of problems, and `[]` means clean:

```
.venv/bin/python -c "from moatleak.registry import Registry; print(Registry.load().lint())"
scripts/check.sh
```

`tools/registry_drift.py` compares a saved OpenRouter provider list (the JSON from
`/api/v1/providers`, saved by you) against the registry. It makes no network calls:

```
.venv/bin/python tools/registry_drift.py --from-file PATH [--registry DIR]
```

It lists providers missing from the registry, HQ and datacenter mismatches, and
registry providers absent from the list.

## Readers and connectors

- A reader lives in `src/moatleak/readers/` and follows the `Reader` protocol there:
  `detect`, `iter_rows`, and `iter_content`. Readers are read-only and fail soft
  (a bad file must not stop the scan). `iter_content` is called only with
  `--scan-content`. Add synthetic fixtures and tests.
- A connector lives in `src/moatleak/connectors/`. It needs explicit user consent
  (show what will be called and ask first), and it must stay out of the scan path.

## Licensing of contributions

Code is under Apache-2.0 ([LICENSE](LICENSE)). Registry data in `src/moatleak/data/`
is under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
([LICENSE-DATA](LICENSE-DATA)). By contributing you license your work under the
matching licence.
