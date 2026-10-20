# Chipcoin Public Mainnet Genesis Specification

Status: RC4 recalibrated genesis candidate. This specification is not release
approval; immutable artifacts, Explorer pinning, and public launch remain
separate decisions.

## Canonical Identity

- Operational profile: `mainnet`
- Immutable chain ID: `chipcoin-mainnet-1`
- P2P magic: first four bytes of
  `SHA-256("chipcoin:p2p-magic:chipcoin-mainnet-1")`, equal to `c0897c0d`
- Previous block hash: 32 zero bytes
- Header version: `1`
- Initial compact target: `0x1e0537e7`
- Timestamp: `2026-10-20T21:00:00Z` (`1792530000`)
- Nonce: `5671737` (lowest valid nonce, independently scanned by the standard-library verifier)
- Genesis hash: `00000238ef41c47992581c18fad544b4e24ecf1e79e7ffed629a215def4a337f`
- TXID / Merkle root: `6ec15ed32ddd62c6134b0c867c33f8fa72ba265b4551d327a57b63721cf34c77`
- Serialized block SHA-256: `484b630c988988bb58b0f0cde171a9e666c15decc6e063cd7704527795a652a4`

With the measured miner-a rate of approximately `3572 H/s`, this compact
target represents `3215030` expected hashes: approximately `900.06s` with one
equivalent miner, `450.03s` with two, and `300.02s` with three. These are
expectations, not guaranteed intervals; measured miner throughput can vary.
The consensus target spacing remains `600s`, and the retarget window remains
`1000` blocks. The initial three-miner bootstrap calibration is intended to
produce about 300 seconds per block; the first retarget responds to observed
intervals using the unchanged clamp and genesis-target cap. The genesis-to-
height-999 span contains 999 intervals: at exactly 300 seconds each it is
299,700 seconds, yielding compact bits `0x1e029b48` and about `600.65s` per
block at the same aggregate hashrate after quantization.

The public magic is distinct from rehearsal (`f9beb4d9`), testnet
(`fab4c0de`), and devnet (`fac3b6da`). The chain ID, magic, and canonical
genesis hash are independent identity checks. A matching profile name alone is
not sufficient.

## Genesis Transaction

The genesis contains exactly one output-free transaction. Its sorted metadata
contains:

```text
chain_id=chipcoin-mainnet-1
coinbase=true
genesis_message=Die Welt ist alles, was der Fall ist.
height=0
```

The message is UTF-8, is exactly 37 encoded bytes, and contains no BOM,
newline, carriage return, or NUL. Metadata is part of transaction
serialization, so changing the message changes the TXID, Merkle root, and
block hash.

The transaction has no inputs and no outputs. Height 0 therefore creates no
spendable UTXO and mints no CHC. Ordinary issuance starts at height 1 with 50
CHC. Coinbase maturity remains 100, the first halving boundary remains height
111000, and total issuance is clamped to exactly 11000000 CHC.

## Reward-Node Registration Funding

The final public mainnet sets `funded_reward_node_activation_height = 0`.
Because the canonical genesis at height `0` contains only the fixed output-free
genesis transaction, this makes funded reward-node registration and renewal
mandatory from the first operational block at height `1` without requiring an
activation value of `1`.

Every registration or renewal must use the funded v2 format, consume mature
UTXOs owned and signed by the ML-DSA-44 reward owner, return change only to the
owner's CHCQ address, and pay exactly the canonical fee as a real input/output
difference. The fee is included in the block's transaction-fee total and paid
to the miner. Consensus rejects legacy input-free operations, metadata-only fee
declarations, wrong-owner inputs, immature coinbase inputs, incorrect fees, and
double spends.

This transaction-format rule does not activate reward distribution. Mainnet
attestations, settlements, and payouts remain gated by
`node_reward_activation_height = 1000`. The isolated TEST-ONLY rehearsal keeps
its funded-v2 activation at height `300` for historical compatibility, while
public testnet activation remains unset pending a separate coordinated rollout.

## Deterministic Finalization

After the founder approves one UTC Unix timestamp, an offline operator runs:

```bash
.venv/bin/python scripts/build-public-mainnet-genesis.py \
  --timestamp APPROVED_UNIX_TIMESTAMP \
  --output-dir NEW_EMPTY_OUTPUT_DIRECTORY \
  --acknowledge-founder-approved-timestamp
```

The builder uses the fixed transaction, header fields, and RC4 initial target and
selects the lowest valid nonce. It emits the serialized block, a canonical JSON
manifest, an embedding snippet, and `SHA256SUMS`. Repeating the command from the
same source with the same timestamp must produce byte-identical output.

Finalization requires an independent reproduction before embedding the block
hex and hash in `chipcoin.consensus.genesis`. The timestamp must be reviewed
against the intended launch window and retarget behavior before mining. No
node startup path derives timestamp, nonce, or genesis content at runtime.

## Enforcement

The candidate is embedded in the RC4 source. Source freeze does not itself
approve public artifacts, Explorer deployment, or mainnet launch. In the frozen
release:

1. an empty database installs the embedded genesis atomically;
2. an existing database must contain the same height-zero hash and chain ID;
3. block validation accepts height 0 only when it is byte-identical to the
   configured canonical genesis;
4. P2P version handshakes require matching chain ID and genesis hash;
5. snapshots require matching network, chain ID, and embedded genesis;
6. APIs expose chain ID and genesis hash for wallet, miner, reward, and
   Explorer identity checks.
7. Wallet and miner endpoint validation also requires the configured network
   magic; the mining API publishes that field alongside chain ID and genesis.

The rehearsal remains a separate historical chain. Its databases, wallet
material, snapshots, peerbooks, and Docker volumes are never valid bootstrap
inputs for this public chain.
