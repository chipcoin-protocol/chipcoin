# Chipcoin Post-Quantum Threat Model

This threat model covers application integration and node operation around CHCQ
and ML-DSA-44. It is not a mathematical cryptanalysis of ML-DSA.

| Risk | Asset | Attacker capability | Attack path | Existing mitigation | Existing test | Residual risk | Future work |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Malformed PQ transaction DoS | node CPU | submit many invalid PQ txs | oversized/truncated signatures reaching verifier | mempool PQ precheck before UTXO/verifier | `tests/pq/test_transaction_validation_hardening.py` | parser still pays deserialization cost | P2P raw tx byte caps per peer |
| CPU exhaustion | verifier capacity | relay valid but expensive PQ txs | many ML-DSA inputs | `MAX_PQ_INPUTS`, sigop cost, template cap | hardening tests | limits are policy, not block consensus | tune from testnet telemetry |
| Memory exhaustion | mempool/runtime | many large txs | large public keys/signatures/metadata | generic max tx size plus PQ size policy | local node and hardening tests | raw P2P buffering cost remains | monitor per-peer raw decode pressure |
| Scheme confusion | funds/consensus | craft mismatched scheme/address | ECDSA key with ML-DSA scheme or reverse | address scheme must match input scheme; CHCQ commitment check | readiness malformed tests | none known | add more cross-scheme fuzzing |
| Cross-network replay | funds/network isolation | replay signed tx across networks | same tx on devnet/testnet | v2 signing domain includes network | serialization/browser parity tests | legacy v1 remains legacy behavior | keep v2-only for PQ spends |
| Activation bypass | consensus | submit CHCQ before height | output or spend before activation | activation checks for outputs and v2 spends | readiness suite | none known | monitor pre-activation rejection counters |
| Downgrade | funds | encode PQ spend as v1 | v1 input with nonlegacy scheme | v1 nonlegacy rejected in serialization/stateless validation | serialization and readiness tests | none known | keep wallet send PQ disabled until complete |
| Browser dependency update | browser interop | compromised or breaking npm package | Noble internal API changes | exact version, adapter, frozen vectors, Chromium CI | browser tests | supply-chain risk remains | consider vendored WASM/C backend later |
| Frozen vector divergence | release quality | accidental code drift | Python/TS serialization/signing mismatch | frozen fixtures and parity tests | wallet/browser tests | fixtures can become stale if not reviewed | require explicit vector review on upgrades |
| Oversized block workload | validator CPU | miner includes many valid PQ spends | block with many ML-DSA verifies | consensus max block weight; local template PQ cap | consensus validation tests | block consensus has no PQ sigop cap | collect telemetry before considering consensus change |
| Mempool spam | node memory/CPU | many unique txids | semantically equivalent PQ txs | duplicate/double-spend and policy checks | mempool tests | no fee-market-specific PQ tuning | consider PQ fee policy after activation data |
| Reorg across activation | chainstate/mempool | reorg to lower tip | disconnected CHCQ tx readmitted below activation | mempool reconciliation validates under new tip | PQ reorg boundary test | rare edge depends on stored branch work | monitor activation window |
| Incorrect API metadata | explorer/users | ambiguous tx metadata | missing `sig_scheme_id` or address kind | service/presenter metadata derivation | HTTP API/readiness tests | explorer may render unknowns | keep unknown display explicit |
| Compromised private key | funds | key theft | sign valid spends | standard key security assumptions | out of test scope | PQ keys not browser-stored yet | define PQ backup/storage before UI send |
| Weak entropy | funds | bad key generation seed | predictable wallet key | Python keygen validates seed length; deterministic tests separate | wallet tests | production entropy quality outside consensus | document wallet entropy requirements |
| Native backend supply chain | consensus implementation | malicious vendored code | compromised `mldsa-native` | pinned backend, size assertions, vectors | conftest/backend tests | external audit needed | vendor provenance review |
| Log/metric amplification | disk/ops | many rejected txs | logs include large payloads | structured logs omit keys/signatures | hardening audit | high rate still creates log volume | rate-limit repeated rejection logs if needed |
| Silent fallback | consensus safety | backend unavailable | fallback to fake verifier | no production fallback; unavailable backend errors | tests/conftest, validation tests | deployment packaging risk | startup health check for backend |

## Security Assumptions

- ML-DSA-44 implementation behaves according to its upstream specification.
- Node operators deploy a build that includes the pinned native backend.
- Public testnet peers upgrade before height `30000`.
- Local policy limits are not relied on for block consensus.
- Browser PQ signing remains disabled until a separate storage and UX design is
  implemented.

## Recommended Future Work

- Add long-running post-activation PQ mempool load tests.
- Add per-peer raw transaction decode pressure metrics.
- Commission external review of `mldsa-native` vendoring and build chain.
- Define browser PQ key storage, backup and recovery before enabling send.
- Use testnet telemetry to tune PQ policy limits before mainnet planning.
