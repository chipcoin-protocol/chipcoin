# Protocol Outline

## Monetary Unit

- Consensus uses only integer `Chipbits`.
- `1 CHC = 100_000_000 Chipbits`.
- No float monetary arithmetic is allowed in consensus, storage, validation, or mining.

## Special Transactions

Chipcoin v2 defines two consensus-validated node-control transaction families:

- legacy registry control: `register_node`, `renew_node`
- reward-node control: `register_reward_node`, `renew_reward_node`

Both are:

- non-coinbase
- signed by the node owner key
- effective from the next block, never the same block

Legacy forms are metadata-only. Funded v2 reward-node forms also contain
ordinary UTXO inputs and owner-only change outputs. Once a network's
`funded_reward_node_activation_height` is reached, consensus requires funded
v2 and rejects metadata-only forms.

`register_node` metadata:

- `kind=register_node`
- `node_id`
- `payout_address`
- `owner_pubkey_hex`
- `owner_signature_hex`

`renew_node` metadata:

- `kind=renew_node`
- `node_id`
- `owner_pubkey_hex`
- `owner_signature_hex`

Special node owner signatures:

- v2 signatures use the domain `chipcoin:special-node-tx:v2:<network>`.
- the signed v2 payload covers the same metadata fields as the legacy v1
  digest and binds them to the active network through the domain prefix.
- builder output includes `owner_signature_version=v2` and
  `owner_signature_network=<network>` once v2 is active for the target network
  height.
- mainnet validation requires v2 from genesis.
- devnet/testnet use legacy v1 before height 11111 and require v2 from height
  11111 onward.

Consensus rules:

- `node_id` is unique
- only one active registration exists for a given `owner_pubkey`
- `renew_node` is the standard path to keep a registered node active
- the canonical registration or renewal fee is derived from the parent
  registry, not from transactions earlier in the same block

## Node Rewards

Per-block subsidy is split into:

- miner base subsidy
- deterministic node reward pool

At mainnet genesis-era parameters:

- height `0`: no spendable output and no subsidy
- ordinary miner subsidy from height `1`: `50 CHC`
- node reward pool: `50 CHC` only at an epoch-closing block
- ordinary non-closing block subsidy: `50 CHC`
- maximum closing-block subsidy before fees: `100 CHC`

Epoch and reward parameters:

- mainnet:
  - epoch length: `100` blocks
  - retarget window: `1000` blocks
  - target block time: `600` seconds
  - coinbase maturity: `100` blocks
  - halving interval: `111000` blocks
  - max supply: `11000000 CHC`
- devnet:
  - epoch length: `100` blocks
  - retarget window: `200` blocks
  - target block time: `300` seconds
  - coinbase maturity: `10` blocks
  - halving interval: `111000` blocks
  - max supply: `11000000 CHC`
- maximum rewarded nodes per epoch:
  - mainnet: `25`
  - devnet: `10`

Difficulty retarget rule:

- `bits` stays unchanged between retarget boundaries
- a retarget happens when `height % difficulty_adjustment_window == 0`
- the target timespan is:
  - `target_block_time_seconds * difficulty_adjustment_window`
- the observed timespan is:
  - `timestamp(last_block_in_window) - timestamp(first_block_in_window)`
- the observed timespan is clamped to `[target_timespan / 4, target_timespan * 4]`
- the next target is computed as:
  - `next_target = previous_target * bounded_timespan / target_timespan`
- the next target is then capped by the PoW limit derived from `genesis_bits`
- the final compact `bits` value is the compact encoding of that capped target

Terminal supply rule:

- the normal block subsidy follows the integer halving schedule above
- once the halving schedule reaches zero, one explicit final correction block mints the remaining tail needed to land exactly on `11000000 CHC`
- this final correction is paid to the miner only
- the node reward pool is `0` for that correction block
- all later blocks mint `0`

Reward registration, activation, eligibility, settlement, and payout are
separate protocol states:

