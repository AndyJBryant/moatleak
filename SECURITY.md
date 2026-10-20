# Security policy

## What moatleak touches

- **Reads, read-only:** local AI-tool records. Hermes logs, the Hermes `state.db`
  (opened as `file:{path}?mode=ro&immutable=1`) and Claude Code transcripts.
- **Writes:** only to the `--out` directory (default `./moatleak-report`):
  `report.html`, `ledger.csv`, `summary.json`, `ledger.db`.
- **Network:** none. The package makes no network calls and contains no network code.
- **Prompt text:** never written to any output. `--scan-content` reads conversation
  text locally and keeps only category counts.
- **Report:** one HTML file. The page itself loads no remote resources.

## In scope

Please report anything that:

- makes moatleak use the network in any way (any network activity is in scope);
- puts prompt text, matched text, or keys into any output file;
- writes outside `--out`, or into the directories being scanned;
- makes the HTML report load a remote resource.

## How to report

Please use GitHub's private vulnerability reporting (Security tab → Report a
vulnerability) on this repository. Do not open a public issue for security problems.

## Supported versions

The latest 0.1.x release.

## Check the offline claim yourself

On Linux, run the scan inside an empty network namespace. If anything tried to reach
the network, it would fail:

```
unshare -rn moatleak scan
```

If `unshare` itself is refused (some distributions restrict unprivileged user
namespaces), that is not evidence of network use. Use a VM or container with
networking disabled instead.

On macOS, turn on airplane mode and run `moatleak scan`. Treat this as a sanity
check, not proof.
