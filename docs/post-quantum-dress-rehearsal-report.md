# Post-Quantum Testnet Dress Rehearsal Report

Status: **PASS**
Activation height: `8`
Duration: `7.071s`

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
- legacy transaction mined: height=1, block_hash=1fb2db2fdc7a3abc4e0710bb2482f27537bb3935bf8ca68cfa5d5c359898d5ea, transactions=2, pq=False
- legacy: status=PASS, txid=1fb9d1ce329d50d8aba5c2659a847147b89ae7d1576949766d662d69e831a437, block_hash=1fb2db2fdc7a3abc4e0710bb2482f27537bb3935bf8ca68cfa5d5c359898d5ea, api_location=chain
- post-activation empty block: height=9, block_hash=125c2d59841770c7fb003d4eab3c89e8bcd4ea5ab83cd69f81984421e377d2c1, transactions=1, pq=False
- activation: status=PASS, previous_height=1, activation_height=8, next_height=9, post_activation_block=125c2d59841770c7fb003d4eab3c89e8bcd4ea5ab83cd69f81984421e377d2c1
- first CHCQ address: status=PASS, address=CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE, address_kind=pq, address_scheme_id=10
- first CHC -> CHCQ mined: height=10, block_hash=53cfaa453ab93a0ea222f7d76b0a69392cdcef5ec9f4a23be9f72f390fd1f1de, transactions=2, pq=True
- first CHC -> CHCQ: status=PASS, txid=1d31c942acebc5f3521009c8184e23b54fecc8b123f2fcfaf24a6b1d1a262c74, block_hash=53cfaa453ab93a0ea222f7d76b0a69392cdcef5ec9f4a23be9f72f390fd1f1de, address_kind=pq
- first CHCQ -> CHC mined: height=11, block_hash=05b7e90cbb0cfdc31bfbb9e44bcc79960704d2e37205843cbe8f1c8795eed640, transactions=2, pq=True
- first CHCQ spend: status=PASS, txid=d34337de8295c062370c0b2ec98edc3b7e38574dffa61481d4758a4395356c21, block_hash=05b7e90cbb0cfdc31bfbb9e44bcc79960704d2e37205843cbe8f1c8795eed640, sig_scheme_id=10
- mixed legacy and PQ outputs mined: height=12, block_hash=7ba811e7f605f292911c9c947145ff022ebab73a5cb8ae43c525e9122634ee61, transactions=3, pq=True
- mixed CHCQ -> CHCQ mined: height=13, block_hash=299304b29d9a0715ba5ba5995a8567f14346973aa7cc56265e05b8c39192bbc4, transactions=2, pq=True
- mixed traffic: status=PASS, txids=['ab328b6490d84962cb94b933caee77b69deb3bab5d4ad676857211f91411747e', '1ec7fe1302282f3ccd81de236423d684d89d7fc05b2dcc1d6aaafdd2c13b7d86', '7da9f70423e10e578e0664cef6958e14b1623258a0aac9f7bf66d492a0749796'], blocks=['7ba811e7f605f292911c9c947145ff022ebab73a5cb8ae43c525e9122634ee61', '299304b29d9a0715ba5ba5995a8567f14346973aa7cc56265e05b8c39192bbc4']
- stress PQ block 1: height=14, block_hash=4e3545d4647e551a0a7a0c9afa18e0bdd135f7d83538dfa8f7f357c06005b1b2, transactions=2, pq=True
- stress PQ block 2: height=15, block_hash=66ca93fd8bcd912ee54c54e240859359006c278cf09dbad01a290d8f547e5fc2, transactions=2, pq=True
- stress PQ block 3: height=16, block_hash=3dd705d9aed043d0214fc6492e2a7a5b07d20daafb345bc532c4658dd76135e6, transactions=2, pq=True
- stress PQ block 4: height=17, block_hash=43518fd9c3f8090134239b84cb1321c4af81b1a5c24c7c16bb5645038fda0913, transactions=2, pq=True
- moderate stress: status=PASS, txids=['c264b1e099efcbaf6f22815e327e40828f51b298cb0317a95fb7bd73460b10f1', '4237f78ce60aea47d0f685867a6f06cad0d167aaf44e5616d2f36ac5ef4c8df1', '6128fcb6c57af4d66f6997ac5fa4b2904de70483a31e8a1ac39a88831a59ed71', '8353cba7fe28f847c6811f0ec5ad3d0a0bf57e81d321e917ce854fa7c93279a6'], metrics={'pq_verify_count': 6, 'pq_verify_failures': 0, 'pq_verify_duration_seconds_total': 0.000735, 'pq_verify_duration_seconds_avg': 0.000122, 'pq_verify_duration_seconds_max': 0.000139, 'pq_tx_accepted': 8, 'pq_tx_rejected': 0, 'pq_malformed': 0, 'pq_relay': 8, 'pq_mined': 8, 'pq_orphan': 0}
- reorg scenarios: status=PASS, before_activation_reorg_depth=1, during_activation_reorg_depth=2, after_activation_reorg_depth=1
- restart: status=PASS, height=17, mempool_size=0
- fresh sync: status=PASS, blocks_fetched=18, headers_received=18, height=17
- negative tests: status=PASS, pre_activation=CHCQ outputs are not active on this network at this height., wrong_scheme=PQ transaction input uses a non-verification-capable signature scheme., bad_signature=Input signature is invalid., bad_public_key=Input public key does not match the CHCQ commitment., truncated_signature=PQ transaction input signature has the wrong size for ML-DSA-44., oversized=PQ transaction input signature has the wrong size for ML-DSA-44., truncated_encoding=unpack_from requires a buffer of at least 41 bytes for unpacking 4 bytes at offset 37 (actual buffer size is 5)
- API and audit metadata: status=PASS, height=17, audit_activation=20000
- browser fixture/parity/build: status=PASS, npm_test={'command': ['npm', 'test'], 'returncode': 0, 'output_tail': 'marek/Documents/CODEX/Chipcoin-v2/apps/browser-wallet\n\n ✓ tests/unit/submitted_cache.test.ts (5 tests) 7ms\n ✓ tests/unit/api_client.test.ts (2 tests) 14ms\n ✓ tests/unit/transaction_parity.test.ts (7 tests) 154ms\n ✓ tests/unit/address_scheme.test.tsx (18 tests) 63ms\n ✓ tests/unit/recovery_phrase.test.ts (3 tests) 9ms\n ✓ tests/unit/mldsa44.test.ts (12 tests) 336ms\n ✓ tests/unit/selection.test.ts (1 test) 20ms\n ✓ tests/unit/addresses.test.ts (4 tests) 75ms\n ✓ tests/unit/network_support.test.ts (5 tests) 802ms\n   ✓ browser wallet network support > accepts a node endpoint only when the selected network matches 487ms\n ✓ tests/unit/encryption.test.ts (2 tests) 629ms\n   ✓ wallet encryption > round-trips encrypted private key material 363ms\n ✓ tests/unit/session_security.test.ts (4 tests) 1266ms\n   ✓ wallet session security > requires explicit confirmation before revealing a private key from an active session 521ms\n   ✓ wallet session security > recovers the same wallet from the same recovery phrase 384ms\n\n Test Files  11 passed (11)\n      Tests  63 passed (63)\n   Start at  12:24:26\n   Duration  1.71s (transform 837ms, setup 0ms, collect 1.42s, tests 3.38s, environment 3ms, prepare 1.19s)\n\n'}, npm_build={'command': ['npm', 'run', 'build'], 'returncode': 0, 'output_tail': '.js               21.21 kB │ gzip:  6.41 kB\ndist/assets/App-BxExBiaW.js             24.07 kB │ gzip:  6.45 kB\ndist/assets/address_scheme-COckLfHy.js  46.74 kB │ gzip: 17.99 kB\n✓ built in 662ms\n\n> chipcoin-browser-wallet@0.1.1 build:firefox\n> vite build --mode firefox\n\nvite v5.4.21 building for firefox...\ntransforming...\n✓ 76 modules transformed.\nrendering chunks...\ncomputing gzip size...\ndist/onboarding.html                     0.49 kB │ gzip:  0.29 kB\ndist/settings.html                       0.65 kB │ gzip:  0.32 kB\ndist/popup.html                          0.71 kB │ gzip:  0.34 kB\ndist/assets/popup-d8wEJRZq.css           4.02 kB │ gzip:  1.46 kB\ndist/assets/popup.js                     0.25 kB │ gzip:  0.21 kB\ndist/assets/settings.js                  0.25 kB │ gzip:  0.21 kB\ndist/assets/browser-BgmI1fFX.js          2.48 kB │ gzip:  1.04 kB\ndist/assets/onboarding.js                4.70 kB │ gzip:  1.63 kB\ndist/assets/messages-CmOXBm18.js        20.11 kB │ gzip:  8.13 kB\ndist/assets/background.js               21.21 kB │ gzip:  6.41 kB\ndist/assets/App-BxExBiaW.js             24.07 kB │ gzip:  6.45 kB\ndist/assets/address_scheme-COckLfHy.js  46.74 kB │ gzip: 17.99 kB\n✓ built in 650ms\n'}, bundle={'command': ['npm', 'run', 'test:mldsa:bundle'], 'returncode': 0, 'output_tail': '\n> chipcoin-browser-wallet@0.1.1 test:mldsa:bundle\n> node scripts/inspect-mldsa44-bundle.mjs\n\n{\n  "ok": true,\n  "files": 13,\n  "wasm_assets": 0,\n  "noble_in_production_bundle": false,\n  "csp_has_unsafe_eval": false\n}\n'}
- readiness suite: status=PASS, pytest={'command': ['/home/komarek/Documents/CODEX/Chipcoin-v2/.venv/bin/python', '-m', 'pytest', 'tests/pq/test_activation_readiness.py', '-q'], 'returncode': 0, 'output_tail': '......                                                                   [100%]\n6 passed in 0.75s\n'}
- pq-smoke: status=PASS, ready=True
- pq-benchmark: status=PASS
- pq-audit-report: status=PASS

## Benchmark

- ECDSA verify 1000 median seconds: `0.000436`
- ECDSA verify 1000 throughput/s: `2232.23`
- ML-DSA-44 verify 1000 median seconds: `8.7e-05`
- ML-DSA-44 verify 1000 throughput/s: `11013.6`

## Readiness And Smoke

- Readiness: `PASS`
- Smoke ready: `True`
- Smoke final local height: `10`

## Audit

- Testnet activation height: `20000`
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