- reward-node registration is allowed before `node_reward_activation_height`
- warmup completes in `registration_epoch + reward_node_warmup_epochs`; this
  calculation continues before reward activation
- a registration or completed warmup does not by itself make a node eligible
  for a reward
- valid on-chain reward attestations and epoch settlements are rejected before
  `node_reward_activation_height`
- after activation, an active node must have a canonical registration or
  renewal in the current epoch, and that action must precede the evaluated
  height
- settlement eligibility additionally requires the assigned availability
  checks, valid verifier attestations, committee quorum, final-window
  confirmation, and the applicable concentration rules
- the settlement is included at the epoch-closing height; its ordered reward
  entries become node-reward outputs in that block's coinbase

The reward activation heights are network-specific: devnet uses `300`, testnet
uses `600`, and mainnet uses `1000`. A transaction-format activation, such as
the TEST-ONLY funded registration/renewal v2 activation at height `300`, is not
a reward activation and does not enable attestations, settlements, or payouts.

On the final public mainnet, `funded_reward_node_activation_height = 0` makes
the funded v2 format mandatory from the first operational block at height `1`.
Every reward-node registration and renewal must spend mature owner UTXOs signed
with ML-DSA-44, return any change to the owner's CHCQ address, and pay exactly
the canonical registration or renewal fee as the difference between inputs and
outputs. That effective fee is included in the block fee total and paid to the
miner. A legacy input-free transaction or a transaction that only declares a
fee in metadata is invalid on mainnet. This funding rule is independent of the
height-`1000` reward activation boundary.

The TEST-ONLY rehearsal retains funded v2 activation at height `300` for its
preserved history. Public testnet has no funded-v2 activation height until a
separate coordinated rollout is approved.

For mainnet's 100-block epochs and two-epoch warmup, a node registered at
height `302` is registered in epoch `3` and becomes warmup-complete at height
`500` (epoch `5`). Reward processing remains disabled until height `1000`.
With a canonical epoch-10 renewal included at height `1000`, the record can be
active from height `1001`. Its first theoretical payout is the epoch-10 closing
block at height `1099`, and only if the epoch's checks, attestations, committee,
quorum, final confirmation, and concentration rules all pass. A registry with
only one active node cannot form a verifier committee for that candidate, so it
cannot produce an eligible reward entry.

Coinbase validation checks the exact settlement-derived outputs: the first
output is the miner subsidy plus transaction fees, followed by reward-node
outputs in settlement rank order. Wrong recipients, amounts, ordering, or
output count invalidate the block.

## Transport

The main peer protocol is planned as a custom TCP-based protocol with a small binary framing layer. HTTP is not part of peer consensus traffic.

Frame layout:

- 4 bytes: network magic
- 12 bytes: ASCII command padded with NUL bytes
- 4 bytes: payload length, little-endian unsigned integer
- 4 bytes: payload checksum
- N bytes: typed payload

Transport receivers must reject frames whose payload length exceeds the hard
P2P payload cap before attempting to read the payload. The current cap is:

```text
MAX_P2P_FRAME_PAYLOAD_SIZE = 8_000_000 bytes
```

This cap exists to prevent unauthenticated peers from advertising very large
payload lengths and forcing excessive memory allocation or long reads.

## Message Families

Initial message set:

- `version`
- `verack`
- `ping`
- `pong`
- `getaddr`
- `addr`
- `inv`
- `getdata`
- `tx`
- `block`
- `getheaders`
- `headers`
- `getblocks`

`getaddr` / `addr` are discovery-only messages. They help nodes exchange bounded peer candidates and do not carry any consensus authority.

## Synchronization Strategy

Synchronization is intended to be header-first:

1. exchange versions
2. request headers from one or more suitable peers
3. validate header linkage, proof of work, and expected difficulty where possible
4. compare cumulative work across competing header tips
5. open a bounded moving block-download window for the strongest known header chain
6. request blocks in parallel from multiple healthy peers with per-peer in-flight caps
7. reassign overdue block requests when peers stall
8. apply full block validation before activating any new chain tip

