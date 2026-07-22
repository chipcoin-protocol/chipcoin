# Chipcoin Post-Quantum Activation Checklist

This checklist is for the scheduled testnet CHCQ activation at height `20000`.
Every item should be checked with exact command output, date and operator.

## Testnet Activation Rescheduled

Testnet activation was rescheduled from height `30000` to height `20000` after
completion of implementation, audit, smoke testing, browser parity, dress
rehearsal and operational readiness work. This is a mandatory testnet consensus
upgrade before height `20000`; old nodes that retain the `30000` schedule can
diverge at the first block containing PQ activity below height `30000`. No
keys, CHCQ addresses, transaction serialization, sighash, scheme ids, PoW,
rewards, or wallet file formats changed.

## Before Activation

- [ ] Confirm code version includes `549b69b Add PQ transaction validation hardening`
      or a later commit containing the same PQ hardening.
- [ ] Confirm `pq_support_activation_height("testnet") == 20000`.
- [ ] Run full Python test suite: `.venv/bin/python -m pytest -q`.
- [ ] Run PQ suite: `.venv/bin/python -m pytest tests/pq -q`.
- [ ] Run readiness suite: `.venv/bin/python -m pytest tests/pq/test_activation_readiness.py -q`.
- [ ] Run smoke command: `.venv/bin/python -m chipcoin.tools.pq_smoke`.
- [ ] Run benchmark: `.venv/bin/python -m chipcoin.tools.pq_benchmark`.
- [ ] Save audit report: `.venv/bin/python -m chipcoin.tools.pq_audit_report --json`.
- [ ] Generate operational readiness dashboard:
      `.venv/bin/python -m chipcoin.tools.pq_operational_readiness --output-dir /var/lib/chipcoin/pq-readiness`.
- [ ] Confirm dashboard status is `READY` or explicitly document every
      `DEGRADED`/`UNKNOWN` reason before proceeding.
- [ ] Run browser wallet tests: `cd apps/browser-wallet && npm ci && npm test`.
- [ ] Run browser builds: `npm run build`.
- [ ] Run bundle inspection: `npm run test:mldsa:bundle`.
- [ ] Confirm Chromium CI `browser-pq-chromium` is green.
- [ ] Confirm Firefox runtime verification is green or document local blocker.
- [ ] Confirm API metadata exposes `sig_scheme_id`, `sig_scheme_name`,
      `address_kind`, and `address_scheme_id` for PQ vectors.
- [ ] Confirm explorer displays CHCQ/PQ badges and recent-window PQ stats.
- [ ] Confirm browser wallet still blocks CHCQ send and does not store PQ keys.
- [ ] Confirm runtime memory metrics include PQ counters.
- [ ] Confirm minimum compatible node version is published.
- [ ] Confirm miners/reward nodes have upgraded binaries or images.
- [ ] Confirm snapshot import/export remains compatible.
- [ ] Confirm rollback plan and known-good pre-PQ image/tag are documented.
- [ ] Publish community notice explaining CHCQ status and browser limitations.

## Near Height 20000

- [ ] Record current height and blocks remaining.
- [ ] Run `chipcoin pq-operational-readiness --compact` at least every monitoring
      interval and archive `latest.json`.
- [ ] Record peer version distribution.
- [ ] Record miner version readiness.
- [ ] Record percentage of known operational nodes upgraded.
- [ ] Record chain height spread across public peers.
- [ ] Watch mempool PQ malformed/rejected counters.
- [ ] Watch PQ verify latency counters.
- [ ] Watch CPU/RSS and restart counters.
- [ ] Watch logs for `CHCQ outputs are not active` before activation.
- [ ] Verify no unexpected browser CHCQ send path appears.
- [ ] Confirm explorer activation panel reports scheduled/active state correctly.
- [ ] Freeze nonessential deployments during the activation window.

## After Activation

- [ ] Confirm activation state is active at height >= `20000`.
- [ ] Confirm operational readiness dashboard no longer reports activation as
      scheduled once the chain is beyond height `20000`.
- [ ] Submit or observe first CHC -> CHCQ transaction.
- [ ] Confirm first CHCQ UTXO exists with correct amount and metadata.
- [ ] Submit or observe first CHCQ -> CHC spend.
- [ ] Confirm ML-DSA verification counters increment.
- [ ] Confirm mempool accepts valid PQ txs and rejects malformed PQ txs.
- [ ] Confirm mined blocks containing PQ txs are accepted by multiple nodes.
- [ ] Confirm API metadata for mined PQ transactions is correct.
- [ ] Confirm explorer visibility and labels are correct.
- [ ] Confirm no node disagreement or persistent height spread appears.
- [ ] Confirm reorg behavior remains normal if a shallow reorg occurs.
- [ ] Record benchmark/latency comparison after live PQ use begins.
- [ ] Save incident log even if no incident occurs.

## Rollback Notes

Rollback must not change consensus history. If an incompatible bug appears before
any CHCQ output is mined, operators can revert deployment after coordinating a
halt. If CHCQ outputs or spends are mined, any protocol-impacting rollback
requires explicit consensus analysis before action.
