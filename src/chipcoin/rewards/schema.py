"""SQLite schema for the reward observer store."""

from __future__ import annotations


SCHEMA_VERSION = 7

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    payout_address TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    payout_address TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    height INTEGER NOT NULL,
    epoch_index INTEGER NOT NULL,
    observed_at INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT,
    latency_ms INTEGER,
    handshake_ok INTEGER NOT NULL,
    network_ok INTEGER NOT NULL,
    registration_status TEXT NOT NULL,
    warmup_status INTEGER NOT NULL,
    banned INTEGER NOT NULL,
    registration_source TEXT NOT NULL,
    warmup_source TEXT NOT NULL,
    ban_source TEXT NOT NULL,
    endpoint_source TEXT NOT NULL,
    public_ip TEXT,
    fingerprint TEXT
);

CREATE INDEX IF NOT EXISTS idx_observations_epoch ON observations(epoch_index);
CREATE INDEX IF NOT EXISTS idx_observations_node_epoch ON observations(node_id, epoch_index);

CREATE TABLE IF NOT EXISTS epoch_node_summaries (
    epoch_index INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    payout_address TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    first_seen INTEGER NOT NULL,
    last_success INTEGER,
    success_count INTEGER NOT NULL,
    failure_count INTEGER NOT NULL,
    consecutive_failures INTEGER NOT NULL,
    handshake_ok INTEGER NOT NULL,
    network_ok INTEGER NOT NULL,
    registration_status TEXT NOT NULL,
    warmup_status INTEGER NOT NULL,
    concentration_status TEXT NOT NULL,
    final_eligible INTEGER NOT NULL,
    rejection_reason TEXT,
    registration_source TEXT NOT NULL,
    warmup_source TEXT NOT NULL,
    ban_source TEXT NOT NULL,
    endpoint_source TEXT NOT NULL,
    public_ip TEXT,
    subnet_key TEXT,
    fingerprint TEXT,
    checked_observation_count INTEGER NOT NULL,
    observation_count INTEGER NOT NULL,
    PRIMARY KEY (epoch_index, node_id)
);

CREATE TABLE IF NOT EXISTS payout_batches (
    batch_id TEXT PRIMARY KEY,
    epoch_index INTEGER NOT NULL,
    network TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled_node_reward_chipbits INTEGER NOT NULL,
    eligible_node_count INTEGER NOT NULL,
    rejected_node_count INTEGER NOT NULL,
    allocated_total_chipbits INTEGER NOT NULL,
    unallocated_total_chipbits INTEGER NOT NULL,
    zero_allocation_reason TEXT,
    provisional_evidence_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    approved_at INTEGER,
    reviewed_at INTEGER,
    created_by TEXT,
    reviewed_by TEXT,
    operator_note TEXT,
    review_result TEXT NOT NULL,
    review_reason TEXT,
    review_snapshot_hash TEXT,
    command_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_payout_batches_epoch ON payout_batches(epoch_index);

CREATE TABLE IF NOT EXISTS payout_batch_items (
    batch_id TEXT NOT NULL,
    allocation_rank INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    payout_address TEXT NOT NULL,
    allocated_chipbits INTEGER NOT NULL,
    remainder_assigned INTEGER NOT NULL,
    provisional_fields_json TEXT NOT NULL,
    PRIMARY KEY (batch_id, allocation_rank)
);

CREATE TABLE IF NOT EXISTS transaction_plans (
    plan_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    status TEXT NOT NULL,
    funding_assumption TEXT NOT NULL,
    input_count INTEGER NOT NULL,
    output_count INTEGER NOT NULL,
    estimated_fee_chipbits INTEGER NOT NULL,
    total_input_chipbits INTEGER NOT NULL,
    total_recipient_chipbits INTEGER NOT NULL,
    change_chipbits INTEGER NOT NULL,
    dust_dropped_chipbits INTEGER NOT NULL,
    insufficient_funds INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    created_by TEXT,
    plan_snapshot_hash TEXT,
    fee_rate_chipbits_per_weight_unit INTEGER NOT NULL,
    dust_threshold_chipbits INTEGER NOT NULL,
    min_input_confirmations INTEGER NOT NULL,
    change_address TEXT NOT NULL,
    dust_policy TEXT NOT NULL,
    provisional_warning_inherited INTEGER NOT NULL,
    invalid_reason TEXT,
    command_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_transaction_plans_batch ON transaction_plans(batch_id);

CREATE TABLE IF NOT EXISTS transaction_plan_inputs (
    plan_id TEXT NOT NULL,
    input_index INTEGER NOT NULL,
    txid TEXT NOT NULL,
    vout INTEGER NOT NULL,
    amount_chipbits INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    confirmations INTEGER NOT NULL,
    PRIMARY KEY (plan_id, input_index)
);

CREATE TABLE IF NOT EXISTS transaction_plan_outputs (
    plan_id TEXT NOT NULL,
    output_index INTEGER NOT NULL,
    output_kind TEXT NOT NULL,
    recipient TEXT NOT NULL,
    amount_chipbits INTEGER NOT NULL,
    batch_node_id TEXT,
    PRIMARY KEY (plan_id, output_index)
);

CREATE TABLE IF NOT EXISTS transaction_artifacts (
    artifact_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    status TEXT NOT NULL,
    unsigned_tx_snapshot_hash TEXT NOT NULL,
    signed_tx_snapshot_hash TEXT,
    signer_type TEXT,
    created_at INTEGER NOT NULL,
    created_by TEXT,
    validation_result TEXT NOT NULL,
    invalid_reason TEXT,
    broadcasted INTEGER NOT NULL,
    sent INTEGER NOT NULL,
    wallet_mutation INTEGER NOT NULL,
    tx_hex TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transaction_artifacts_plan ON transaction_artifacts(plan_id);

CREATE TABLE IF NOT EXISTS broadcast_preflights (
    preflight_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    txid TEXT NOT NULL,
    serialization_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    preflight_result TEXT NOT NULL,
    blocking_reason TEXT,
    warning_count INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    created_by TEXT,
    network TEXT NOT NULL,
    ready_for_manual_broadcast INTEGER NOT NULL,
    warnings_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_broadcast_preflights_artifact ON broadcast_preflights(artifact_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_preflights_plan ON broadcast_preflights(plan_id);

CREATE TABLE IF NOT EXISTS broadcast_preflight_inputs (
    preflight_id TEXT NOT NULL,
    input_index INTEGER NOT NULL,
    txid TEXT NOT NULL,
    vout INTEGER NOT NULL,
    PRIMARY KEY (preflight_id, input_index)
);

CREATE INDEX IF NOT EXISTS idx_broadcast_preflight_inputs_outpoint
ON broadcast_preflight_inputs(txid, vout);
"""
