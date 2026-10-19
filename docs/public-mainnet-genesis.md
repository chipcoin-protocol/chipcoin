# Chipcoin Public Mainnet Genesis Specification

Status: implementation pending founder-approved timestamp and final genesis
finalization.

## Canonical Identity

- Operational profile: `mainnet`
- Immutable chain ID: `chipcoin-mainnet-1`
- P2P magic: first four bytes of
  `SHA-256("chipcoin:p2p-magic:chipcoin-mainnet-1")`, equal to `c0897c0d`
- Previous block hash: 32 zero bytes
- Header version: `1`
- Initial compact target: `0x1d1399ad`
- Timestamp: `PENDING_APPROVAL`
- Nonce: `PENDING_FINALIZATION`
- Genesis hash: `PENDING_FINALIZATION`

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

The builder uses the fixed transaction, header fields, and initial target and
selects the lowest valid nonce. It emits the serialized block, a canonical JSON
manifest, an embedding snippet, and `SHA256SUMS`. Repeating the command from the
same source with the same timestamp must produce byte-identical output.

Finalization requires an independent reproduction before embedding the block
hex and hash in `chipcoin.consensus.genesis`. The timestamp must be reviewed
against the intended launch window and retarget behavior before mining. No
node startup path derives timestamp, nonce, or genesis content at runtime.

## Enforcement

Until the canonical block and hash are embedded, production `mainnet` node,
HTTP, and miner CLI entrypoints fail closed. After finalization:

1. an empty database installs the embedded genesis atomically;
2. an existing database must contain the same height-zero hash and chain ID;
3. block validation accepts height 0 only when it is byte-identical to the
   configured canonical genesis;
4. P2P version handshakes require matching chain ID and genesis hash;
5. snapshots require matching network, chain ID, and embedded genesis;
6. APIs expose chain ID and genesis hash for wallet, miner, reward, and
   Explorer identity checks.

The rehearsal remains a separate historical chain. Its databases, wallet
material, snapshots, peerbooks, and Docker volumes are never valid bootstrap
inputs for this public chain.
