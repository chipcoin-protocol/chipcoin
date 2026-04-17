"""Typed models for observer-only reward tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ObservationOutcome = Literal["success", "failure", "unchecked"]
RegistrationStatus = Literal["registered", "expired", "unregistered"]
ConcentrationStatus = Literal["ok", "ip_concentration_cap", "subnet_concentration_cap", "fingerprint_concentration_cap"]
SourceKind = Literal["manual", "node_registry", "derived", "peer_state", "provisional"]
BatchStatus = Literal["proposed", "approved", "rejected", "simulated"]
ReviewResult = Literal["pending", "pass", "warn", "fail"]
TransactionPlanStatus = Literal["planned", "invalid"]
TransactionArtifactStatus = Literal["unsigned", "signed", "invalid"]
BroadcastPreflightStatus = Literal["prepared", "blocked"]

REJECTION_CODES = frozenset(
    {
        "unreachable",
        "protocol_handshake_failed",
        "wrong_network",
        "expired_registration",
        "insufficient_observation",
        "warmup_not_satisfied",
        "banned",
        "ip_concentration_cap",
        "subnet_concentration_cap",
        "fingerprint_concentration_cap",
        "observer_error",
        "no_eligible_nodes",
    }
)


@dataclass(frozen=True)
class NodeIdentity:
    """Stable node identity and endpoint metadata."""

    node_id: str
    payout_address: str
    host: str
    port: int
    first_seen: int


@dataclass(frozen=True)
class NodeObservation:
    """One observer sample for one node at one chain height."""

    node_id: str
    payout_address: str
    host: str
    port: int
    height: int
    epoch_index: int
    timestamp: int
    outcome: ObservationOutcome
    reason_code: str | None
    latency_ms: int | None
    handshake_ok: bool
    network_ok: bool
    registration_status: RegistrationStatus
    warmup_status: bool
    banned: bool
    registration_source: SourceKind = "manual"
    warmup_source: SourceKind = "manual"
    ban_source: SourceKind = "manual"
    endpoint_source: SourceKind = "manual"
    public_ip: str | None = None
    fingerprint: str | None = None


@dataclass(frozen=True)
class NodeEpochSummary:
    """Per-node summary for one observed epoch."""

    epoch_index: int
    node_id: str
    payout_address: str
    host: str
    port: int
    first_seen: int
    last_success: int | None
    success_count: int
    failure_count: int
    consecutive_failures: int
    handshake_ok: bool
    network_ok: bool
    registration_status: str
    warmup_status: bool
    concentration_status: str
    final_eligible: bool
    rejection_reason: str | None
    registration_source: SourceKind
    warmup_source: SourceKind
    ban_source: SourceKind
    endpoint_source: SourceKind
    public_ip: str | None
    subnet_key: str | None
    fingerprint: str | None
    checked_observation_count: int
    observation_count: int


@dataclass(frozen=True)
class PayoutBatch:
    """Dry-run payout batch header persisted outside consensus state."""

    batch_id: str
    epoch_index: int
    network: str
    status: BatchStatus
    scheduled_node_reward_chipbits: int
    eligible_node_count: int
    rejected_node_count: int
    allocated_total_chipbits: int
    unallocated_total_chipbits: int
    zero_allocation_reason: str | None
    provisional_evidence_count: int
    created_at: int
    approved_at: int | None
    reviewed_at: int | None
    created_by: str | None
    reviewed_by: str | None
    operator_note: str | None
    review_result: ReviewResult
    review_reason: str | None
    review_snapshot_hash: str | None
    command_version: str | None


@dataclass(frozen=True)
class PayoutBatchItem:
    """One deterministic dry-run allocation line for an eligible node."""

    batch_id: str
    allocation_rank: int
    node_id: str
    payout_address: str
    allocated_chipbits: int
    remainder_assigned: bool
    provisional_fields: tuple[str, ...]


@dataclass(frozen=True)
class PlanningUtxo:
    """Manual or hypothetical funding input for dry transaction planning."""

    txid: str
    index: int
    amount_chipbits: int
    recipient: str
    confirmations: int
    coinbase: bool = False


@dataclass(frozen=True)
class TransactionPlan:
    """Dry-run transaction construction plan derived from one approved batch."""

    plan_id: str
    batch_id: str
    status: TransactionPlanStatus
    funding_assumption: str
    input_count: int
    output_count: int
    estimated_fee_chipbits: int
    total_input_chipbits: int
    total_recipient_chipbits: int
    change_chipbits: int
    dust_dropped_chipbits: int
    insufficient_funds: bool
    created_at: int
    created_by: str | None
    plan_snapshot_hash: str | None
    fee_rate_chipbits_per_weight_unit: int
    dust_threshold_chipbits: int
    min_input_confirmations: int
    change_address: str
    dust_policy: str
    provisional_warning_inherited: bool
    invalid_reason: str | None
    command_version: str | None


@dataclass(frozen=True)
class TransactionPlanInput:
    """One selected funding input in a dry transaction plan."""

    plan_id: str
    input_index: int
    txid: str
    vout: int
    amount_chipbits: int
    recipient: str
    confirmations: int


@dataclass(frozen=True)
class TransactionPlanOutput:
    """One planned transaction output in deterministic order."""

    plan_id: str
    output_index: int
    output_kind: str
    recipient: str
    amount_chipbits: int
    batch_node_id: str | None = None


@dataclass(frozen=True)
class TransactionArtifact:
    """Locally stored unsigned or signed transaction artifact."""

    artifact_id: str
    plan_id: str
    batch_id: str
    status: TransactionArtifactStatus
    unsigned_tx_snapshot_hash: str
    signed_tx_snapshot_hash: str | None
    signer_type: str | None
    created_at: int
    created_by: str | None
    validation_result: str
    invalid_reason: str | None
    broadcasted: bool
    sent: bool
    wallet_mutation: bool
    tx_hex: str


@dataclass(frozen=True)
class BroadcastPreflight:
    """Local-only preflight record for manual broadcast preparation."""

    preflight_id: str
    artifact_id: str
    batch_id: str
    plan_id: str
    txid: str
    serialization_hash: str
    status: BroadcastPreflightStatus
    preflight_result: str
    blocking_reason: str | None
    warning_count: int
    created_at: int
    created_by: str | None
    network: str
    ready_for_manual_broadcast: bool
    warnings_json: str
