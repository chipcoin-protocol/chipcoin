# Chipcoin Central Mainnet Explorer Requirements

The operational Chipcoin explorer lives in the separate Chipcoin Central
repository. The incomplete `apps/explorer` directory in this repository is not
the deployed testnet explorer and must not be used as a mainnet release gate.

Mainnet explorer work must be performed and reviewed in Chipcoin Central. It
must satisfy the following checklist before public mainnet infrastructure is
enabled:

- [ ] Provide explicit, separate `testnet` and `mainnet` configurations.
- [ ] Use separate node API endpoints for testnet and mainnet.
- [ ] Query the API health/status response and verify its `network` value.
- [ ] Fail closed when the configured network and API response do not match.
- [ ] Never silently fall back from mainnet to a testnet endpoint.
- [ ] Support ML-DSA-44 `CHCQ` addresses in routes, validation, search,
      summaries, history, and links.
- [ ] Display mainnet blocks and the mainnet genesis without testnet assumptions.
- [ ] Display version-2 PQ transactions and ML-DSA-44 input schemes.
- [ ] Display PQ outputs, UTXOs, maturity, spent status, and values correctly.
- [ ] Display reward-node registrations, attestations, settlements, and CHCQ
      payouts wherever reward-node data is exposed.
- [ ] Show an unambiguous `TESTNET` or `MAINNET` label on every network view.
- [ ] Keep browser and API routes network-scoped so links cannot cross networks.
- [ ] Ensure no testnet hostname, API path, activation height, or explorer link
      is hardcoded into the mainnet configuration or build.
- [ ] Add tests for network mismatch, CHCQ addresses, PQ transaction rendering,
      and separate testnet/mainnet links.
- [ ] Verify deployment against a private mainnet API before public exposure.

No Chipcoin Central source is copied or duplicated into this repository.
