## Summary

What does this change, and why?

## Checklist

- [ ] `scripts/check.sh` passes
- [ ] No real logs, ids, prompts, paths or emails in tests or fixtures

## Registry changes (delete this block if the PR does not touch `src/moatleak/data/`)

- [ ] Every new or changed non-"unknown" claim has a `[[sources]]` entry with a source
      URL and a verbatim `evidence` quote found at that URL
- [ ] The source URLs are listed in this PR description
- [ ] No inferred parents (investors are not parents)
- [ ] `legal_regimes` matches `hq.country` and `ultimate_parent_country`
- [ ] The registry lint passes (see CONTRIBUTING.md)
