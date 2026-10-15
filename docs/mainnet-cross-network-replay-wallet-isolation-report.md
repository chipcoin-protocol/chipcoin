# MAINNET CROSS-NETWORK REPLAY AND WALLET ISOLATION REPORT

Date: 2026-10-06

MemPalace was consulted before the implementation and workflow audit. The test
used production wallet signing, signed-login, endpoint validation, transaction
serialization, and consensus validation paths. No negative artifact was sent to
the live mainnet rehearsal.

## Network And Domain Identity

| Property | Mainnet | Testnet |
|---|---|---|
| Network ID | `mainnet` | `testnet` |
| P2P magic | `f9beb4d9` | `fab4c0de` |
| Genesis hash | `00000007f247394d7ddec57448af5a635aa53465ad06d8d5ede66f812cfe7cc6` | `00029fa9f23d4d3c927ffb9e27a03cc381d71698e3ca82ccdf25516252d9fc7c` |
| PQ activation | height 0 | height 20000 |
| Login domain | `chipcoin:web-auth:v1:mainnet` | `chipcoin:web-auth:v1:testnet` |
| Transaction domain | `chipcoin:tx-signature:v2:mainnet` | `chipcoin:tx-signature:v2:testnet` |

CHCQ strings are deliberately network-neutral addresses. Network isolation is
therefore enforced by endpoint identity checks and the login/transaction
signature domains, rather than by pretending the same CHCQ string has a
network-specific encoding.

## Runtime Matrix

| Case | Source network | Target network | Same artifact | Expected | Actual | Rejection reason | Result |
|---|---|---|---|---|---|---|---|
| PQ signed login | mainnet | mainnet | yes | ACCEPT | ACCEPT | - | PASS |
| PQ signed login replay | mainnet | testnet | yes | REJECT | REJECT | Signature false under testnet digest; production signer also returns `UNSUPPORTED_NETWORK` | PASS |
| PQ signed login | testnet | testnet | yes | ACCEPT | ACCEPT | - | PASS |
| PQ signed login replay | testnet | mainnet | yes | REJECT | REJECT | Signature false under mainnet digest; production signer also returns `UNSUPPORTED_NETWORK` | PASS |
| PQ transaction | mainnet | mainnet | yes | ACCEPT | ACCEPT | - | PASS |
| PQ transaction replay | mainnet | testnet | yes | REJECT | REJECT | `Input signature is invalid.` | PASS |
| PQ transaction | testnet | testnet | yes | ACCEPT | ACCEPT | - | PASS |
| PQ transaction replay | testnet | mainnet | yes | REJECT | REJECT | `Input signature is invalid.` | PASS |
| API endpoint identity | testnet | mainnet wallet | yes | REJECT | REJECT | `Wrong network. Expected mainnet, got testnet.` | PASS |
| API endpoint identity | mainnet | testnet wallet | yes | REJECT | REJECT | `Wrong network. Expected testnet, got mainnet.` | PASS |
| Persisted wallet state | mainnet -> testnet -> mainnet | browser storage | yes | ISOLATED | ISOLATED | Network-scoped keys restore the original mainnet state | PASS |

The browser test replayed the exact login message/signature and transaction
signature without re-signing. The Docker transaction test used the same raw
serialized transaction and signature against both production validation
contexts. Rejected artifacts did not consume the source UTXO or create outputs.

## Browser And Wallet Paths

- `background/session.ts::signProviderLoginMessage()` accepted matching network
  messages and rejected mismatched selected-network context.
- `provider/login_message.ts` accepted both same-network controls and rejected
  both cross-network signature replays cryptographically.
- `wallet/build_transaction.ts::buildSignedPqPaymentTransaction()` generated
  ML-DSA-44 scheme-10 signatures that verified only under their source network
  transaction domain.
- `background/session.ts::updateNodeEndpoint()` rejected both endpoint mismatch
  directions without silently changing saved settings.
- Submitted transactions, wallet summary/history cache, and watch-only records
  remained distinct through `mainnet -> testnet -> mainnet`.
- A PQ wallet identity may be used in either explicitly selected context; this
  does not reinterpret balances, history, sessions, or signed artifacts from
  the other network. Legacy-wallet mainnet refusal remains covered by the
  existing network-support regression.

No authenticated cross-network session, accepted cross-network transaction,
mempool mutation, balance mutation, silent network switch, or legacy fallback
was observed.

## Validation And Regressions

- Isolated Docker (`--network none`) production image: two same-artifact
  transaction replay directions PASS; source controls PASS; target rejection
  reason exact; state mutation false.
- Browser wallet unit/runtime suite: 89/89 PASS, including four dedicated
  cross-network tests.
- Consensus, mainnet profile, wallet signer, and HTTP API selection: 99/99 PASS.
- TypeScript typecheck: PASS.
- Chrome production build: PASS.
- Firefox production build: PASS.
- Production ML-DSA bundle inspection: PASS.
- Firefox headless real-browser ML-DSA test: PASS, including signature,
  tamper, wrong-key, and invalid-input rejection.
- Chromium real-browser execution: NOT AVAILABLE on this host because no
  Chromium/Chrome executable is installed. The Chrome production build and the
  shared browser production modules exercised by the dedicated tests passed;
  clean-profile browser operation remains separately scoped to `BW-OPS-001`.

## Rehearsal Read-Only Check

At the final observation A/B/C were converged at height `328`, tip
`00000007e23902a0e04c405b878de9bccb04ba86d75d284119d055d23ba836bd`,
and cumulative work `72093004746`. All three had two handshaken peers and empty
mempools. Both miners were running, the ordinary monitor was active, and the
canonical reward registry contained two registrations with zero active reward
nodes. The rehearsal was not modified by this gate.

## Gate Decision

`PQ-NEG-002` is promoted to `PASS`. No network-isolation or security blocker
was found. The RC count becomes `83 PASS / 8 NOT_RUN / 7 PENDING_HEIGHT / 0 FAIL`.

```text
MAINNET_LOGIN_CONTROL = PASS
TESTNET_LOGIN_CONTROL = PASS
MAINNET_TO_TESTNET_REPLAY_REJECTED = PASS
TESTNET_TO_MAINNET_REPLAY_REJECTED = PASS
TRANSACTION_NETWORK_ISOLATION = PASS
WALLET_STATE_ISOLATION = PASS
CROSS_NETWORK_CONTAMINATION = NO
PQ_NEG_002 = PASS
NETWORK_ISOLATION_BLOCKER = NO
```
