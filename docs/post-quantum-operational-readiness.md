# Post-Quantum Operational Readiness Dashboard

The operational readiness dashboard is a read-only aggregator for the scheduled
testnet CHCQ activation at height `30000`. It answers one operational question:

`Is Chipcoin operationally ready for Post-Quantum activation?`

It does not mine, submit transactions, mutate node state, change consensus
parameters, enable browser PQ signing, or modify the explorer/API.

## Commands

```bash
python -m chipcoin.tools.pq_operational_readiness
chipcoin pq-operational-readiness
chipcoin pq-operational-readiness --json
chipcoin pq-operational-readiness --no-network --json
chipcoin pq-operational-readiness --html pq-readiness.html --output pq-readiness.json
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | READY |
| 1 | DEGRADED |
| 2 | NOT READY |
| 3 | UNKNOWN |
| 4 | command/configuration error |

## Architecture

The central implementation is `src/chipcoin/pq/operational_readiness.py`.
The CLI wrapper is `src/chipcoin/tools/pq_operational_readiness.py`, with the
top-level alias `chipcoin pq-operational-readiness`.

The dashboard aggregates existing components instead of reimplementing them:

- `pq-audit-report` static metadata;
- `pq-smoke` availability and artifact status;
- `pq-dress-rehearsal` JSON report;
- `pq-benchmark` data embedded in the latest dress rehearsal report;
- public read-only node API endpoints such as `/v1/status`, `/v1/blocks`, and
  `/v1/peers/public`;
- browser PQ build/CI artifacts such as `.github/workflows/browser-pq-chromium.yml`.

## Data Sources

Network data comes from the configured read-only API URL. By default this is
`http://127.0.0.1:28081`, suitable for an operator running the command next to a
node. Public URLs can be supplied with `--api-url`.

Static PQ readiness data comes from the repository and includes:

- activation height;
- scheme ID and scheme name;
- CHCQ address constants;
- ML-DSA key/signature lengths;
- node-local PQ policy limits;
- availability of smoke, benchmark, audit and dress rehearsal tooling.

External service checks are read-only HTTP GET requests for the website,
explorer, faucet, snapshot endpoint, browser wallet page and documentation page.
They are skipped when `--no-network` is set.

## Status Scoring

The dashboard does not use an opaque numeric score. It evaluates critical gates,
major signals and informational signals.

`READY` means all critical gates pass and no major signal fails or is unknown.

`DEGRADED` means all critical gates pass, but at least one major signal has a
warning, stale data, or unknown operational status.

`NOT READY` means at least one critical gate fails.

`UNKNOWN` means there is not enough data to evaluate an essential critical gate.
For example, `--no-network` intentionally produces `UNKNOWN` unless sufficient
cached/live data is supplied elsewhere.

Critical gates include:

- API reachable;
- chain synced;
- activation configuration correct;
- ML-DSA backend available;
- audit metadata available;
- latest dress rehearsal passed.

Major signals include:

- sufficient operational peers;
- acceptable height spread;
- API latency below threshold;
- Chromium runtime CI present;
- PQ metrics available;
- explorer reachable.

Peer version distribution is reported as `UNKNOWN` unless the API exposes the
data. The dashboard does not invent upgrade percentages.

## Thresholds

Thresholds live in `OperationalReadinessThresholds` and can be overridden through
configuration:

- `min_operational_peers`;
- `max_height_spread`;
- `max_api_latency_ms`;
- `max_chain_age_seconds`;
- `max_miner_top_share_percent`;
- `max_pq_verify_failure_count`.

Freshness windows live in `OperationalReadinessFreshness`:

- network/API data: minutes;
- smoke: 24 hours;
- readiness suite: 7 days;
- dress rehearsal: 14 days;
- benchmark: 30 days.

Audit freshness is commit-sensitive: the static audit report is tied to the
current code rather than treated as stale only because time passed.

## Countdown And ETA

The activation countdown uses the testnet activation height from
`pq-audit-report`, not a separate hardcoded value. It reports:

- current height;
- blocks remaining;
- progress percentage;
- average and median recent block interval;
- an ETA label and confidence.

