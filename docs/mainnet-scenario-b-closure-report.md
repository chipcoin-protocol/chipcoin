# MAINNET SCENARIO B - CLOSURE REPORT

Date: 2026-10-05. Session: `fault-20261004T221125Z-3410562`.
MemPalace was consulted during this Scenario B execution. Runtime evidence,
not historical memory, determines the assertions below.

## Evidence

All paths below are relative to
`/tmp/chipcoin-mainnet-docker-rehearsal/fault/evidence/`:

- `fork-20261005T063421Z/fork.json`: common ancestor 197 and divergent blocks 198.
- `winning-20261005T075424Z/work.json`: branch fingerprints before reconnect.
- `scenario-b-reorg-20261005T080011Z/`: convergence, conflicting orphan assertion,
  transaction UTXOs and orphan evidence.
- `recovery-20261005T083344Z/converged.json`: recovery checkpoint 218.
- `baseline-20261005T083907Z/`: post-block A/B/C state, wallet checksums,
  container/network evidence and corresponding baseline log collection.

Closure also performed a read-only SQLite transaction on node-a, decoding stored
blocks with the existing consensus deserializer. This verified canonical TX
occurrences, the canonical spender, block 219 linkage and all 18 losing branch
coinbases (heights 198-215). Node-b independently confirmed canonical occurrence
and spender. A/B/C fingerprints and empty mempools were collected by baseline.
Older orphan lists are supplementary; the final read-only audit covers all 18.

## Conflicting Spends And Reorg

- UTXO-Y: `40544d3f6928ee126022dc08d8fa0507a7f333c62fa46584e918410a0cff7a39:0`.
- TX-A2: `7d3c4a35aed843788cfc03cddbbeae70c7b963306db89e901cb11f0b733a4122`.
- TX-B2: `ad9abec59da2545296d8ea3d35bf340cb3008d908f46520bc17e10384ee49885`.
- A2 confirmed on A at 212:
  `00000001501b4df56463bee7d7cc8214b9ab67240fd1c9601dc99710139c20a7`.
- B2 confirmed on B at 216:
  `00000007f2d3b95c0da1ad72ae53cb264c64c2320b21c56f52c9b8f94e8178b4`.
- A before reconnect: height 215, work `47331577584`.
- B before reconnect: height 218, work `47988960606`.
- B work advantage: `657383022`.
- Common ancestor: height 197,
  `000000028228ab8a60144e8e08e02bf30551a4b2f83d86ea21e917308743d6fb`.
- Natural P2P reorg disconnected A heights 198-215 (18 blocks).

B2 has exactly one canonical occurrence and is the sole canonical spender of Y.
A2 has zero canonical occurrences, no canonical outputs and is absent from the
empty A/B/C mempools. Y is absent from UTXOs. B2 outputs are 100000000 and
4899999000 chipbits; input 5000000000 minus outputs gives fee 1000.
No manual resubmit was performed. The persisted normal-reorg assertion is
`CONFLICTING_ORPHAN_TX_REJECTED`.

All 18 losing coinbases have zero canonical UTXOs. Their blocks remain stored as
noncanonical evidence; they were not deleted. No losing outputs survive.
Pre-reconnect A supply was 1080000000000; canonical B/recovery supply at 218 was
1095000000000. Canonical accounting includes genesis plus 218 mined rewards:
219 * 5000000000 chipbits. Fees transfer existing value and are not new supply.

## Chain Continuation And Final Convergence

Recovery checkpoint 218:
`000000068e1dfe80e7d7ba6ebea443e85b7c128c751d2a60d2f3f7b2f9c3f3d9`,
work `47988960606`, supply `1095000000000`, 223 UTXOs,
UTXO hash `ba9b21f65ee81fae38fef5046d829d0aadd85d2b599947aa5b0280d8123dd926`.

New canonical block 219:
`0000000dd594c3e8fbc80d0abb3b048d5646736697c3204471b7086cd0683d9f`.
Its previous hash is exactly the recovery checkpoint hash above.
Coinbase `84c98eab71cacf2078d08646f89ebbf44d9aa351a6be8496596922a4dfbf508b`
pays 5000000000 chipbits to miner-a address
`CHCQCqjEfT2onoGj8iV3ZG9iCrkZovUjHZDshF3Zu7rR29Ncn5ybbbo7`.

| Field | node-a | node-b | node-c |
|---|---|---|---|
| Height | 219 | 219 | 219 |
| Cumulative work | 48208088280 | 48208088280 | 48208088280 |
| Materialized supply, chipbits | 1100000000000 | 1100000000000 | 1100000000000 |
| UTXO count | 224 | 224 | 224 |
| Mempool size | 0 | 0 | 0 |
| SQLite quick_check | ok | ok | ok |
| SQLite foreign_key_check | empty | empty | empty |

All three share the block 219 tip and these deterministic hashes:

- UTXO: `2ae24bac677e7a84e4341ccb409bda1efb0adc96215af9384189bbf51cbadf42`.
- Selected balances: `1ea095d13d49b720f65309ed27fa1f2f431b2578ff0cf21aba3974a030f46115`.
- Registry and settlements: `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

Registry/settlement equality is equality of the current empty state, not proof
of the future reward lifecycle. Supply increased by exactly one 50 CHC reward.

## Separate Operational Issue

Classification: POST-SCENARIO FINALIZATION / HARNESS OPERATIONAL ISSUE.
Status: recovery complete; finalize code defect remains unresolved.

`finalize_convergence()` wrote lifecycle FINAL_CONVERGENCE and cleaned the fault
monitor, then the session lock rejected `RECONNECTING -> FINAL_CONVERGENCE`.
Thus lifecycle and lock phase differed after consensus convergence. The existing
`recover_session()` entered RECOVERING with the original immutable session ID,
verified shared topology and convergence, closed the lock and restarted miners.
No harness patch, node restart, consensus change or manual state edit was used.
Both miners reported MINER_OPERATIONAL_ON_EXPECTED_BRANCH on shared topology;
ordinary monitor was active/running, fault lock and monitor ownership absent.
This operational defect does not invalidate the observed reorg assertions.

## RC Decision

CONS-RUN-005 and FAULT-RUN-012 definitions exactly match the real conflicting
spend/reorg properties demonstrated, so both are promoted NOT_RUN -> PASS.
Other gates retain their states, including FAULT-OPS-001/002/003 PASS.
Finalize issue remains separately recorded above and requires an operational fix
before relying on that finalize path for another fault session.

RC counts: 69 PASS / 21 NOT_RUN / 8 PENDING_HEIGHT / 0 FAIL / 98 total.
MAINNET_RC_READY = FALSE. PUBLIC_LAUNCH_READY = FALSE.

SCENARIO_B = PASS

CONFLICTING_ORPHAN_TX_REJECTED = PASS

CHAIN_CONTINUATION_AFTER_REORG = PASS

CONSENSUS_STATE_BLOCKER = NO

SCENARIO_B_RETEST_REQUIRED = NO
