# Mixed-version local P2P gate

Run from the node-resilience RC checkout. This test starts one process from the
official `mainnet-v0.1.2` Core source and two processes from the candidate.
All three bind loopback only, use disposable SQLite databases and a synthetic
easy-target Mainnet *profile*, and mine ten local blocks. No public Mainnet
endpoint, database, wallet or production key is used.

```bash
mkdir -p /tmp/chipcoin-node-v012-source
git archive --format=tar --output=/tmp/chipcoin-node-v012-source.tar mainnet-v0.1.2 src/chipcoin
tar -xf /tmp/chipcoin-node-v012-source.tar -C /tmp/chipcoin-node-v012-source
python3 tests/integration/resilience/mixed_version_gate.py /tmp/chipcoin-node-v012-source "$PWD"
```

The gate asserts that the old process imports Core from the extracted source,
then checks peer handshakes and convergence on height, hash and cumulative work.
It also injects one malformed peer and one NULL legacy header into a candidate
node, and verifies that P2P header exchange repairs the record without restart.
The test requires permission to bind local TCP sockets. `MIXED_VERSION_P2P_PASS`
is printed only after all assertions succeed.
