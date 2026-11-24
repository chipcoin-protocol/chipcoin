# Mining Pools — Integrate Chipcoin

**Draft for the website repository; human review required. This is for pool operators, separate from the existing [guide for individual miners](https://chipcoinprotocol.com/pool-mining). Do not modify the live website as part of this handbook patch.**

Chipcoin is an independent SHA-256d proof-of-work network with CHCQ addresses and ML-DSA-44 transaction signatures on Mainnet. Pool operators can request mining templates from a private full node, construct complete canonical blocks, and submit them through the Core's mining HTTP API. [Mainnet v0.1.2](https://github.com/chipcoin-protocol/chipcoin/releases/tag/mainnet-v0.1.2) supports both template-ID submission and complete-block submission; the latter is independent of template-cache expiry. Pool share accounting and Stratum service operation remain the pool's responsibility.

- Mining Pool Integration Handbook — link to `docs/mining-pools/README.md` in the Core repository **after authorized publication**; do not add a live URL before the path exists on the selected public branch.
- [Chipcoin Core source](https://github.com/chipcoin-protocol/chipcoin).
- [Already mining? Individual miner instructions](https://chipcoinprotocol.com/pool-mining).
- For project contact, use the repository's published contact channels; no unverified email or chat endpoint is asserted here.

Editorial follow-up outside this repository: the live [docs page](https://chipcoinprotocol.com/docs) still calls the public testnet the current technical scope, which is inconsistent with the live Mainnet and tagged release. Verify and correct the website copy in its own repository before linking it as a Mainnet integration reference.
