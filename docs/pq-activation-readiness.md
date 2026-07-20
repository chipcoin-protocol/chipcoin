# Post-Quantum Activation Readiness Suite

The readiness suite validates the CHCQ activation lifecycle without changing
production consensus constants or lowering the public testnet activation height.

Production testnet CHCQ activation remains scheduled for height `30000`.

## Test Activation Height

The suite uses a test-only `ConsensusParams.pq_support_activation_height`
override set to height `20`. When the override is not set, consensus continues
to use the normal network activation schedule from
`src/chipcoin/consensus/pq_activation.py`.

This keeps production behavior unchanged while allowing deterministic local
tests of the full pre-activation and post-activation paths.

## Coverage

The suite verifies:

- pre-activation rejection of CHCQ outputs, v2 PQ spends, mempool admission, and
  block validation;
- legacy CHC transaction compatibility before activation;
- post-activation CHC to CHCQ payment, mined CHCQ UTXO creation, CHCQ spend, and
  mined spend confirmation;
- mixed CHC to CHC, CHC to CHCQ, CHCQ to CHC, and CHCQ to CHCQ transactions;
- malformed PQ transaction rejection for bad signatures, truncated signatures,
  wrong public keys, mismatched commitments, wrong scheme IDs, wrong address
  ownership, and corrupted serialization;
- node API exposure of `sig_scheme_id`, `sig_scheme_name`, `address_kind`, and
  `address_scheme_id`.

## Running Locally

Run the focused pytest suite:

```bash
python3 -m pytest tests/pq/test_activation_readiness.py -q
```

Run the readiness report wrapper:

```bash
bash scripts/pq-activation-readiness.sh
```

Run the shorter operational smoke command:

```bash
python3 -m chipcoin.tools.pq_smoke
```

Expected report:

```text
PQ ACTIVATION READINESS

PASS  pre-activation rejection
PASS  post-activation acceptance
PASS  CHCQ spend
PASS  mixed legacy/PQ compatibility
PASS  API metadata
PASS  malformed transaction rejection

OVERALL RESULT

READY FOR ACTIVATION
```

## Rationale

The activation override lives in consensus parameters instead of monkeypatching
validation functions. Tests therefore exercise the same validation calls used by
the node, mempool, mining template, block application, and HTTP API paths.

The suite uses deterministic wallet seeds and local SQLite node services. It
does not depend on public testnet height, external peers, wall-clock timing, or
network access.

For release validation and server checks, use the operational smoke command
documented in `docs/pq-smoke-test.md`. The smoke command validates the happy-path
activation lifecycle and API metadata with stable console output; this pytest
suite remains the detailed regression suite.
