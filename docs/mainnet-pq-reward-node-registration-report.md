# MAINNET PQ REWARD NODE REGISTRATION REPORT

Date: 2026-10-05

## Scope

This report covers only `REWARD-RUN-002`: real pre-activation registration of
the two reward nodes configured for the isolated mainnet rehearsal. Consensus
parameters, activation height, epoch length, warmup, reward economics, chain
history, and database state were not modified.

MemPalace was consulted before execution for the established reward-node
registration workflow and historical implementation context.

## Baseline

- Network: `mainnet`
- Pre-submission height / epoch: `274 / 2`
- A/B/C tip: `0000000a8b3d65854a718dcea4a740a6ab7f36f4e5979f9d72f8fe2ea807c0ec`
- A/B/C cumulative work: `60260110350`
- Registry count: `0`
- Mempool: empty
- A/B/C SQLite quick/FK checks: PASS
- Ordinary monitor: active
- Topology: shared
- Miner A/B: running
- Owner and attestation wallets: distinct ML-DSA-44 wallets, scheme ID `10`,
  mounted read-only in their node containers

## Canonical Registrations

Both registrations used the normal `register-reward-node` CLI and P2P
submission path. No registry row or database state was inserted manually.
Each transaction was observed in the mempool of A/B/C before mining. Both were
then included in the same canonical block.

### Reward node A

- Node ID / endpoint: `rehearsal-reward-a` / `node-a:8333`
- TXID: `e9cba6513e0c3e005e2869fea251cb4f4198496f94e733f2b2b0af04121e0778`
- Raw SHA-256: `ae43a3cc5f9cce8ee57068d6f56e9fd9d25dafeb972765c94ae65d0e7cf6e66a`
- Fee: `100000000` chipbits (`1 CHC`)
- Confirmation: height `275`, block `000000138b57a78e50d0f503c79c89f5e4e4d37f88e0b0a365d3454884ab81f0`
- Owner / payout: `CHCQCqjWLptxDkCEymFxGrUkuM1VYb32zbqsK5vdsD2zKsPKHU8V2YfH`
- Attestation identity: `CHCQCqkQSHjjDsmsrKEmdqah8fmKLsPUSv9p9ZDftJpG5wPxmPAEkXUV`
- Owner and attestation schemes: ML-DSA-44 / `10`

### Reward node B

- Node ID / endpoint: `rehearsal-reward-b` / `node-b:8333`
- TXID: `28d92c7f808cb0f2743817d60e754f615589c76fc767539c1f53c90d57dbb45b`
- Raw SHA-256: `1d47a2c598f75ff382c4e36b727ef98b6433777c60f719245c444fe8e40a75fd`
- Fee: `100000000` chipbits (`1 CHC`)
- Confirmation: height `275`, block `000000138b57a78e50d0f503c79c89f5e4e4d37f88e0b0a365d3454884ab81f0`
- Owner / payout: `CHCQCqj5EnPD6QUSTukN8oV4FHSBBtU1JHCDaAYVCNFwK7rRg95wzcNw`
- Attestation identity: `CHCQCqkPba3JUwi1gU9q7epgRSu8tkDKRtU4UdtgzbFKgqkasUfgxssL`
- Owner and attestation schemes: ML-DSA-44 / `10`

For both nodes, owner and attestation public identities are distinct. The
canonical payout commitment matches the expected owner CHCQ address. No
legacy/ECDSA identity or payout appears in either record. Canonical block
acceptance exercises the production signature and registration validation path.

## Registry And Warmup

At height `277`, all three nodes reported exactly two registry records with:

- Registry hash: `d73320ecade254ce716214f16305df5351261bcf9cfe28ddd161badb7dcbddf8`
- Registration height / epoch: `275 / 2`
- State: `warming_up`, active `false`
- Warmup-complete epoch / height: `4 / 400`

Expected schedule under unchanged 100-block epochs and two-epoch warmup:

- Epoch 2: registration confirmed at height 275
- Epoch 3: first complete post-registration epoch
- Epoch 4 / height 400: warmup requirement complete
- Height 999: warmup complete; activation-dependent behavior still disabled
- Height 1000: activation boundary; warmup is already satisfied, while actual
  renewal, attestation, committee/quorum and eligibility remain subject to
  their dedicated runtime gate

No warmup, activation, epoch, or reward parameter was shortened or simulated.

## No Premature Activation

At height `277`, both records were inactive and warming up. A/B/C had no reward
attestations, no settlements, zero distributed node rewards and zero
materialized node reward supply. No payout, settlement, committee, or active
eligibility was observed.

## Final Convergence

- Height: `277`
- Tip: `0000000686e917cc060ec669b814927b9016ee9469e3445acc1a61ebcba6b8bc`
- Cumulative work: `60917493372`
- Materialized supply: `1390000000000` chipbits
- UTXO count/hash: `282` / `e0632a4e6d2d8b6252942e7043ee81280ece8ef6a00356aeea53777a39155fa2`
- Registry count/hash: `2` / `d73320ecade254ce716214f16305df5351261bcf9cfe28ddd161badb7dcbddf8`
- Settlement count / distributed reward: `0 / 0`
- Mempool: empty
- SQLite quick/FK checks: PASS on A/B/C

The four reward-wallet checksums were unchanged. A private-seed leakage scan
covering 16,571 repository, rehearsal-log and registration-evidence files found
zero hits outside the authorized wallet files. Evidence is retained under
`/tmp/chipcoin-mainnet-docker-rehearsal/reward-registration-20261005`.

## Gate Result

`REWARD-RUN-002` is promoted to `PASS`. No other reward, activation, Explorer,
or height-gated requirement is promoted by this test.

REWARD_NODE_1_REGISTERED = PASS

REWARD_NODE_2_REGISTERED = PASS

PQ_OWNER_ATTESTATION = PASS

CHCQ_PAYOUT_DESTINATIONS = PASS

PRE_ACTIVATION_REGISTRATION = PASS

PREMATURE_REWARD_ACTIVATION = NO

REWARD_RUN_002 = PASS

REWARD_CONSENSUS_BLOCKER = NO
