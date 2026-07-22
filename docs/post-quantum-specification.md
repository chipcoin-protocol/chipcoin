# Chipcoin Post-Quantum Specification And Audit

## Scope

This document describes the Post-Quantum (PQ) implementation that exists in this
repository today. It is an internal engineering specification, not a new
protocol proposal. It documents code paths, activation rules, node-local policy,
operational tooling, tests and residual risks for the scheduled testnet
activation at height `30000`.

This audit does not change consensus rules, transaction serialization, the
activation height, public API shape, explorer behavior, browser-wallet send
behavior, or the ML-DSA implementation.

## Status

- Core Python supports ML-DSA-44 signing and verification through the pinned
  vendored native backend in `src/chipcoin/crypto/pq/mldsa.py`.
- CHCQ addresses are recognized by core, API, explorer and browser wallet.
- Transaction v2 carries `sig_scheme_id` per input.
- Testnet and devnet CHCQ/v2 wallet-spend activation remains height `30000`.
- Browser ML-DSA exists only behind disabled test/debug internals; send/spend
  CHCQ remains disabled in browser UI.
- Operational readiness is covered by pytest, `pq-smoke`, `pq-benchmark`, and
  `pq-audit-report`.

## Threat Model

The primary node threat is malformed or adversarial PQ transactions consuming
CPU or memory before they fail validation. Secondary threats are scheme
confusion, cross-network replay, activation bypass, serialization divergence,
browser/core drift, and misleading operational metrics.

The hardening target is fail-cheap behavior for invalid PQ transactions while
preserving block consensus compatibility.

## End-To-End Pipeline

