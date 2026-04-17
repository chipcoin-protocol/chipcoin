"""Payload models and deterministic helpers for native epoch node rewards."""

from __future__ import annotations

from dataclasses import dataclass
import json
from statistics import median
from typing import Mapping

from .hashes import double_sha256
from .models import Transaction
from .params import ConsensusParams


REGISTER_REWARD_NODE_KIND = "register_reward_node"
RENEW_REWARD_NODE_KIND = "renew_reward_node"
REWARD_ATTESTATION_BUNDLE_KIND = "reward_attestation_bundle"
REWARD_SETTLE_EPOCH_KIND = "reward_settle_epoch"


@dataclass(frozen=True)
class RewardNodeEndpoint:
    """Consensus-visible endpoint declaration for one reward node."""

    host: str
    port: int


@dataclass(frozen=True)
class RewardAttestation:
    """One verifier attestation for one candidate check."""

    epoch_index: int
    check_window_index: int
    candidate_node_id: str
    verifier_node_id: str
    result_code: str
    observed_sync_gap: int
    endpoint_commitment: str
    concentration_key: str
    signature_hex: str


@dataclass(frozen=True)
class RewardAttestationBundle:
    """Compact carriage for multiple verifier attestations."""

    epoch_index: int
    bundle_window_index: int
    bundle_submitter_node_id: str
    attestations: tuple[RewardAttestation, ...]


@dataclass(frozen=True)
class RewardSettlementEntry:
    """One final reward recipient entry in epoch settlement."""

    node_id: str
    payout_address: str
    reward_chipbits: int
    selection_rank: int
    concentration_key: str
    final_confirmation_passed: bool


@dataclass(frozen=True)
class RewardSettlement:
    """One parsed native epoch settlement payload."""

    epoch_index: int
    epoch_start_height: int
    epoch_end_height: int
    epoch_seed_hex: str
    policy_version: str
    submission_mode: str
    candidate_summary_root: str
    verified_nodes_root: str
    rewarded_nodes_root: str
    rewarded_node_count: int
    distributed_node_reward_chipbits: int
    undistributed_node_reward_chipbits: int
    reward_entries: tuple[RewardSettlementEntry, ...]


def epoch_seed(previous_epoch_closing_block_hash: str, epoch_index: int) -> bytes:
    """Return the deterministic epoch seed used by assignment helpers."""

    if len(previous_epoch_closing_block_hash) != 64:
        raise ValueError("previous_epoch_closing_block_hash must be 32 bytes hex")
    if epoch_index < 0:
        raise ValueError("epoch_index cannot be negative")
    payload = bytes.fromhex(previous_epoch_closing_block_hash) + epoch_index.to_bytes(8, "big") + b"reward-epoch-v1"
    return double_sha256(payload)


def epoch_close_height(epoch_index: int, params: ConsensusParams) -> int:
    """Return the closing block height for one epoch index."""

    if epoch_index < 0:
        raise ValueError("epoch_index cannot be negative")
    return ((epoch_index + 1) * params.epoch_length_blocks) - 1


def candidate_check_windows(
    *,
    node_id: str,
    seed: bytes,
    params: ConsensusParams,
) -> tuple[int, ...]:
    """Return deterministic check-window assignments for one candidate."""

    if params.reward_target_checks_per_epoch > params.reward_check_windows_per_epoch:
        raise ValueError("reward_target_checks_per_epoch cannot exceed reward_check_windows_per_epoch")
    scored_windows = sorted(
        (
            (
                _score_bytes(seed, f"candidate-window|{window_index}|{node_id}"),
                window_index,
            )
            for window_index in range(params.reward_check_windows_per_epoch)
        ),
        key=lambda item: (item[0], item[1]),
    )
    selected = sorted(window_index for _score, window_index in scored_windows[: params.reward_target_checks_per_epoch])
    return tuple(selected)


