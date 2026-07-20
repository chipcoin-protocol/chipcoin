# Testnet CHCQ Activation Notes

CHCQ post-quantum address support is experimental testnet functionality. It is
not audited yet and must not be marketed as quantum-proof mainnet.

Planned activation constants live in:

```text
src/chipcoin/consensus/pq_activation.py
```

Current scheduled heights:

```text
devnet:  30000
testnet: 30000
mainnet: 0 for future genesis support
```

Before activation, nodes reject CHCQ outputs, CHCQ spends, and v2 wallet spends.
After activation, CHC and CHCQ can coexist.

Activation must not proceed until:

- the vendored `mldsa-native` ML-DSA-44 consensus backend is pinned and built
  reproducibly across node builds
- official FIPS 204/backend KAT tests pass
- v2 sighash and transaction vectors are frozen
- CLI CHCQ generation and spending work against the node backend
- mempool and block rejection-path tests pass
- browser wallet PQ signing remains disabled until it verifies against the node
  consensus backend

## Frozen wallet spend vector 1

This vector exercises one post-activation testnet CHCQ spend built by
`TransactionSigner` with the pinned ML-DSA-44 backend.

```text
network: testnet
activation_height: 30000
seed_hex: 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
scheme_id: 10
scheme_name: mldsa44
address: CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE
private_key_sha256: 04bf6b9f579166a627961dfc5c3bf9717df868db88863856356c4668c8b56b0b
public_key_sha256: 9f107644c1084526af3bc8098680b05499a2325a644e388fb4f970e058d19d46
funding_outpoint: 6666666666666666666666666666666666666666666666666666666666666666:1
funding_value_chipbits: 1234567890
recipient: CHCCH5FG4NCAWBFqa2zZKufrdnAa7rRE1gH5C
amount_chipbits: 1000000000
fee_chipbits: 1000
change_chipbits: 234566890
metadata: {"kind":"payment","purpose":"pq-vector-1"}
signature_digest_hex: 48ee8dd1efdb4bbec4238e823e75619f9308550fb5e901c6a4ba8fb99f6fb539
signature_sha256: d1af5447e0758334b719a99849e10062821f2b7d9fea01be35f2ed15f3a7ccfe
txid: 05eb8549e696aa818d5a20aa585a12959c80ebeaa6035c8a44272caf17f7c2ce
raw_tx_sha256: a873e1e18fca2457bac12386176035be8c80a5de0e4f2eb039d5b15be9198623
raw_tx_len: 3934
```

The regression test lives in `tests/wallet/test_wallet_signer.py` as
`test_transaction_signer_builds_post_activation_pq_vector`.

The browser-wallet parity fixture lives in
`apps/browser-wallet/tests/fixtures/pq-vector-1.json`. It intentionally stores
the unsigned v2 transaction bytes and signing payload/digest, not private key
material. Python verifies the fixture in
`tests/wallet/test_pq_browser_vector_fixture.py`, and browser-wallet unit tests
verify that TypeScript serialization remains byte-compatible before browser-side
ML-DSA signing is enabled.

## Local node regression coverage

`tests/node/test_local_node.py` covers the post-activation node path for:

- legacy CHC input creating a CHCQ output
- CHCQ input spending back to a legacy CHC output
- mempool admission, block template inclusion, block validation, and mempool
  cleanup for the CHCQ spend

The same file keeps the pre-activation rejection test for CHCQ outputs.

## CLI smoke coverage

`tests/node/test_cli.py` covers the operator-facing CHCQ wallet flow:

- `wallet-generate --scheme mldsa44`
- `wallet-address`
- `wallet-utxos`
- `wallet-build`
- `wallet-send` in local submission mode

The smoke test funds a local testnet CHCQ wallet, builds a version 2 transaction,
submits it to the local mempool with post-activation validation enabled, and
asserts that the resulting transaction uses scheme id `10` (`mldsa44`).

`wallet-build` and `wallet-send` output include the wallet address, address kind,
signature scheme id/name, and transaction version so operators can confirm that a
CHCQ wallet is producing a v2 ML-DSA-44 transaction.

## HTTP/API observability coverage

`tests/node/test_http_api.py` covers the explorer-facing CHCQ transaction path:

- `POST /v1/tx/submit` accepts a post-activation CHCQ spend
- `GET /v1/tx/<txid>` exposes transaction version, input signature scheme id/name,
  and output address kind/scheme id
- `GET /v1/mempool` exposes the staged CHCQ transaction metadata
- `GET /v1/address/<address>` and `/utxos` report CHCQ wallet balances
- `GET /v1/address/<address>/history` reports confirmed CHCQ change and legacy
  recipient history after the transaction is mined