| Step | Code | Input | Output | Controls | Failure mode | Scope | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ML-DSA key generation | `wallet_key_from_mldsa44_seed()` in `src/chipcoin/wallet/signer.py`; `derive_mldsa44_keypair()` in `src/chipcoin/crypto/pq/mldsa.py` | 32-byte seed | wallet key, public key, CHCQ address | seed length, backend key sizes | `ValueError`, `MLDsaBackendUnavailable` | wallet/runtime | `tests/wallet/test_wallet_signer.py`, `tests/wallet/test_mldsa44_browser_interop.py` |
| CHCQ derivation | `public_key_to_pq_address()` in `src/chipcoin/crypto/addresses.py` | public key, scheme id | `CHCQ...` address | scheme byte range, SHA3-256 commitment | `ValueError` | address format | `tests/wallet/test_pq_browser_vector_fixture.py`, browser address tests |
| CHCQ parsing | `parse_address()` in `src/chipcoin/crypto/addresses.py` | address string | `AddressInfo(kind="pq")` | longest-prefix-first, Base58Check, version `0x50`, 32-byte commitment | `ValueError` | consensus input/output recognition | `tests/node/test_http_api.py`, browser address tests |
| Output construction | `TransactionSigner.build_signed_transaction()` in `src/chipcoin/wallet/signer.py` | recipient address | `TxOutput` | address parse and output amount checks downstream | validation errors | wallet/consensus | `tests/pq/test_activation_readiness.py`, `tests/node/test_cli.py` |
| v2 serialization | `serialize_transaction()` in `src/chipcoin/consensus/serialization.py` | `Transaction(version>=2)` | bytes | one-byte `sig_scheme_id`, varint fields, v1 non-legacy rejection | `ValueError` | consensus wire/hash | `tests/consensus/test_serialization.py`, browser parity tests |
| v2 signing payload | `serialize_transaction_for_signing()` | unsigned-stripped tx, previous output, network | signing payload | previous output value/recipient, input index, domain string | `IndexError`, serialization errors | consensus signing | `tests/consensus/test_serialization.py`, `apps/browser-wallet/tests/unit/transaction_parity.test.ts` |
| Sighash v2 | `transaction_signature_digest()` in `src/chipcoin/consensus/validation.py` | signing payload | 32-byte double-SHA256 digest | network domain `chipcoin:tx-signature:v2:<network>` | deterministic mismatch rejects signature | consensus | Python/browser frozen vectors |
| ML-DSA signing | `SignatureScheme.sign()` via `sign_mldsa44()` | 32-byte seed, 32-byte digest | 2420-byte signature | seed and digest length; backend output size | `ValueError`, backend error | wallet/CLI | `tests/wallet/test_wallet_signer.py`, `tests/wallet/test_mldsa44_browser_interop.py` |
| ML-DSA verification | `_validate_standard_input_signature()` | public key, digest, signature | valid/invalid | activation, scheme, sizes, commitment, backend verify | `ContextualValidationError` | consensus | `tests/consensus/test_validation.py`, readiness suite |
| Mempool precheck | `enforce_pq_mempool_precheck()` in `src/chipcoin/pq/policy.py` | candidate tx | pass/reject | version for PQ inputs, scheme, sizes, input count, sigops, tx size, CHCQ scheme | `ValidationError` before verifier | node-local policy | `tests/pq/test_transaction_validation_hardening.py` |
| UTXO lookup | `validate_transaction_stateful()` | tx input outpoints | UTXO entries | existence, maturity | contextual rejection | consensus | validation/readiness tests |
| Mempool acceptance | `MempoolManager.accept()` | tx | `AcceptedTransaction` | duplicate, known-on-chain, double-spend, fees, precheck | `ValidationError` | node-local policy plus consensus validation | `tests/node/test_local_node.py`, PQ hardening tests |
| P2P relay | `NodeRuntime._handle_tx_message()` and `record_pq_relay()` | relayed tx | inv broadcast | mempool acceptance first | tx dropped/logged | node-local relay policy | runtime tests plus PQ metrics coverage |
| Mining template | `MiningCoordinator.build_template()` in `src/chipcoin/node/mining.py` | mempool entries | candidate block | weight, dependencies, reward controls, PQ signature cost | entry skipped | node-local template policy | hardening and mining tests |
| PQ sigops | `pq_sigop_count()` and `pq_signature_cost()` | tx | count/cost | ML-DSA-44 inputs only | over-limit skipped/rejected by policy | node-local | `tests/pq/test_transaction_validation_hardening.py` |
| Block validation | `validate_block()` and `validate_block_stateful()` | block | total fees | stateless tx checks, double-spend, UTXO, signatures, coinbase | validation error | consensus | `tests/consensus/test_validation.py`, readiness suite |
| Apply block | `NodeService.apply_block()` | valid block | persisted chainstate | block validation before write | block rejected | consensus state transition | node/local/readiness tests |
| Reorg/rollback | `NodeService.activate_chain()` | target tip | active chain switch | replay active branch, reconcile mempool | disconnected tx readmission only if valid under new tip | consensus replay plus node-local mempool | `tests/pq/test_activation_readiness.py::test_reorg_below_activation_does_not_readd_chcq_transaction_to_mempool` |
| API metadata | `_transaction_scheme_metadata()` in `src/chipcoin/node/service.py`; presenters | tx/address | `sig_scheme_id`, `sig_scheme_name`, `address_kind`, `address_scheme_id` | parse and scheme registry | unknown metadata reported safely | public read API | `tests/node/test_http_api.py`, readiness API test |
| Explorer | Chipcoin Central explorer code in `../chipcoin-central` | API metadata | badges/stats | read-only API proxy | unknown displayed as unknown | external UI | browser/explorer manual and prior CI checks |
| Browser wallet | `apps/browser-wallet/src/shared/address_scheme.ts`, `src/crypto/mldsa44.ts` | API/address/vector data | labels, watch-only, test-only signing | feature flag false, send validation blocks CHCQ | no PQ send exposed | UI/application | browser npm tests, Chromium CI, Firefox run |
| Readiness suite | `tests/pq/test_activation_readiness.py` | local test params | pytest pass/fail | activation override height 20 | test failure | test-only | `python -m pytest tests/pq/test_activation_readiness.py -q` |
| Smoke command | `src/chipcoin/pq/readiness.py`, `src/chipcoin/tools/pq_smoke.py` | temp local node | READY/FAIL | activation override, real API serialization | non-zero exit | operational test | `tests/pq/test_pq_smoke_command.py` |
| Benchmark | `src/chipcoin/tools/pq_benchmark.py` | local crypto backend | timing report | same 32-byte digest class for ECDSA/PQ verify | non-zero only on runtime error | operational measurement | `tests/pq/test_transaction_validation_hardening.py` |
| Runtime metrics | `PQMempoolMetrics`, `NodeRuntime._log_runtime_memory_metrics()` | validation/relay/mining events | structured log counters | no key/signature logging | metrics gap only | observability | PQ hardening and validation observer tests |

