from chipcoin.consensus.epoch_settlement import (
    REWARD_ATTESTATION_BUNDLE_KIND,
    REWARD_SETTLE_EPOCH_KIND,
    REGISTER_REWARD_NODE_KIND,
    RENEW_REWARD_NODE_KIND,
    RewardAttestation,
    RewardAttestationBundle,
    RewardSettlementEntry,
    attestation_bundle_duplicates,
    bundle_rule_violations,
    candidate_check_windows,
    concentration_tiebreak_key,
    epoch_seed,
    verifier_committee,
    verifier_emission_counts,
)
from chipcoin.consensus.params import DEVNET_PARAMS, MAINNET_PARAMS


def test_native_reward_kinds_are_locked() -> None:
    assert REGISTER_REWARD_NODE_KIND == "register_reward_node"
    assert RENEW_REWARD_NODE_KIND == "renew_reward_node"
    assert REWARD_ATTESTATION_BUNDLE_KIND == "reward_attestation_bundle"
    assert REWARD_SETTLE_EPOCH_KIND == "reward_settle_epoch"


def test_epoch_seed_is_deterministic() -> None:
    first = epoch_seed("11" * 32, 7)
    second = epoch_seed("11" * 32, 7)
    third = epoch_seed("22" * 32, 7)

    assert first == second
    assert first != third
    assert len(first) == 32


def test_candidate_check_windows_are_deterministic_and_bounded() -> None:
    windows_a = candidate_check_windows(node_id="node-a", seed=epoch_seed("33" * 32, 9), params=DEVNET_PARAMS)
    windows_b = candidate_check_windows(node_id="node-a", seed=epoch_seed("33" * 32, 9), params=DEVNET_PARAMS)

    assert windows_a == windows_b
    assert len(windows_a) == DEVNET_PARAMS.reward_target_checks_per_epoch
    assert windows_a == tuple(sorted(windows_a))
    assert all(0 <= window < DEVNET_PARAMS.reward_check_windows_per_epoch for window in windows_a)


def test_verifier_committee_is_deterministic_and_excludes_candidate() -> None:
    committee_a = verifier_committee(
        candidate_node_id="node-b",
        active_verifier_node_ids=["node-a", "node-b", "node-c", "node-d"],
        check_window_index=2,
        seed=epoch_seed("44" * 32, 1),
        params=DEVNET_PARAMS,
    )
    committee_b = verifier_committee(
        candidate_node_id="node-b",
        active_verifier_node_ids=["node-a", "node-b", "node-c", "node-d"],
        check_window_index=2,
        seed=epoch_seed("44" * 32, 1),
        params=DEVNET_PARAMS,
    )

    assert committee_a == committee_b
    assert "node-b" not in committee_a
    assert len(committee_a) == DEVNET_PARAMS.reward_verifier_committee_size


def test_bundle_duplicate_detection_is_explicit() -> None:
    attestation = RewardAttestation(
        epoch_index=1,
        check_window_index=2,
        candidate_node_id="node-a",
        verifier_node_id="node-v",
        result_code="pass",
        observed_sync_gap=1,
        endpoint_commitment="endpoint",
        concentration_key="key",
        signature_hex="aa",
    )
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=2,
        bundle_submitter_node_id="node-v",
        attestations=(attestation, attestation),
    )

    assert attestation_bundle_duplicates(bundle) == {(1, 2, "node-a", "node-v")}
    assert bundle_rule_violations(bundle, DEVNET_PARAMS) == ["duplicate_attestation", "verifier_over_emission"]


def test_bundle_respects_attestation_count_limit() -> None:
    attestations = tuple(
        RewardAttestation(
            epoch_index=1,
            check_window_index=index,
            candidate_node_id=f"node-{index}",
            verifier_node_id=f"verifier-{index}",
            result_code="pass",
            observed_sync_gap=0,
            endpoint_commitment=f"endpoint-{index}",
            concentration_key=f"key-{index}",
            signature_hex=f"{index:02x}",
        )
        for index in range(DEVNET_PARAMS.max_attestations_per_bundle + 1)
    )
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=0,
        bundle_submitter_node_id="node-v",
        attestations=attestations,
    )

    assert bundle_rule_violations(bundle, DEVNET_PARAMS) == ["too_many_attestations"]


def test_verifier_emission_counts_are_per_window() -> None:
    bundle = RewardAttestationBundle(
        epoch_index=1,
        bundle_window_index=3,
        bundle_submitter_node_id="node-v",
        attestations=(
            RewardAttestation(1, 3, "node-a", "verifier-1", "pass", 1, "e1", "k1", "aa"),
            RewardAttestation(1, 3, "node-b", "verifier-1", "pass", 2, "e2", "k2", "bb"),
            RewardAttestation(1, 4, "node-c", "verifier-1", "pass", 3, "e3", "k3", "cc"),
        ),
    )

    assert verifier_emission_counts(bundle) == {(3, "verifier-1"): 2, (4, "verifier-1"): 1}


def test_concentration_tiebreak_prefers_more_passes_then_lower_gap_then_hash() -> None:
    seed = epoch_seed("55" * 32, 4)
    strongest = concentration_tiebreak_key(
        node_id="node-a",
        payout_address="CHCa",
        passed_check_count=3,
        observed_sync_gaps=[1, 2, 2],
        seed=seed,
    )
    weaker_pass_count = concentration_tiebreak_key(
        node_id="node-b",
        payout_address="CHCb",
        passed_check_count=2,
        observed_sync_gaps=[0, 0],
        seed=seed,
    )
    worse_gap = concentration_tiebreak_key(
        node_id="node-c",
        payout_address="CHCc",
        passed_check_count=3,
        observed_sync_gaps=[4, 5, 5],
        seed=seed,
    )

    assert strongest < weaker_pass_count
    assert strongest < worse_gap


def test_settlement_entry_payload_is_typed_and_stable() -> None:
    entry = RewardSettlementEntry(
        node_id="node-a",
        payout_address="CHCa",
        reward_chipbits=1_250_000_000,
        selection_rank=0,
        concentration_key="key-a",
        final_confirmation_passed=True,
    )

    assert entry.node_id == "node-a"
    assert entry.reward_chipbits == 1_250_000_000
    assert entry.final_confirmation_passed is True


def test_consensus_params_expose_native_reward_defaults() -> None:
    assert MAINNET_PARAMS.reward_target_checks_per_epoch == 3
    assert MAINNET_PARAMS.reward_min_passed_checks_per_epoch == 2
    assert MAINNET_PARAMS.reward_verifier_committee_size == 3
    assert MAINNET_PARAMS.reward_verifier_quorum == 2
    assert MAINNET_PARAMS.reward_final_confirmation_window_blocks == 10
    assert MAINNET_PARAMS.reward_sync_lag_tolerance_blocks == 5
    assert MAINNET_PARAMS.register_node_fee_chipbits == 100_000_000
    assert MAINNET_PARAMS.renew_node_fee_chipbits == 10_000_000
    assert DEVNET_PARAMS.max_attestation_bundles_per_block == 4
    assert DEVNET_PARAMS.max_attestations_per_bundle == 24
    assert DEVNET_PARAMS.max_attestations_per_verifier_per_window == 1
