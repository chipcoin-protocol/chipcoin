# Post-Quantum Smoke Test

The PQ smoke command is an operational end-to-end validation tool for releases,
CI, servers, and manual checks. It creates a temporary local Chipcoin node,
simulates CHCQ activation at a low height, mines the full CHCQ lifecycle, checks
API metadata, prints a stable report, and removes temporary state by default.

The detailed regression suite remains:

```bash
python3 -m pytest tests/pq/test_activation_readiness.py -q
```

The smoke command is the shorter operational check:

```bash
python3 -m chipcoin.tools.pq_smoke
```

When running from an uninstalled source checkout, either use the project virtual
environment after `pip install -e .` or set `PYTHONPATH=src`.

## Usage

```bash
python3 -m chipcoin.tools.pq_smoke
python3 -m chipcoin.tools.pq_smoke --activation-height 20
python3 -m chipcoin.tools.pq_smoke --json
python3 -m chipcoin.tools.pq_smoke --keep-state
python3 -m chipcoin.tools.pq_smoke --verbose
```

The main CLI also exposes the same implementation:

```bash
chipcoin pq-smoke
```

## Expected Output

```text
========================================
CHIPCOIN PQ SMOKE TEST
========================================

PASS  created CHCQ address
PASS  pre-activation rejected
PASS  activation reached
PASS  CHC -> CHCQ mined
PASS  CHCQ -> CHC mined
PASS  API metadata OK

READY

activation height: 20
final local height: 22
PQ scheme: ML-DSA-44

========================================
```

## Exit Status

- `0`: complete success;
- non-zero: one stage failed.

On failure the command prints the failed stage and a concise reason. It does not
print `READY`.

## Temporary State

By default the command creates an isolated temporary directory and removes it on
success or failure. Use `--keep-state` to preserve the temporary node database
for debugging.

No public testnet node, peer, DNS name, or external API is used.

## What It Validates

- production testnet CHCQ activation is height `20000`;
- local test-only PQ activation can be set to a low height;
- CHCQ address generation and parsing resolve to ML-DSA-44;
- CHC to CHCQ is rejected before activation;
- local mining reaches the activation height;
- CHC to CHCQ is accepted and mined after activation;
- the mined CHCQ UTXO exists with the expected amount and scheme;
- CHCQ to CHC signs and verifies through the real ML-DSA-44 backend;
- the CHCQ UTXO is spent and the legacy destination receives funds;
- node HTTP/API serialization exposes `sig_scheme_id`, `sig_scheme_name`,
  `address_kind`, and `address_scheme_id`.

## What It Does Not Validate

- browser WASM signing;
- public-testnet networking;
- global chain-wide PQ statistics;
- production-load DoS resistance;
- the real height-20000 activation event itself.

## Relationship To The Pytest Suite

The readiness pytest suite is the detailed automated regression suite, including
negative malformed transaction cases. The smoke command is a compact operational
check intended for release validation, CI jobs, servers, and internal demos.