## Consensus Versus Node-Local Policy

### Consensus Rules

| Rule | Code | Notes |
| --- | --- | --- |
| Activation height | `src/chipcoin/consensus/pq_activation.py` | testnet/devnet `30000`; test overrides only via `ConsensusParams.pq_support_activation_height` |
| Transaction v1 scheme gating | `validate_transaction_stateless()` and `serialize_transaction()` | v1 inputs cannot declare non-legacy schemes |
| Transaction v2 scheme byte | `serialize_transaction()` | `sig_scheme_id` encoded as one byte for version >= 2 |
| Known scheme IDs | `src/chipcoin/crypto/pq/schemes.py` | unknown scheme rejected for version >= 2 |
| CHCQ output activation | `_validate_transaction_outputs_for_activation()` | CHCQ outputs rejected before activation |
| v2 wallet spend activation | `_validate_standard_input_signature()` | v2 wallet spends rejected before activation |
| CHCQ spend ownership | `_validate_standard_input_signature()` | input scheme must match address scheme and public-key SHA3 commitment |
| Digest and network binding | `transaction_signature_digest()` | v2 payload includes `chipcoin:tx-signature:v2:<network>` |
| Signature validity | `_validate_legacy_input_signature()`, `_validate_standard_input_signature()` | ECDSA and ML-DSA verify against same transaction digest model |
| Block validity | `validate_block()` | validates each included transaction and staged UTXO transitions |
| Serialization/hash identity | `serialize_transaction()`, `Transaction.txid()` | consensus byte representation |

### Node-Local Policy

| Policy | Code | Consensus impact |
| --- | --- | --- |
| `MAX_PQ_INPUTS` | `src/chipcoin/pq/policy.py` | mempool standardness only |
| `MAX_PQ_TX_SIZE` | `src/chipcoin/pq/policy.py` | mempool standardness only |
| `MAX_PQ_SIGOPS_PER_TX` | `src/chipcoin/pq/policy.py` | mempool standardness only |
| `MAX_PQ_SIGOPS_PER_BLOCK` | `src/chipcoin/pq/policy.py`, mining template | local block-template selection only |
| PQ signature cost | `pq_signature_cost()` | logging/metrics/template policy only |
| Cheap precheck | `enforce_pq_mempool_precheck()` | blocks may still validate by consensus if valid |
| Runtime counters | `PQMempoolMetrics` | observability only |
| Relay counters | `record_pq_relay()` | observability only |
| Benchmark | `pq_benchmark.py` | no protocol effect |

No node-local PQ policy is applied inside `validate_block()` as a block validity
condition. This is the critical separation that prevents local policy tuning from
causing consensus divergence.

## Constants Inventory

