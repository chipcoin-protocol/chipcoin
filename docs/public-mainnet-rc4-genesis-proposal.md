# Public Mainnet RC4 Genesis Proposal

Status: RC4 genesis candidate; not published and not a launch approval. It is
based on the frozen RC3 source tags and changes the initial PoW target
and the identity values that necessarily derive from the new genesis.

## Candidate identity

| Field | Candidate |
| --- | --- |
| Chain ID | `chipcoin-mainnet-1` |
| P2P magic | `c0897c0d` (unchanged; derived from chain ID) |
| Timestamp | `2026-10-20T21:00:00Z` / `1792530000` |
| Initial bits | `0x1e0537e7` |
| Target spacing / retarget window | `600s` / `1000` blocks |
| Nonce | `5671737` |
| Genesis hash | `00000238ef41c47992581c18fad544b4e24ecf1e79e7ffed629a215def4a337f` |
| TXID / Merkle root | `6ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c77` |
| Serialized block SHA-256 | `484b630c988988bb58b0f0cde171a9e666c15decc6e063cd7704527795a652a4` |

## Calibration and retarget

The compact target decodes to `0x00000537e700...0000` and contributes
`3,215,030` expected hashes per block. Using the measured miner-a rate of
approximately `3,572 H/s`, expected times are `900.06s`, `450.03s`, and
`300.02s` for one, two, and three equivalent miners. Thus the intended
bootstrap average with three miners is about 300 seconds; the consensus
spacing remains 600 seconds.

At candidate height 1000 the existing algorithm compares the measured span
from genesis to height 999 against 600,000 seconds, clamps the span to one
quarter through four times that target, scales the previous target, and caps
the result at the genesis target. There are 999 inter-block intervals in that
span; at 300 seconds each, the span is 299,700 seconds. The resulting compact
bits are `0x1e029b48`, giving about 600.65 seconds at the same aggregate
hashrate after compact quantization. Actual intervals are random and the
measured rate is only one host's observed result.

## Reproduction

The candidate was built from the RC4 worktree with timestamp `1792530000`.
Parallel (two-worker) and serial (one-worker) canonical builders emitted
byte-identical artifact directories. The independent standard-library
verifier checked serialization, TXID, Merkle root, hash, bits, PoW and all
lower nonces. Artifact hashes and statuses are in
`docs/releases/public-mainnet-rc4-genesis-candidate.json`.

No independent second-host reproduction or formal RC gate has been performed.
The genesis, source, and release remain candidates; no mainnet chain was
started and no mining was performed.
