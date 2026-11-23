# Submit block audit (development candidate)

Status: IMPLEMENTED in working tree; TESTED only in isolated tests; NOT DEPLOYED.

## Evidence and scope

Read-only inspection of the running chipcom image on 2026-11-23 found exact SHA-256 matches with the unmodified checkout for `node/service.py`, `node/runtime.py`, `interfaces/http_api.py`, `node/sync.py`, `consensus/params.py`, `consensus/validation.py`, `consensus/serialization.py`, and `miner/worker.py`. This verifies these files, not the entire release image or its configuration. MemPalace was consulted for historical context; the conclusions here are based on current source and isolated tests.

Operational incident details and private operator correspondence are kept outside the public repository. The reproducible audit below relies on source code and isolated tests.

## Verified cause and call graph

`HttpApiApp._handle_submit_block` → `NodeRuntime.submit_mined_block_from_http` → `NodeService.prepare_mined_block_submission` → `NodeRuntime.announce_block` → `NodeService.apply_block` → `consensus.validation.validate_block` → storage and P2P inventory broadcast. The non-runtime API calls `NodeService.submit_mined_block` instead. Native solo mining uses `MinerWorker._submit_block` → `MiningNodeClient.submit_block` → the same HTTP endpoint. External pools using that endpoint encounter the same administrative template constraints.

Before this candidate, the API required `template_id`; `receive_transaction` cleared *all* cached templates; `get_block_template` set a 15-second expiry; `prepare_mined_block_submission` returned `unknown_or_expired_template` when the record disappeared, before consensus validation. `announce_block` could commit and then fail during inventory relay, producing an HTTP 500. The 15-second TTL is confirmed in source. These failure paths were reproduced in isolated tests.

P2P `SyncManager.receive_block` stores side-branch payloads and uses `NodeService.activate_chain` when fork choice selects a stronger contiguous branch. A stored side block is not necessarily contextually validated until activation. The existing P2P runtime broadcasts inventory for a stored side branch after `receive_block`, except when `parent_unknown` is set; the candidate follows that policy. Full-block HTTP submission checks the ingest result and storage lookup before reporting `stored=true`. The active-tip fast path uses `NodeService.apply_block`, which invokes the same `validate_block` consensus function before storage. No consensus rules were changed.

## Candidate behavior

- Mempool additions retain existing legacy jobs. Active-chain changes still clear the job cache.
- Legacy jobs retain the 15-second TTL and existing request/response fields. The cache is bounded to 256 records; oldest jobs are evicted first. The deployed cache had no count limit. The initial candidate used 64, but was raised to 256 to reduce eviction risk for pools with multiple simultaneous jobs. A deterministic test verifies that the oldest job remains valid after 256 same-tip requests within its TTL; request 257 evicts it.
- A request without `template_id` carries a complete canonical serialized block. It can be validated after job expiry or a mempool change.
- Full-block results include `stored`, `on_active_chain`, and `consensus_validity`. A side branch can be stored with `consensus_validity=pending`; this does not claim contextual validity. A descendant may trigger validation and reorganization under existing fork choice.
- A repeated active-chain block reports `already_accepted`; a known side branch reports `known_side_branch`. A relay error after commit is logged and the committed result is returned.

## Open risks and gates

The generic P2P side-branch path can store a block before contextual validation. This is inherited from P2P and is explicitly reported as pending. Invalid side-branch payload retention, resource limits, stale header handling, and full-block rate limiting need further review before release. T1/T8/T10 and basic retry/reorg tests exist, but the full T1–T12 matrix, external pool validation of the integrated image, and real Mainnet PQ transaction vectors are NOT_RUN. The production image must remain untouched pending approval.