def verifier_committee(
    *,
    candidate_node_id: str,
    active_verifier_node_ids: list[str],
    check_window_index: int,
    seed: bytes,
    params: ConsensusParams,
) -> tuple[str, ...]:
    """Return the deterministic verifier committee for one candidate and window."""

    if check_window_index < 0 or check_window_index >= params.reward_check_windows_per_epoch:
        raise ValueError("check_window_index out of range")
    scored = sorted(
        (
            (
                _score_bytes(seed, f"verifier|{check_window_index}|{candidate_node_id}|{verifier_node_id}"),
                verifier_node_id,
            )
            for verifier_node_id in active_verifier_node_ids
            if verifier_node_id != candidate_node_id
        ),
        key=lambda item: (item[0], item[1]),
    )
    return tuple(verifier_node_id for _score, verifier_node_id in scored[: params.reward_verifier_committee_size])


def attestation_bundle_duplicates(bundle: RewardAttestationBundle) -> set[tuple[int, int, str, str]]:
    """Return duplicate attestation identity tuples found inside one bundle."""

    seen: set[tuple[int, int, str, str]] = set()
    duplicates: set[tuple[int, int, str, str]] = set()
    for attestation in bundle.attestations:
        key = (
            attestation.epoch_index,
            attestation.check_window_index,
            attestation.candidate_node_id,
            attestation.verifier_node_id,
        )
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return duplicates


