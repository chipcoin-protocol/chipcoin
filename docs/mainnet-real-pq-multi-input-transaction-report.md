# MAINNET REAL PQ MULTI-INPUT TRANSACTION REPORT

Date: 2026-10-06

## Scope

This report covers only `PQ-RUN-003`: one real, ordinary, multi-input
ML-DSA-44 transaction on the isolated mainnet rehearsal. No consensus, wallet,
reward, database, difficulty, maturity, activation, or epoch parameter was
modified. MemPalace was consulted for the established production wallet signing
and input-selection path.

## Baseline

At height `277`, A/B/C were converged on:

- Tip: `0000000686e917cc060ec669b814927b9016ee9469e3445acc1a61ebcba6b8bc`
- Cumulative work: `60917493372`
- Materialized supply: `1390000000000` chipbits
- UTXO count/hash: `282` / `e0632a4e6d2d8b6252942e7043ee81280ece8ef6a00356aeea53777a39155fa2`
- Mempool: empty
- Reward registry count/hash: `2` / `d73320ecade254ce716214f16305df5351261bcf9cfe28ddd161badb7dcbddf8`
- Reward nodes: registered, warming up, inactive
- Reward attestations/settlements/distributed rewards: `0 / 0 / 0`
- SQLite quick/FK checks: PASS

## Transaction

The transaction was built and signed by the production `wallet-build` path in
the validated rehearsal image, using the read-only `miner-a` ML-DSA-44 wallet.
It was submitted through the production HTTP transaction endpoint on node-a.

- TXID: `fc382a82dcda0a6064f5f89cb25591e1279244155e161c18605373a2bc201a33`
- Raw SHA-256: `0b4739a370f5b07f4b6d9fcc720702a1d3aea34faab2409d55449e7db4e78c80`
- Transaction version: `2`
- Raw size: `7712` bytes
- Source/change: `CHCQCqjEfT2onoGj8iV3ZG9iCrkZovUjHZDshF3Zu7rR29Ncn5ybbbo7`
- Destination: `CHCQCqiwih5HyVzieodVeHj4L9YBWx3mQ62ktz1SFhuc85TSnofyTV3F`

Canonical mature inputs:

1. `028b74f5a27bc9c282e0128dcadf7eb65741e8d072a319e5ba85e90111f54807:0`
   - Origin height: `75`
   - Amount: `5000000000` chipbits
   - Coinbase: yes
2. `03437b46c20838fc19cd55a4a0099879bbe810ea68235b82ab68c3a377411d19:0`
   - Origin height: `12`
   - Amount: `5000000000` chipbits
   - Coinbase: yes

Both inputs belonged to the source wallet, were canonical, mature, unspent,
and unrelated to reward payouts or Scenario A/B transactions.

Each input carried a distinct 2,420-byte ML-DSA-44 signature, scheme ID `10`,
and the expected public-key commitment. There was no legacy/ECDSA fallback.
Production mempool and block validation accepted both signatures.

Arithmetic:

- Inputs: `10000000000` chipbits
- Payment: `7500000000` chipbits
- Change: `2499999000` chipbits
- Fee: `1000` chipbits
- `10000000000 = 7500000000 + 2499999000 + 1000`: PASS

## Propagation And Confirmation

- Submission started: `2026-10-05T20:14:45.110568646Z`
- Node-a accepted: PASS, fee `1000` chipbits
- A/B/C mempool observation: `2026-10-05T20:15:47.746446123Z`
- A/B/C each reported the same TX with two scheme-10 inputs
- Confirmation height: `278`
- Confirmation block: `000000028ee8f094dd88d8d8e6671a7310f0d7ab18077110ba8fafdbfb5d2b41`
- Transaction index: `1`
- Canonical occurrence count through height 327: exactly `1`

## UTXO And Fee Accounting

After confirmation on A/B/C:

- Both input outpoints were absent from the UTXO set.
- Destination output `:0`, `7500000000` chipbits: present.
- Change output `:1`, `2499999000` chipbits: present.
- Both outputs are PQ/CHCQ, scheme ID `10`.
- Transaction absent from every mempool.
- No duplicate or ghost output was found.

Block 278 reported `fees_chipbits=1000`. Its miner coinbase paid
`5000001000` chipbits: the normal `5000000000` block reward plus the exact
`1000`-chipbit fee. The transaction input/output gap is the same `1000`
chipbits, so the fee is transferred rather than newly minted. Supply follows
the normal block schedule with no unexpected creation or destruction.

## Reward Isolation

The transaction did not modify reward registrations. While Codex was stopped
and normal mining continued, the chain crossed height 300 and the existing
automation performed the expected epoch-3 renewals. This was normal height
progression, not part of this gate and not manually triggered by the test.

At the final checkpoint all nodes still reported:

- Registry count: `2`
- Original registration height: `275`
- Last renewal height/epoch: `300 / 3`
- State: `warming_up_until_height_400`
- Active: `false`
- Attestation count: `0`
- Settlement count: `0`
- Distributed/materialized node rewards: `0`

No reward gate is promoted by this report.

## Final Convergence

At height `327`, A/B/C matched exactly on:

- Tip: `00000007a4b1e7175057fc9d3c68d62c6b03790c1912d7fa915929bdd79d4501`
- Cumulative work: `71873877072`
- Materialized supply: `1640000000000` chipbits
- UTXO count/hash: `332` / `0550ab3b265d0a4e749ed8b1d9609e645100f0cab7dad1dd1205b34f1855ab12`
- Registry count/hash: `2` / `250181d631f01060457af722e0d794c0c5af7d173233338c522b849342526fbb`
- Mempool: empty
- Relevant balances and reward state: identical
- SQLite quick/FK checks: PASS
- Wallet checksums: unchanged

Evidence is retained under
`/tmp/chipcoin-mainnet-docker-rehearsal/pq-multi-input-20261005`.

## Gate Result

Only `PQ-RUN-003` is promoted to `PASS`.

PQ_MULTI_INPUT = PASS

ML_DSA_44_ALL_INPUTS = PASS

MEMPOOL_PROPAGATION = PASS

CANONICAL_CONFIRMATION = PASS

UTXO_ACCOUNTING = PASS

PQ_RUN_003 = PASS

PQ_CONSENSUS_BLOCKER = NO
