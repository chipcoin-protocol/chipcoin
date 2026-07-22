# PQ Transaction Validation Hardening

This note documents node-local hardening for post-quantum transaction handling.
It does not change consensus rules, transaction serialization, activation
height, API shape, browser behavior, or the ML-DSA implementation.

## Pipeline

Post-quantum transactions can enter the node through P2P relay, local CLI/HTTP
submission, mempool re-admission after reorg, and mining template selection.
The relevant path is:

1. P2P message decode and transaction deserialization.
2. Mempool preflight policy.
3. Mempool duplicate and double-spend checks.
4. UTXO overlay construction.
5. Contextual transaction validation.
6. ML-DSA signature verification.
7. Relay inventory broadcast.
8. Mining template selection.
9. Block validation and apply.
10. Reorg rollback and mempool reconciliation.
11. Wallet/API presentation.

The expensive step is ML-DSA verification. Node-local policy now rejects malformed
PQ transactions before the UTXO overlay and verifier path whenever possible.

## Precheck Order

Mempool admission runs cheap checks first:

- generic transaction size, input-count and output-count policy;
- PQ version rule for PQ inputs only;
- scheme id known and verification-capable;
- ML-DSA-44 public-key length;
- ML-DSA-44 signature length;
- PQ input count;
- PQ sigop count;
- PQ signature-cost budget;
- serialized PQ transaction size;
- output address parsing and supported CHCQ scheme.

CHC to CHCQ outputs are still allowed to use the existing transaction version
when consensus activation allows them. The version-2 policy applies only to PQ
inputs.

## Policy Limits

Central PQ policy constants live in `src/chipcoin/pq/policy.py`:

- `MAX_PQ_SIGNATURE_SIZE = 2420`
- `MAX_PQ_PUBLIC_KEY_SIZE = 1312`
- `MAX_PQ_INPUTS = 16`
- `MAX_PQ_TX_SIZE = 64000`
- `MAX_PQ_SIGOPS_PER_TX = 16`
- `MAX_PQ_SIGOPS_PER_BLOCK = 256`
- `PQ_SIGOP_COST_ML_DSA_44 = 16`

These are mempool/mining policy limits, not consensus limits. A future release can
tune them from testnet telemetry without changing block validity.

## Signature Cost

PQ signature cost is a node-local metric:

```text
pq_signature_cost = mldsa44_input_count * PQ_SIGOP_COST_ML_DSA_44
```

It is used for mempool policy, mining-template selection, logging and metrics.
It is not part of consensus and does not make otherwise-valid historical blocks
invalid.

## Runtime Metrics

The node tracks cumulative PQ counters internally and adds them to the periodic
runtime metrics log without changing public API response shapes:

```text
runtime memory metrics ... pq_verify_count=1 pq_verify_failures=0 pq_verify_duration_seconds_total=0.002341 pq_tx_accepted=1 pq_tx_rejected=0 pq_malformed=0 pq_relay=0 pq_mined=1 pq_orphan=0
```

Counters:

- `pq_verify_count`
- `pq_verify_failures`
- `pq_verify_duration_seconds_total`
- `pq_verify_duration_seconds_avg`
- `pq_verify_duration_seconds_max`
- `pq_tx_accepted`
- `pq_tx_rejected`
- `pq_malformed`
- `pq_relay`
- `pq_mined`
- `pq_orphan`

Logs never dump private keys, public keys, or signatures.

## Benchmark

Run the operational benchmark locally:

```bash
python3 -m chipcoin.tools.pq_benchmark
chipcoin pq-benchmark
chipcoin pq-benchmark --json
chipcoin pq-benchmark --quick --json
```

The benchmark measures deterministic ECDSA and ML-DSA-44 key derivation, signing,
single verification, 100 verifications, and 1000 verifications. It reports Python
version, platform, public-key/signature sizes, mean, median, max, standard
deviation, throughput, CPU-time proxy and process memory via the platform data
available to Python.

`--quick` keeps the command fast for CI smoke checks by using 100 iterations for
the rows normally labelled `*_verify_1000`.

## Fuzz And Negative Tests

The focused tests cover truncated signatures, truncated public keys, reserved
scheme ids, wrong transaction version for PQ inputs, excessive PQ input/sigop
count, benchmark output and internal metrics. Existing readiness tests continue
to cover corrupted serialization, wrong keys, wrong commitments, activation
boundary behavior, API metadata and full CHCQ lifecycle.

## Non-Goals

This hardening does not validate browser signing, public-testnet networking,
global PQ statistics, production-load DoS resistance, or the real height-20000
activation event.
