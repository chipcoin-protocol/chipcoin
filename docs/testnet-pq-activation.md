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
