# Mainnet Scenario B Acceptance Criteria

Scenario B verifies conflicting transactions across a real Docker partition. It
does not permit consensus, difficulty, maturity, P2P, mempool, database, or
economic parameter changes.

## Preconditions

- node-a, node-b, and node-c have identical consensus fingerprints;
- miner-a and miner-b are operational on the shared rehearsal network;
- the ordinary monitor is active, the fault monitor is inactive, and no fault
  lock exists;
- SQLite `quick_check` is `ok` and `foreign_key_check` is empty on A/B/C;
- TX-A2 and TX-B2 are persisted but have never been submitted;
- both transactions are independently valid ML-DSA-44 transactions with
  scheme ID 10, explicit fees, different TXIDs and outputs, and exactly the
  same mature input outpoint.

## Partition Assertions

Branch A consists of node-a and miner-a. Branch B consists of node-b, node-c,
and miner-b. Bidirectional P2P isolation must be demonstrated before either
transaction is submitted.

- TX-A2 is submitted only to A and confirmed only on A.
- TX-B2 is submitted only to B and confirmed only on B.
- Both transactions spend the recorded UTXO-Y.
- Branch B becomes the known winner only when its cumulative work is greater
  than branch A's cumulative work. Height alone is insufficient.
- Both miners are stopped before reconnect.

## Reorg Assertions

Reconnect restores only normal P2P connectivity. No block, transaction, tip,
database, mempool entry, or cumulative-work value may be injected manually.

`CONFLICTING_ORPHAN_TX_REJECTED` is PASS only when all of the following are
observed at runtime:

- branch B is selected naturally by cumulative work;
- TX-B2 remains canonical and TX-A2 becomes orphaned;
- TX-A2 is absent from every canonical chain and mempool;
- UTXO-Y is consumed exactly once, by TX-B2;
- all TX-A2 outputs are absent and all expected TX-B2 outputs are present;
- no double spend, ghost UTXO, or duplicate accounting exists;
- losing-branch blocks and coinbases are removed from canonical UTXO and
  supply accounting;
- A/B/C converge on height, tip, cumulative work, supply, UTXO hash, selected
  balances, reward registry, settlement state, and payout state;
- SQLite integrity checks pass on A/B/C.

Any unmet assertion is FAIL. The orchestrator must stop miners and preserve
evidence; it must not repair node state or resubmit the orphan transaction.
