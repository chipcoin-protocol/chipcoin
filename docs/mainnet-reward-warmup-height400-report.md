# MAINNET REWARD WARMUP HEIGHT-400 OBSERVATION

Date: 2026-10-07

## Scope

This was a read-only observation of the existing mainnet rehearsal while it
crossed heights 399, 400, and 401. No transaction was submitted, no node or
miner was restarted, and no database, configuration, monitor, consensus
parameter, or RC gate was modified. Evidence is retained under
`/tmp/chipcoin-mainnet-docker-rehearsal/reward-warmup-height400-20261006`.

MemPalace was consulted for the established reward-node lifecycle semantics.

## Production Semantics

The production path in `src/chipcoin/consensus/nodes.py` defines:

- `current_epoch(height) = height // epoch_length_blocks`;
- `warmup_complete_epoch = registration_epoch + reward_node_warmup_epochs`;
- warmup is satisfied when the evaluated epoch is greater than or equal to
  `warmup_complete_epoch`;
- active status additionally requires a confirmed renewal in the evaluated
  epoch and `last_renewed_height < evaluation_height`.

With registration at height 275 (epoch 2), epoch length 100, and two warmup
epochs, the first warmup-complete epoch is epoch 4 and its first height is 400.
The registry diagnostics evaluate the next candidate block height. Therefore,
at tip 399 they evaluate height 400: warmup is satisfied, but both records are
still stale until their epoch-4 renewals are confirmed. The renewals were
included naturally in block 400. At tip 400 the diagnostics evaluate height
401 and report both records active from height 401. This matches the production
rule and is not an off-by-one discrepancy.

## Registered Nodes

Both records retained registration height 275, distinct owner and attestation
identities, ML-DSA-44 scheme ID 10, and their original CHCQ payout addresses.

| Node | Owner / payout | Attestation identity | Registration |
|---|---|---|---:|
| `rehearsal-reward-a` | `CHCQCqjWLptxDkCEymFxGrUkuM1VYb32zbqsK5vdsD2zKsPKHU8V2YfH` | `CHCQCqkQSHjjDsmsrKEmdqah8fmKLsPUSv9p9ZDftJpG5wPxmPAEkXUV` | 275 |
| `rehearsal-reward-b` | `CHCQCqj5EnPD6QUSTukN8oV4FHSBBtU1JHCDaAYVCNFwK7rRg95wzcNw` | `CHCQCqkPba3JUwi1gU9q7epgRSu8tkDKRtU4UdtgzbFKgqkasUfgxssL` | 275 |

Registry count remained exactly 2. Registration origin, owner, attestation,
payout, and warmup-complete height were not changed by renewal.

## Boundary Evidence

| Tip | Epoch / evaluation | Canonical block | Node state | Renewal | Reward effects |
|---:|---|---|---|---|---|
| 399 | epoch 3 / candidate 400 | `0000000d64e26deff6447a58dfb49241059d481edb50f99916b494195e385e9f` | warmup satisfied for candidate 400; `stale`, inactive until renewal | epoch-3 renewal remained at height 300 | 0 attestations, 0 settlements, 0 payouts |
| 400 | epoch 4 / candidate 401 | `00000005ec38d6b705ffba5a0936f9d4877510f6bec4e97da34e8c9422a3ad9c` | warmup complete; active from height 401 | both epoch-4 renewals confirmed at height 400 | 0 attestations, 0 settlements, 0 payouts |
| 401 | epoch 4 / candidate 402 | `0000000b6affca9f3e230d3704b2b6356040fdbe5b0331bc7d2eb7361ecb3947` | warmup complete and active | renewal state unchanged and current | 0 attestations, 0 settlements, 0 payouts |

Block 400 directly extends block 399, and block 401 directly extends block 400.
The two automatic renewal transactions confirmed in block 400 were:

- node B: `5cc9825a4c4a5b0b09af2261543f525af2acb621f5296de8a6c0f1025c6f1fd8`;
- node A: `75c4ed4f114a876684c9d40519831d9c6aefba4e5ddfc1c97341cebaa5133878`.

Both are canonical `renew_reward_node` transactions for epoch 4, signed on
mainnet with scheme ID 10. No registry duplication occurred.

## Consistency

At height 401, A/B/C agreed on:

- tip `0000000b6affca9f3e230d3704b2b6356040fdbe5b0331bc7d2eb7361ecb3947`;
- cumulative work `88089324948`;
- registry count/hash `2` / `54fafa9ca92c6d379af6bb7abc73bc42669ed48ad60ad53fce81aee6d65111c2`;
- UTXO count/hash `406` / `a8b81a6b3e52932cda030eee2e31679aaa7328c02021e1eda84689f5b36a8615`;
- zero stored settlements and zero distributed node rewards;
- empty mempool and identical reward-node state.

SQLite `quick_check` returned `ok` and `foreign_key_check` returned no rows on
all three nodes. Both miners remained running and the ordinary rehearsal
monitor remained active. The transient mempool difference observed at tip 399
was the normal propagation of the two automatic renewals; it was empty and
convergent after block 400.

The registry-local active flag does not promote or execute the activation,
attestation, committee, settlement, payout, or Explorer reward gates. Those
remain height-gated and unchanged.

## Result

No reward RC gate or RC count was modified by this preparatory observation.

HEIGHT_400_REACHED = YES

REGISTRY_COUNT = 2

REWARD_NODE_A_REGISTRATION_HEIGHT = 275

REWARD_NODE_B_REGISTRATION_HEIGHT = 275

REWARD_NODE_A_WARMUP_COMPLETE = YES

REWARD_NODE_B_WARMUP_COMPLETE = YES

REWARD_NODE_A_ACTIVE = YES

REWARD_NODE_B_ACTIVE = YES

REGISTRY_DUPLICATION = NO

RENEWAL_STATE_COHERENT = YES

A_B_C_REWARD_STATE_CONVERGENT = YES

SQLITE_INTEGRITY = PASS

WARMUP_BOUNDARY_BEHAVIOR = PASS

REWARD_RC_BLOCKER = NO

RC_STATE = 86_PASS_5_NOT_RUN_7_PENDING_HEIGHT_0_FAIL