| Constant | Value | Python source | Browser/source counterpart | Guard |
| --- | ---: | --- | --- | --- |
| Legacy ECDSA scheme | `0` | `crypto/pq/schemes.py` | `shared/address_scheme.ts` | API/browser tests |
| ML-DSA-44 scheme | `10` | `crypto/pq/schemes.py` | `crypto/mldsa44.ts`, `shared/address_scheme.ts` | frozen vectors |
| Reserved ML-DSA-65 | `11` | `crypto/pq/schemes.py` | display as unknown/registered | policy tests |
| Reserved Falcon | `20` | `crypto/pq/schemes.py` | display as unknown/registered | audit report |
| Reserved SPHINCS+ | `30` | `crypto/pq/schemes.py` | display as unknown/registered | audit report |
| CHCQ prefix | `CHCQ` | `crypto/addresses.py` | `crypto/addresses.ts` | address tests |
| CHCQ version | `0x50` | `crypto/addresses.py` | `crypto/addresses.ts` | address tests |
| PQ commitment | `32` bytes | `crypto/addresses.py` | `crypto/addresses.ts` | vectors |
| PQ tx version | `2` | `consensus/pq_activation.py` | transaction parity tests | serialization tests |
| Digest length | `32` bytes | `pq/policy.py`, mldsa/signatures validators | `crypto/mldsa44.ts` | interop tests |
| ML-DSA seed | `32` bytes | `crypto/pq/mldsa.py` | `crypto/mldsa44.ts` | interop tests |
| ML-DSA public key | `1312` bytes | `crypto/pq/mldsa.py` | `crypto/mldsa44.ts` | interop tests |
| ML-DSA private key | `2560` bytes | backend assertion/audit report | `crypto/mldsa44.ts` | audit report, interop tests |
| ML-DSA signature | `2420` bytes | `crypto/pq/mldsa.py` | `crypto/mldsa44.ts` | interop tests |
| Testnet activation | `30000` | `consensus/pq_activation.py` | `shared/constants.ts`, fixtures/docs | smoke/audit tests |
| Domain separator | `chipcoin:tx-signature:v2:<network>` | `consensus/serialization.py` | transaction parity fixture | serialization parity |
| Noble version | `0.6.1` | browser package metadata/docs | `crypto/mldsa44.ts` | browser tests |

Duplications between Python and TypeScript are intentional language-boundary
duplications. They are guarded by frozen vectors, Python/browser parity tests,
Chromium runtime CI, and Firefox verification.

## Cryptographic Integration Audit

Chipcoin signs a 32-byte transaction digest, not an arbitrary application
message. For transaction v2, the signing payload includes previous output value,
previous output recipient, input index, and the network-domain string before
double-SHA256. The ML-DSA backend receives that raw digest directly.

Properties verified by tests:

- malformed public-key and signature lengths fail before verifier calls;
- wrong public key fails CHCQ commitment matching;
- wrong scheme id fails scheme/address matching;
- altered signature fails verification;
- a v2 digest for one network does not match another network's domain-separated
  payload;
- browser Noble raw-digest signing matches Python `mldsa-native` vectors;
- browser UI does not expose PQ send/spend or persistent PQ key storage.

Residual assumptions:

- this is not a mathematical audit of ML-DSA;
- JavaScript zeroization is best-effort only;
- browser signing remains experimental and disabled until separate wallet UX and
  storage work is completed.

## Serialization Audit

Transaction serialization is deterministic:

- version is little-endian `uint32`;
- input/output counts and bytes/strings use repository varints;
- `sig_scheme_id` is encoded only for transaction version >= 2;
- signatures and public keys are length-prefixed byte arrays;
- output values are little-endian `uint64`;
- recipients and metadata strings are UTF-8 length-prefixed fields;
- metadata keys are sorted.

Current parser hardening rejects truncated extended varints with `ValueError`.
Existing tests cover v1/v2 byte identity, signing payload domain bytes, browser
unsigned transaction bytes, signing digest parity, and corrupted serialization in
the activation readiness suite.

## Activation Rules

Production/testnet activation height is read from
`pq_support_activation_height("testnet")` and remains `30000`. Test-only low
heights are created by `make_pq_readiness_params()` in `src/chipcoin/pq/readiness.py`.
The override is scoped to local `ConsensusParams` instances used by tests and
smoke runs.

Before activation:

- CHCQ outputs are rejected;
- CHCQ spends are rejected;
- v2 wallet spends are rejected;
- legacy CHC transactions continue to work.

After activation:

- CHC to CHCQ outputs can be mined;
- CHCQ to CHC and CHCQ to CHCQ spends validate through ML-DSA-44;
- legacy ECDSA transactions continue to coexist.

Reorg behavior is covered by a PQ boundary test that disconnects a post-activation
CHCQ transaction and reactivates a pre-activation tip. The disconnected CHCQ
transaction is not re-added to mempool while the next height is below activation.

## DoS And Resource Usage

The intended cheap-to-expensive order is:

