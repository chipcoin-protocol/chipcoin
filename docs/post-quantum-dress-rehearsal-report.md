# Post-Quantum Testnet Dress Rehearsal Report

Status: **PASS**
Activation height: `8`
Duration: `6.783s`

## Summary

- Legacy blocks: `3`
- PQ blocks: `8`
- Legacy transactions: `2`
- PQ transactions: `8`
- PQ verify count: `7`
- PQ verify failures: `1`

## Timeline

- bootstrap genesis/local funding: height=0, block_hash=40fb712e321ca22ec6f144a8cda23f281f1311509dafedcb4e95dc561cff68ad, transactions=1, pq=False
- bootstrap: status=PASS, genesis_like_height=0, miner=CHCCT9A8CEgF7qJ3T6QuXSFQN31kEexxxa2oX, legacy_wallet=CHCCH5FG4NCAWBFqa2zZKufrdnAa7rRE1gH5C, pq_wallet=CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE, api=HttpApiApp
- legacy transaction mined: height=1, block_hash=64de74cfcd6c10c5149e38d111c6077f96c517d8be9a92a85e88b3a4ea0643b8, transactions=2, pq=False
- legacy: status=PASS, txid=7d8202288de34a9d5bcaa4bc27dbace6e80558ad0b8727f08527ca2cbc70c57f, block_hash=64de74cfcd6c10c5149e38d111c6077f96c517d8be9a92a85e88b3a4ea0643b8, api_location=chain
- post-activation empty block: height=9, block_hash=308c8699f2cd637d151b537dfbdef54eacd6bd7e3ed8de6ca644cb631d05c001, transactions=1, pq=False
- activation: status=PASS, previous_height=1, activation_height=8, next_height=9, post_activation_block=308c8699f2cd637d151b537dfbdef54eacd6bd7e3ed8de6ca644cb631d05c001
- first CHCQ address: status=PASS, address=CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE, address_kind=pq, address_scheme_id=10
- first CHC -> CHCQ mined: height=10, block_hash=09bdf6ea6b6298cab45603d8ebf4c2db7abe9d9c681c9801ae1077c4fea48dbf, transactions=2, pq=True
- first CHC -> CHCQ: status=PASS, txid=3a013bf89f328019b07dc51a2ff4cfa29c0e300657dee5e21c3df2bb64482845, block_hash=09bdf6ea6b6298cab45603d8ebf4c2db7abe9d9c681c9801ae1077c4fea48dbf, address_kind=pq
- first CHCQ -> CHC mined: height=11, block_hash=2db51795b51ac94e4e78361452e518638285add15f1f09469e4e7246361582c9, transactions=2, pq=True
- first CHCQ spend: status=PASS, txid=3580afb606a3cbdf8a4ed726230b3381b78b856ca1bd3abedcd6c224801d6cd7, block_hash=2db51795b51ac94e4e78361452e518638285add15f1f09469e4e7246361582c9, sig_scheme_id=10
- mixed legacy and PQ outputs mined: height=12, block_hash=63aaa88fd04521e639aa8f64c8b439a27767f2b16025f31a775858cbc657973e, transactions=3, pq=True
- mixed CHCQ -> CHCQ mined: height=13, block_hash=5d5a06accd1ab6dc470ef231bca3b46c07d4bbc68a72164b066c8bc6ec302c23, transactions=2, pq=True
- mixed traffic: status=PASS, txids=['034e1993d786fb68a2184a6e21ad206d131d8b02c8bfa2d7bef9db0a941ce008', '33f9e6a8293f12561a35d5267cfc112206585d65a6312dfae51f6f2081aecf15', 'b9b308607f51ec87edd73235bd84666cff5d250b3c0ae201ed6ff0189c30baaf'], blocks=['63aaa88fd04521e639aa8f64c8b439a27767f2b16025f31a775858cbc657973e', '5d5a06accd1ab6dc470ef231bca3b46c07d4bbc68a72164b066c8bc6ec302c23']
- stress PQ block 1: height=14, block_hash=4b2ad7091bf6dd6032466b23b4a94a1fca283e3307a6fdac4d770b743129c124, transactions=2, pq=True
- stress PQ block 2: height=15, block_hash=702e9bccfc7ea56149e88d61456f46f5187b7dc952bc55c9d7c161b2305dc44e, transactions=2, pq=True
- stress PQ block 3: height=16, block_hash=66de2a58c0374cab8b5ed5e40e4b895254ebf22275e1ebcc7e99b95c12b3bc95, transactions=2, pq=True
- stress PQ block 4: height=17, block_hash=0da9a358143e9c899667f1d65410ee902f2266e3207c6044572e6aed67aa3523, transactions=2, pq=True
- moderate stress: status=PASS, txids=['37b01273af5cc181e8a0f074e94b2e1d18879e3462c9d50370fe255619c55d4e', '86bdc4e317f7f3b3f7094975de799601ca51de82d840af38eeaae982e68cc1b0', 'c38416d52c8764a11df62a0cb58a2cc0f365b72b58467fad7f803b96f80271c4', '11b342e7be988e96807c181c82f865985943b0154c45b63c244939bf099ea420'], metrics={'pq_verify_count': 6, 'pq_verify_failures': 0, 'pq_verify_duration_seconds_total': 0.000617, 'pq_verify_duration_seconds_avg': 0.000103, 'pq_verify_duration_seconds_max': 0.000113, 'pq_tx_accepted': 8, 'pq_tx_rejected': 0, 'pq_malformed': 0, 'pq_relay': 8, 'pq_mined': 8, 'pq_orphan': 0}
- reorg scenarios: status=PASS, before_activation_reorg_depth=1, during_activation_reorg_depth=2, after_activation_reorg_depth=1
- restart: status=PASS, height=17, mempool_size=0
- fresh sync: status=PASS, blocks_fetched=18, headers_received=18, height=17
- negative tests: status=PASS, pre_activation=CHCQ outputs are not active on this network at this height., wrong_scheme=PQ transaction input uses a non-verification-capable signature scheme., bad_signature=Input signature is invalid., bad_public_key=Input public key does not match the CHCQ commitment., truncated_signature=PQ transaction input signature has the wrong size for ML-DSA-44., oversized=PQ transaction input signature has the wrong size for ML-DSA-44., truncated_encoding=unpack_from requires a buffer of at least 41 bytes for unpacking 4 bytes at offset 37 (actual buffer size is 5)
- API and audit metadata: status=PASS, height=17, audit_activation=30000
- browser fixture/parity/build: status=PASS, npm_test={'command': ['npm', 'test'], 'returncode': 0, 'output_tail': 'marek/Documents/CODEX/Chipcoin-v2/apps/browser-wallet\n\n ✓ tests/unit/submitted_cache.test.ts (5 tests) 7ms\n ✓ tests/unit/api_client.test.ts (2 tests) 14ms\n ✓ tests/unit/transaction_parity.test.ts (7 tests) 141ms\n ✓ tests/unit/address_scheme.test.tsx (18 tests) 44ms\n ✓ tests/unit/recovery_phrase.test.ts (3 tests) 9ms\n ✓ tests/unit/mldsa44.test.ts (12 tests) 301ms\n ✓ tests/unit/selection.test.ts (1 test) 12ms\n ✓ tests/unit/addresses.test.ts (4 tests) 63ms\n ✓ tests/unit/network_support.test.ts (5 tests) 720ms\n   ✓ browser wallet network support > accepts a node endpoint only when the selected network matches 459ms\n ✓ tests/unit/encryption.test.ts (2 tests) 619ms\n   ✓ wallet encryption > round-trips encrypted private key material 367ms\n ✓ tests/unit/session_security.test.ts (4 tests) 1313ms\n   ✓ wallet session security > requires explicit confirmation before revealing a private key from an active session 604ms\n   ✓ wallet session security > recovers the same wallet from the same recovery phrase 372ms\n\n Test Files  11 passed (11)\n      Tests  63 passed (63)\n   Start at  08:23:29\n   Duration  1.78s (transform 993ms, setup 0ms, collect 1.55s, tests 3.24s, environment 3ms, prepare 1.28s)\n\n'}, npm_build={'command': ['npm', 'run', 'build'], 'returncode': 0, 'output_tail': '.js               21.21 kB │ gzip:  6.42 kB\ndist/assets/App-BCOd6VP9.js             24.07 kB │ gzip:  6.45 kB\ndist/assets/address_scheme-B7578J-P.js  46.74 kB │ gzip: 17.99 kB\n✓ built in 564ms\n\n> chipcoin-browser-wallet@0.1.1 build:firefox\n> vite build --mode firefox\n\nvite v5.4.21 building for firefox...\ntransforming...\n✓ 76 modules transformed.\nrendering chunks...\ncomputing gzip size...\ndist/onboarding.html                     0.49 kB │ gzip:  0.29 kB\ndist/settings.html                       0.65 kB │ gzip:  0.32 kB\ndist/popup.html                          0.71 kB │ gzip:  0.34 kB\ndist/assets/popup-d8wEJRZq.css           4.02 kB │ gzip:  1.46 kB\ndist/assets/popup.js                     0.25 kB │ gzip:  0.21 kB\ndist/assets/settings.js                  0.25 kB │ gzip:  0.21 kB\ndist/assets/browser-FzVHYVQq.js          2.48 kB │ gzip:  1.04 kB\ndist/assets/onboarding.js                4.70 kB │ gzip:  1.63 kB\ndist/assets/messages-RCpT5VaZ.js        20.11 kB │ gzip:  8.13 kB\ndist/assets/background.js               21.21 kB │ gzip:  6.42 kB\ndist/assets/App-BCOd6VP9.js             24.07 kB │ gzip:  6.45 kB\ndist/assets/address_scheme-B7578J-P.js  46.74 kB │ gzip: 17.99 kB\n✓ built in 592ms\n'}, bundle={'command': ['npm', 'run', 'test:mldsa:bundle'], 'returncode': 0, 'output_tail': '\n> chipcoin-browser-wallet@0.1.1 test:mldsa:bundle\n> node scripts/inspect-mldsa44-bundle.mjs\n\n{\n  "ok": true,\n  "files": 13,\n  "wasm_assets": 0,\n  "noble_in_production_bundle": false,\n  "csp_has_unsafe_eval": false\n}\n'}
- readiness suite: status=PASS, pytest={'command': ['/home/komarek/Documents/CODEX/Chipcoin-v2/.venv/bin/python', '-m', 'pytest', 'tests/pq/test_activation_readiness.py', '-q'], 'returncode': 0, 'output_tail': '......                                                                   [100%]\n6 passed in 0.73s\n'}
- pq-smoke: status=PASS, ready=True
- pq-benchmark: status=PASS
- pq-audit-report: status=PASS

## Benchmark

- ECDSA verify 1000 median seconds: `0.000417`
- ECDSA verify 1000 throughput/s: `2360.05`
- ML-DSA-44 verify 1000 median seconds: `8.4e-05`
- ML-DSA-44 verify 1000 throughput/s: `11419.04`

## Readiness And Smoke

- Readiness: `PASS`
- Smoke ready: `True`
- Smoke final local height: `10`

## Audit

- Testnet activation height: `30000`
- ML-DSA backend available: `True`
- Policy max PQ inputs: `16`

## Warnings

- none

## Errors

- none

## Checks

- PASS bootstrap
- PASS legacy
- PASS activation
- PASS first CHCQ address
- PASS first CHC -> CHCQ
- PASS first CHCQ spend
- PASS mixed traffic
- PASS moderate stress
- PASS reorg scenarios
- PASS restart
- PASS fresh sync
- PASS negative tests
- PASS API and audit metadata
- PASS browser fixture/parity/build
- PASS readiness suite
- PASS pq-smoke
- PASS pq-benchmark
- PASS pq-audit-report
