"""Baseline Phase 1 eligibility checks for observer-only rewards."""

from __future__ import annotations

from .config import RewardObserverConfig
from .models import NodeEpochSummary


def apply_baseline_eligibility(summary: NodeEpochSummary, config: RewardObserverConfig) -> NodeEpochSummary:
    """Apply non-concentration eligibility rules to one epoch summary."""

    rejection_reason: str | None = None
    if summary.registration_status != "registered":
        rejection_reason = "expired_registration"
    elif summary.checked_observation_count < config.required_observations_per_epoch:
        rejection_reason = "insufficient_observation"
    elif not summary.network_ok:
        rejection_reason = "wrong_network"
    elif not summary.handshake_ok:
        rejection_reason = "protocol_handshake_failed"
    elif not summary.warmup_status:
        rejection_reason = "warmup_not_satisfied"
    elif summary.rejection_reason == "banned":
        rejection_reason = "banned"
    elif summary.success_count < config.min_successful_observations:
        rejection_reason = "unreachable"

    return NodeEpochSummary(
        **{
            **summary.__dict__,
            "concentration_status": "ok",
            "final_eligible": rejection_reason is None,
            "rejection_reason": rejection_reason,
        }
    )