1. P2P frame/message decode limits.
2. Transaction deserialization.
3. Generic mempool size/input/output policy.
4. PQ version/scheme checks.
5. PQ public-key/signature length checks.
6. PQ input count and signature-cost checks.
7. Serialized PQ transaction size policy.
8. Address parsing.
9. Duplicate/double-spend checks.
10. UTXO overlay lookup.
11. Sighash construction.
12. ML-DSA verification.

Malformed signatures, oversized keys, reserved schemes and wrong versions now
fail before UTXO overlay construction and before native verifier calls. Logging
includes txid, version, counts and PQ cost; it never logs public keys, signatures,
seeds or private keys.

## Benchmark Methodology

`chipcoin pq-benchmark` compares ECDSA and ML-DSA verification over the same
logical input class: a valid signature over an already-calculated 32-byte
transaction digest. It reports mean, median, max, standard deviation, throughput,
Python version, platform, process CPU time and RSS delta.

The numbers are implementation-specific and hardware-specific. They should be
used for operational sizing of the current Chipcoin implementation, not as a
general claim that ML-DSA is universally faster than ECDSA.

## Test Coverage Matrix

| Requirement | Primary tests |
| --- | --- |
| Key generation | `tests/wallet/test_wallet_signer.py`, `tests/wallet/test_mldsa44_browser_interop.py` |
| Address derivation | `tests/wallet/test_pq_browser_vector_fixture.py`, browser address tests |
| Serialization parity | `tests/consensus/test_serialization.py`, `apps/browser-wallet/tests/unit/transaction_parity.test.ts` |
| Signing digest | serialization tests, browser parity fixture |
| Valid signature | `tests/consensus/test_validation.py`, readiness suite |
| Invalid signature | `tests/pq/test_activation_readiness.py`, consensus validation tests |
| Malformed key/signature | consensus validation and PQ hardening tests |
| Scheme mismatch | readiness malformed tests |
| Pre-activation rejection | readiness suite, local node tests |
| Post-activation acceptance | readiness suite, smoke command |
| CHC -> CHCQ | readiness suite, smoke command |
| CHCQ -> CHC | readiness suite, smoke command |
| Mempool precheck | `tests/pq/test_transaction_validation_hardening.py` |
| Mining template | local node/mining tests plus PQ signature-cost policy |
| Block validation | consensus validation tests |
| Reorg boundary | `test_reorg_below_activation_does_not_readd_chcq_transaction_to_mempool` |
| API metadata | readiness API test, `tests/node/test_http_api.py` |
| Explorer metadata | browser/explorer display tests in Chipcoin Central and browser scheme tests |
| Browser parity | npm tests, frozen fixtures |
| Chromium runtime | `.github/workflows/browser-pq-chromium.yml` |
| Firefox runtime | documented local verification |
| Benchmark command | PQ hardening tests |
| Metrics | PQ hardening tests and block observer test |
| Audit report | `tests/pq/test_pq_audit_report.py` |

## Known Limitations And Residual Risks

- Browser CHCQ send/spend and persistent PQ key storage are intentionally absent.
- Public testnet activation at the real height cannot be fully proven before it
  happens; local readiness and smoke tests simulate the same rules with scoped
  params.
- Explorer global PQ statistics are recent-window diagnostics, not chain-wide
  consensus state.
- External auditors should review the vendored ML-DSA backend and build chain
  before mainnet use.
- Local policy limits may need testnet telemetry tuning, but must not be moved
  into consensus without a separate protocol change.

## Upgrade Constraints

- Do not change `SIG_SCHEME_ML_DSA_44`, CHCQ format, transaction v2 encoding, or
  activation height without explicit consensus-change review.
- Do not upgrade browser `@noble/post-quantum` without frozen vector, Chromium,
  Firefox and Python/browser interop passing.
- Do not replace `mldsa-native` without regenerating and reviewing test vectors.
- Do not expose browser PQ send until storage, backup, UX warnings and recovery
  behavior are separately specified and tested.

## Activation Checklist

Use `docs/post-quantum-activation-checklist.md` as the operational checklist for
the height-30000 rollout.