Operational notes:

- `headers` improve download planning but do not bypass full block validation
- block downloads are not pinned to the same peer that first supplied the headers
- bounded windows and timeout-based reassignment avoid unbounded orphan and stall behavior
- peer misbehavior and temporary bans still apply during sync for malformed or invalid protocol data

## Serialization Requirement

Consensus-critical objects must use deterministic serialization. The exact wire format may differ from internal storage encoding, but both must be explicit and versioned.

## Transaction Signatures

Ordinary spend transactions use real secp256k1 ECDSA signatures over a deterministic per-input payload.

For input index `i`, the signing payload is:

1. the transaction serialized with all input signatures and public keys stripped
2. the current `input_index`
3. the referenced previous output value in integer `Chipbits`
4. the referenced previous output recipient address
5. a fixed signing mode marker

The final digest signed and verified by consensus is `double_sha256(signing_payload)`.

Validation rules:

- the provided SEC1 public key must be a valid secp256k1 point
- `public_key_to_address(public_key)` must match the referenced UTXO recipient
- the ECDSA signature must verify against the canonical digest
- any mutation of outputs, metadata, previous-output binding, or input ordering invalidates the signature

## Post-Quantum Testnet Addresses

Chipcoin also defines an experimental post-quantum UTXO ownership path for
testnet/devnet under the `CHCQ` address prefix. This does not change PoW,
block hashes, txids, Merkle roots, block format, or mining consensus.

CHCQ addresses use:

```text
CHCQ + Base58Check(0x50 || scheme_id:uint8 || SHA3-256(raw_pq_public_key))
```

Address parsing is longest-prefix-first: `CHCQ` before `CHC`.

Transaction version `1` remains byte-identical. Transaction version `2` adds a
per-input `sig_scheme_id:uint8` before the input signature/public key fields.
The v2 signature digest includes:

```text
chipcoin:tx-signature:v2:<network>
```

See `docs/post-quantum-addresses.md` for the scheme registry, activation
heights, backend policy, and required frozen test vectors.

Wallets keep private keys off-node. Nodes only receive signed transactions and verify them during mempool admission and block validation.

## Validity vs Policy

Chipcoin v2 distinguishes between:

- consensus validity: rules every node must enforce for blocks and transactions
- mempool policy: local admission and retention rules for unconfirmed transactions

Consensus validity currently includes:

- deterministic transaction serialization
- per-input secp256k1 signature verification
- referenced-UTXO ownership checks
- value conservation and coinbase rules
- block-level proof-of-work and subsidy validation

Mempool policy currently includes:

- minimum fee for ordinary transactions
- duplicate rejection
- conflict rejection for transactions spending already-reserved inputs
- output recipient address standardness checks
- size and input/output-count limits
- transaction TTL expiry
- simple capacity-based eviction of lowest-fee, oldest entries

## Block Assembly

Chipcoin block assembly is deterministic and intentionally simple.

Transaction selection:

- fee-rate is computed as `fee_chipbits / weight_units`
- `weight_units` currently equals serialized transaction byte length
- equivalently: `1 serialized byte = 1 weight unit`
- selection compares fee-rate using integer cross-multiplication, not floats
- ties are broken by higher absolute fee, then earlier mempool admission time, then lower `txid`

Dependency handling:

- a child transaction can be included only if its parent transaction is already confirmed or already selected earlier in the same block
- selected transactions are ordered so ancestors always appear before descendants

Block limit:

- the current limit uses `max_block_weight`
- the miner reserves budget for coinbase first
- then it includes mempool transactions until the remaining weight budget is exhausted

A transaction may be consensus-valid but still be rejected from mempool for policy reasons. Such a transaction is non-standard, not necessarily invalid by consensus.

## Deferred Work

This skeleton does not implement:

- peer scoring logic
- anti-abuse protections