ETA is intentionally approximate. If timestamps are unavailable, intervals are
too sparse, or block times are irregular, the dashboard reports `UNKNOWN` or low
confidence instead of false precision.

If current height is at or beyond activation height, remaining blocks are `0`
and ETA is `activation reached`.

## Zero Versus Unavailable

The JSON schema distinguishes real zero from unavailable data. PQ metrics use:

```json
{
  "value": null,
  "availability": "unavailable"
}
```

for missing metrics. A value of `0` is only used when the source explicitly
reports zero.

Before activation, zero recent PQ activity is expected and is annotated as:

`Expected before activation`

It is not classified as a failure.

## Outputs

JSON output is schema-versioned:

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "commit": "...",
  "network": "testnet",
  "status": "READY",
  "activation": {},
  "chain": {},
  "network_readiness": {},
  "pq_features": {},
  "operational_tests": {},
  "pq_metrics": {},
  "pq_activity": {},
  "services": {},
  "warnings": [],
  "failures": [],
  "unknowns": [],
  "reasons": []
}
```

HTML output is a static standalone file with no CDN, no tracking and no required
JavaScript. Dynamic data is escaped before rendering.

Markdown output is suitable for daily reports, GitHub issues, Telegram updates
and operator notes.

## Storage

Use `--output-dir` for cron/systemd operation:

```bash
chipcoin pq-operational-readiness \
  --config /etc/chipcoin/pq-readiness.toml \
  --output-dir /var/lib/chipcoin/pq-readiness
```

The dashboard writes atomically:

- `latest.json`;
- `latest.html`;
- `latest.md`;
- `history/YYYY-MM-DDTHH-MM-SSZ.json`.

The default command does not persist output into the repository unless paths are
explicitly supplied.

## Configuration

Optional TOML configuration:

```toml
api_url = "https://testnet-api.chipcoinprotocol.com"
timeout_seconds = 5
block_interval_window = 20
output_dir = "/var/lib/chipcoin/pq-readiness"
minimum_compatible_version = "operator-defined"

[thresholds]
min_operational_peers = 5
max_height_spread = 3
max_api_latency_ms = 2000

[freshness]
smoke_seconds = 86400
dress_rehearsal_seconds = 1209600
```

Precedence is:

`CLI > environment > config file > defaults`

Supported environment variables include:

- `CHIPCOIN_PQ_READINESS_API_URL`;
- `CHIPCOIN_PQ_READINESS_TIMEOUT`;
- `CHIPCOIN_PQ_READINESS_NO_NETWORK`;
- `CHIPCOIN_PQ_READINESS_BLOCK_WINDOW`;
- `CHIPCOIN_PQ_READINESS_OUTPUT_DIR`.

## Cron/Systemd

Example systemd unit:

```ini
[Unit]
Description=Chipcoin PQ operational readiness dashboard

[Service]
Type=oneshot
ExecStart=/opt/chipcoin/.venv/bin/python -m chipcoin.tools.pq_operational_readiness --config /etc/chipcoin/pq-readiness.toml --output-dir /var/lib/chipcoin/pq-readiness --compact
WorkingDirectory=/opt/chipcoin
```

Example timer:

```ini
[Unit]
Description=Run Chipcoin PQ operational readiness dashboard every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
```

Use a systemd lock or scheduler policy if multiple hosts may write to the same
output directory. The command writes files atomically, but it does not coordinate
distributed writers.

## Daily Report Integration

`render_daily_report_section()` returns a compact Markdown section containing:

- status;
- height and activation height;
- remaining blocks;
- ETA;
- critical failures;
- major warnings;
- last dress rehearsal;
- last readiness suite;
- PQ activity note.

The daily report generator can call the dashboard once and embed this section
without duplicating network fetches.

## Limits

This dashboard does not:

- prove mathematical security of ML-DSA;
- execute the full dress rehearsal automatically;
- run full pytest, npm builds or browser runtime tests by default;
- infer peer version distribution when the API does not expose it;
- submit transactions;
- mine blocks;
- validate browser PQ send, which remains disabled.

Use the dashboard as an operational readiness view, not as a replacement for the
readiness suite, dress rehearsal, threat model or activation checklist.