def verifier_emission_counts(bundle: RewardAttestationBundle) -> dict[tuple[int, str], int]:
    """Return per-window verifier emission counts inside one bundle."""

    counts: dict[tuple[int, str], int] = {}
    for attestation in bundle.attestations:
        key = (attestation.check_window_index, attestation.verifier_node_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def bundle_rule_violations(bundle: RewardAttestationBundle, params: ConsensusParams) -> list[str]:
    """Return deterministic bundle-rule violations for a single bundle."""

    violations: list[str] = []
    if len(bundle.attestations) > params.max_attestations_per_bundle:
        violations.append("too_many_attestations")
    if attestation_bundle_duplicates(bundle):
        violations.append("duplicate_attestation")
    if any(
        count > params.max_attestations_per_verifier_per_window
        for count in verifier_emission_counts(bundle).values()
    ):
        violations.append("verifier_over_emission")
    return violations


def attestation_identity(attestation: RewardAttestation) -> tuple[int, int, str, str]:
    """Return the unique identity tuple for one attestation."""

    return (
        attestation.epoch_index,
        attestation.check_window_index,
        attestation.candidate_node_id,
        attestation.verifier_node_id,
    )


def reward_attestation_signature_digest(attestation: RewardAttestation) -> bytes:
    """Return the signing digest for one attestation."""

    payload = json.dumps(
        {
            "candidate_node_id": attestation.candidate_node_id,
            "check_window_index": attestation.check_window_index,
            "concentration_key": attestation.concentration_key,
            "endpoint_commitment": attestation.endpoint_commitment,
            "epoch_index": attestation.epoch_index,
            "observed_sync_gap": attestation.observed_sync_gap,
            "result_code": attestation.result_code,
            "verifier_node_id": attestation.verifier_node_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return double_sha256(payload)


def parse_reward_attestation_bundle_metadata(metadata: Mapping[str, str]) -> RewardAttestationBundle:
    """Parse bundle metadata into a typed attestation bundle."""

    for key in ("epoch_index", "bundle_window_index", "bundle_submitter_node_id", "attestation_count", "attestations_json"):
        if key not in metadata or metadata[key] == "":
            raise ValueError(f"reward_attestation_bundle transactions must declare {key}.")
    raw = json.loads(metadata["attestations_json"])
    if not isinstance(raw, list):
        raise ValueError("reward_attestation_bundle attestations_json must be a JSON array.")
    attestations = tuple(
        RewardAttestation(
            epoch_index=int(item["epoch_index"]),
            check_window_index=int(item["check_window_index"]),
            candidate_node_id=str(item["candidate_node_id"]),
            verifier_node_id=str(item["verifier_node_id"]),
            result_code=str(item["result_code"]),
            observed_sync_gap=int(item["observed_sync_gap"]),
            endpoint_commitment=str(item["endpoint_commitment"]),
            concentration_key=str(item["concentration_key"]),
            signature_hex=str(item["signature_hex"]),
        )
        for item in raw
    )
    if int(metadata["attestation_count"]) != len(attestations):
        raise ValueError("reward_attestation_bundle attestation_count does not match attestations_json length.")
    return RewardAttestationBundle(
        epoch_index=int(metadata["epoch_index"]),
        bundle_window_index=int(metadata["bundle_window_index"]),
        bundle_submitter_node_id=str(metadata["bundle_submitter_node_id"]),
        attestations=attestations,
    )


def parse_reward_settlement_metadata(metadata: Mapping[str, str]) -> RewardSettlement:
    """Parse settlement metadata into a typed reward settlement."""

    for key in (
        "epoch_index",
        "epoch_start_height",
        "epoch_end_height",
        "epoch_seed",
        "policy_version",
        "candidate_summary_root",
        "verified_nodes_root",
        "rewarded_nodes_root",
        "rewarded_node_count",
        "distributed_node_reward_chipbits",
        "undistributed_node_reward_chipbits",
        "reward_entries_json",
    ):
        if key not in metadata or metadata[key] == "":
            raise ValueError(f"reward_settle_epoch transactions must declare {key}.")
    raw = json.loads(metadata["reward_entries_json"])
    if not isinstance(raw, list):
        raise ValueError("reward_settle_epoch reward_entries_json must be a JSON array.")
    reward_entries = tuple(
        RewardSettlementEntry(
            node_id=str(item["node_id"]),
            payout_address=str(item["payout_address"]),
            reward_chipbits=int(item["reward_chipbits"]),
            selection_rank=int(item["selection_rank"]),
            concentration_key=str(item["concentration_key"]),
            final_confirmation_passed=bool(item["final_confirmation_passed"]),
        )
        for item in raw
    )
    return RewardSettlement(
        epoch_index=int(metadata["epoch_index"]),
        epoch_start_height=int(metadata["epoch_start_height"]),
        epoch_end_height=int(metadata["epoch_end_height"]),
        epoch_seed_hex=str(metadata["epoch_seed"]),
        policy_version=str(metadata["policy_version"]),
        submission_mode=str(metadata.get("submission_mode", "manual")),
        candidate_summary_root=str(metadata["candidate_summary_root"]),
        verified_nodes_root=str(metadata["verified_nodes_root"]),
        rewarded_nodes_root=str(metadata["rewarded_nodes_root"]),
        rewarded_node_count=int(metadata["rewarded_node_count"]),
        distributed_node_reward_chipbits=int(metadata["distributed_node_reward_chipbits"]),
        undistributed_node_reward_chipbits=int(metadata["undistributed_node_reward_chipbits"]),
        reward_entries=reward_entries,
    )


def build_reward_settlement(
    *,
    epoch_index: int,
    epoch_seed_hex: str,
    epoch_start_height: int,
    epoch_end_height: int,
    policy_version: str,
    submission_mode: str,
    active_records_by_id: Mapping[str, object],
    attestations: list[RewardAttestation],
    distributed_reward_chipbits: int,
    params: ConsensusParams,
) -> RewardSettlement:
    """Build one deterministic settlement payload from persisted epoch state."""

    seed = bytes.fromhex(epoch_seed_hex)
    reward_entries = derive_reward_settlement_entries(
        active_records_by_id=active_records_by_id,
        seed=seed,
        attestations=attestations,
        distributed_reward_chipbits=distributed_reward_chipbits,
        params=params,
    )
    distributed_chipbits = sum(entry.reward_chipbits for entry in reward_entries)
    undistributed_chipbits = distributed_reward_chipbits - distributed_chipbits
    candidate_summary_root, verified_nodes_root, rewarded_nodes_root = reward_entries_roots(
        epoch_index=epoch_index,
        seed=seed,
        attestations=attestations,
        reward_entries=reward_entries,
    )
    return RewardSettlement(
        epoch_index=epoch_index,
        epoch_start_height=epoch_start_height,
        epoch_end_height=epoch_end_height,
        epoch_seed_hex=epoch_seed_hex,
        policy_version=policy_version,
        submission_mode=submission_mode,
        candidate_summary_root=candidate_summary_root,
        verified_nodes_root=verified_nodes_root,
        rewarded_nodes_root=rewarded_nodes_root,
        rewarded_node_count=len(reward_entries),
        distributed_node_reward_chipbits=distributed_chipbits,
        undistributed_node_reward_chipbits=undistributed_chipbits,
        reward_entries=reward_entries,
    )


def reward_settlement_metadata(settlement: RewardSettlement) -> dict[str, str]:
    """Serialize one typed settlement to transaction metadata."""

    return {
        "kind": REWARD_SETTLE_EPOCH_KIND,
        "epoch_index": str(settlement.epoch_index),
        "epoch_start_height": str(settlement.epoch_start_height),
        "epoch_end_height": str(settlement.epoch_end_height),
        "epoch_seed": settlement.epoch_seed_hex,
        "policy_version": settlement.policy_version,
        "submission_mode": settlement.submission_mode,
        "candidate_summary_root": settlement.candidate_summary_root,
        "verified_nodes_root": settlement.verified_nodes_root,
        "rewarded_nodes_root": settlement.rewarded_nodes_root,
        "rewarded_node_count": str(settlement.rewarded_node_count),
        "distributed_node_reward_chipbits": str(settlement.distributed_node_reward_chipbits),
        "undistributed_node_reward_chipbits": str(settlement.undistributed_node_reward_chipbits),
        "reward_entries_json": json.dumps(
            [
                {
                    "node_id": entry.node_id,
                    "payout_address": entry.payout_address,
                    "reward_chipbits": entry.reward_chipbits,
                    "selection_rank": entry.selection_rank,
                    "concentration_key": entry.concentration_key,
                    "final_confirmation_passed": entry.final_confirmation_passed,
                }
                for entry in settlement.reward_entries
            ],
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def build_reward_settlement_transaction(settlement: RewardSettlement) -> Transaction:
    """Build one `reward_settle_epoch` transaction from a typed settlement."""

    return Transaction(version=1, inputs=(), outputs=(), metadata=reward_settlement_metadata(settlement))


def concentration_tiebreak_key(
    *,
    node_id: str,
    payout_address: str,
    passed_check_count: int,
    observed_sync_gaps: list[int],
    seed: bytes,
) -> tuple[int, float, bytes]:
    """Return the deterministic tie-break key for one concentration group."""

    if passed_check_count < 0:
        raise ValueError("passed_check_count cannot be negative")
    if observed_sync_gaps:
        median_gap = float(median(observed_sync_gaps))
    else:
        median_gap = float("inf")
    hash_rank = _score_bytes(seed, f"concentration-rank|{node_id}|{payout_address}")
    return (-passed_check_count, median_gap, hash_rank)


def derive_reward_settlement_entries(
    *,
    active_records_by_id: Mapping[str, object],
    seed: bytes,
    attestations: list[RewardAttestation],
    distributed_reward_chipbits: int,
    params: ConsensusParams,
) -> tuple[RewardSettlementEntry, ...]:
    """Derive deterministic reward recipients from one epoch attestation set."""

    return tuple(
        analyze_reward_settlement(
            active_records_by_id=active_records_by_id,
            seed=seed,
            attestations=attestations,
            distributed_reward_chipbits=distributed_reward_chipbits,
            params=params,
        )["reward_entries"]
    )


def analyze_reward_settlement(
    *,
    active_records_by_id: Mapping[str, object],
    seed: bytes,
    attestations: list[RewardAttestation],
    distributed_reward_chipbits: int,
    params: ConsensusParams,
) -> dict[str, object]:
    """Derive deterministic reward recipients from one epoch attestation set.

    Prototype eligibility rule:
    - candidate must be an active registered reward node
    - candidate must pass at least `reward_min_passed_checks_per_epoch` assigned windows
    - one passed window must be the candidate's final assigned window
    - one window passes when at least `reward_verifier_quorum` assigned verifiers submit
      valid `pass` attestations with sync gap within tolerance
    - one rewarded node survives per concentration key via deterministic tie-break
    - the surviving set is capped by `max_rewarded_nodes_per_epoch`
    - distributed reward is split equally with deterministic remainder to earlier ranks
    """

    grouped: dict[tuple[str, int], list[RewardAttestation]] = {}
    for attestation in attestations:
        key = (attestation.candidate_node_id, attestation.check_window_index)
        grouped.setdefault(key, []).append(attestation)

    qualified: list[tuple[object, int, list[int], str]] = []
    node_evaluations: list[dict[str, object]] = []
    active_ids = sorted(active_records_by_id)
    for node_id, record in sorted(active_records_by_id.items()):
        assigned_windows = candidate_check_windows(node_id=node_id, seed=seed, params=params)
        passed_windows = 0
        observed_sync_gaps: list[int] = []
        final_confirmation_passed = False
        final_window = assigned_windows[-1] if assigned_windows else None
        passed_window_indexes: list[int] = []
        failed_windows: list[dict[str, object]] = []
        for window_index in assigned_windows:
            ordered_committee = verifier_committee(
                candidate_node_id=node_id,
                active_verifier_node_ids=active_ids,
                check_window_index=window_index,
                seed=seed,
                params=params,
            )
            committee = set(ordered_committee)
            window_attestations = [
                attestation
                for attestation in grouped.get((node_id, window_index), [])
                if attestation.verifier_node_id in committee
            ]
            passed_by_verifier: dict[str, RewardAttestation] = {}
            failing_attestations = 0
            for attestation in window_attestations:
                if attestation.result_code != "pass":
                    failing_attestations += 1
                    continue
                if attestation.observed_sync_gap > params.reward_sync_lag_tolerance_blocks:
                    failing_attestations += 1
                    continue
                passed_by_verifier.setdefault(attestation.verifier_node_id, attestation)
            if len(passed_by_verifier) >= params.reward_verifier_quorum:
                passed_windows += 1
                passed_window_indexes.append(window_index)
                observed_sync_gaps.extend(
                    attestation.observed_sync_gap for attestation in passed_by_verifier.values()
                )
                if final_window is not None and window_index == final_window:
                    final_confirmation_passed = True
            else:
                failure_reason = "missing_attestations"
                if failing_attestations > 0 and len(passed_by_verifier) == 0:
                    failure_reason = "no_valid_pass_quorum"
                elif 0 < len(passed_by_verifier) < params.reward_verifier_quorum:
                    failure_reason = "insufficient_quorum"
                failed_windows.append(
                    {
                        "window_index": window_index,
                        "committee": list(ordered_committee),
                        "valid_pass_count": len(passed_by_verifier),
                        "attestation_count": len(window_attestations),
                        "failure_reason": failure_reason,
                    }
                )
        concentration_key = next(
            (
                attestation.concentration_key
                for attestation in attestations
                if attestation.candidate_node_id == node_id and attestation.concentration_key
            ),
            f"unscoped:{node_id}",
        )
        node_evaluations.append(
            {
                "node_id": record.node_id,
                "payout_address": record.payout_address,
                "assigned_windows": list(assigned_windows),
                "passed_window_indexes": passed_window_indexes,
                "passed_window_count": passed_windows,
                "final_window_index": final_window,
                "final_confirmation_passed": final_confirmation_passed,
                "concentration_key": concentration_key,
                "failed_windows": failed_windows,
                "status": "qualified"
                if passed_windows >= params.reward_min_passed_checks_per_epoch and final_confirmation_passed
                else "not_rewarded",
                "not_rewarded_reason": None
                if passed_windows >= params.reward_min_passed_checks_per_epoch and final_confirmation_passed
                else (
                    "final_confirmation_missing"
                    if passed_windows >= params.reward_min_passed_checks_per_epoch
                    else "insufficient_passed_windows"
                ),
            }
        )
        if passed_windows >= params.reward_min_passed_checks_per_epoch and final_confirmation_passed:
            qualified.append((record, passed_windows, observed_sync_gaps, concentration_key))

    by_concentration: dict[str, list[tuple[object, int, list[int], str]]] = {}
    for item in qualified:
        by_concentration.setdefault(item[3], []).append(item)

    resolved: list[tuple[object, int, list[int], str]] = []
    concentration_exclusions: list[dict[str, object]] = []
    for concentration_key, entries in sorted(by_concentration.items()):
        ranked_entries = sorted(
            entries,
            key=lambda item: (
                concentration_tiebreak_key(
                    node_id=item[0].node_id,
                    payout_address=item[0].payout_address,
                    passed_check_count=item[1],
                    observed_sync_gaps=item[2],
                    seed=seed,
                ),
                item[0].node_id,
                item[0].payout_address,
            ),
        )
        winner = ranked_entries[0]
        resolved.append((winner[0], winner[1], winner[2], concentration_key))
        for excluded in ranked_entries[1:]:
            concentration_exclusions.append(
                {
                    "concentration_key": concentration_key,
                    "winner_node_id": winner[0].node_id,
                    "excluded_node_id": excluded[0].node_id,
                    "reason": "anti_concentration",
                }
            )
            for node_report in node_evaluations:
                if node_report["node_id"] == excluded[0].node_id:
                    node_report["status"] = "excluded"
                    node_report["not_rewarded_reason"] = "anti_concentration"

    ordered = sorted(
        resolved,
        key=lambda item: (
            concentration_tiebreak_key(
                node_id=item[0].node_id,
                payout_address=item[0].payout_address,
                passed_check_count=item[1],
                observed_sync_gaps=item[2],
                seed=seed,
            ),
            item[0].node_id,
            item[0].payout_address,
        ),
    )
    if len(ordered) > params.max_rewarded_nodes_per_epoch:
        for excluded in ordered[params.max_rewarded_nodes_per_epoch :]:
            for node_report in node_evaluations:
                if node_report["node_id"] == excluded[0].node_id:
                    node_report["status"] = "excluded"
                    node_report["not_rewarded_reason"] = "reward_cap"
        ordered = ordered[: params.max_rewarded_nodes_per_epoch]
    reward_count = len(ordered)
    if reward_count == 0 or distributed_reward_chipbits <= 0:
        return {
            "reward_entries": (),
            "node_evaluations": node_evaluations,
            "concentration_exclusions": concentration_exclusions,
            "eligible_ranking": [],
        }

    base_reward = distributed_reward_chipbits // reward_count
    remainder = distributed_reward_chipbits % reward_count
    reward_entries = tuple(
        RewardSettlementEntry(
            node_id=item[0].node_id,
            payout_address=item[0].payout_address,
            reward_chipbits=base_reward + (1 if index < remainder else 0),
            selection_rank=index,
            concentration_key=item[3],
            final_confirmation_passed=True,
        )
        for index, item in enumerate(ordered)
    )
    for entry in reward_entries:
        for node_report in node_evaluations:
            if node_report["node_id"] == entry.node_id:
                node_report["status"] = "rewarded"
                node_report["selection_rank"] = entry.selection_rank
                node_report["reward_chipbits"] = entry.reward_chipbits
    return {
        "reward_entries": reward_entries,
        "node_evaluations": node_evaluations,
        "concentration_exclusions": concentration_exclusions,
        "eligible_ranking": [
            {
                "selection_rank": index,
                "node_id": item[0].node_id,
                "payout_address": item[0].payout_address,
                "passed_window_count": item[1],
                "concentration_key": item[3],
            }
            for index, item in enumerate(ordered)
        ],
    }


def reward_entries_roots(
    *,
    epoch_index: int,
    seed: bytes,
    attestations: list[RewardAttestation],
    reward_entries: tuple[RewardSettlementEntry, ...],
) -> tuple[str, str, str]:
    """Return deterministic summary roots for prototype settlement payloads."""

    candidate_summary_root = double_sha256(
        json.dumps(
            [
                (
                    attestation.candidate_node_id,
                    attestation.check_window_index,
                    attestation.verifier_node_id,
                    attestation.result_code,
                )
                for attestation in sorted(
                    attestations,
                    key=lambda item: (
                        item.candidate_node_id,
                        item.check_window_index,
                        item.verifier_node_id,
                        item.result_code,
                    ),
                )
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + seed
        + epoch_index.to_bytes(8, "big")
    ).hex()
    verified_nodes_root = double_sha256(
        json.dumps(
            [entry.node_id for entry in reward_entries],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + seed
        + b"verified"
    ).hex()
    rewarded_nodes_root = double_sha256(
        json.dumps(
            [
                (entry.node_id, entry.payout_address, entry.reward_chipbits, entry.selection_rank)
                for entry in reward_entries
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + seed
        + b"rewarded"
    ).hex()
    return candidate_summary_root, verified_nodes_root, rewarded_nodes_root


def _score_bytes(seed: bytes, payload: str) -> bytes:
    return double_sha256(seed + payload.encode("utf-8"))
