"""Standalone CLI for Phase 1 reward observer operations."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ..node.service import NodeService
from ..rewards.batches import (
    batch_snapshot_hash,
    build_dry_run_batch,
    compare_epoch_to_batch,
    finalize_batch_review_snapshot,
    transition_batch,
    validate_batch,
)
from ..rewards.config import RewardObserverConfig
from ..rewards.models import PlanningUtxo, REJECTION_CODES, NodeObservation
from ..rewards.observer import RewardObserver
from ..rewards.reporting import (
    batch_audit_report,
    batch_items_report,
    batch_review_report,
    build_epoch_summary,
    concentration_report,
    eligible_nodes_report,
    observation_stats_report,
    payout_batch_list_report,
    payout_batch_report,
    broadcast_preflight_list_report,
    broadcast_preflight_report,
    rejected_nodes_report,
    transaction_plan_list_report,
    transaction_plan_report,
    transaction_artifact_list_report,
    transaction_artifact_report,
)
from ..rewards.store import RewardObserverStore
from ..rewards.tx_plans import build_transaction_plan
from ..rewards.signing import (
    ExplicitPrivateKeySigner,
    build_unsigned_transaction_artifact,
    sign_transaction_artifact,
)
from ..rewards.preflight import build_broadcast_preflight, export_signed_transaction_artifact


def main(argv: list[str] | None = None) -> int:
    """Run the reward observer CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    config = RewardObserverConfig.load_json(args.config)
    store = RewardObserverStore(config.storage_path)
    observer = RewardObserver(config=config, store=store)

    if args.command == "init":
        observer.initialize()
        _print_json(store.store_status())
        return 0

    if args.command == "store-status":
        observer.initialize()
        _print_json(store.store_status())
        return 0

    if args.command == "ingest-observation":
        observer.initialize()
        if args.reason_code is not None and args.reason_code not in REJECTION_CODES:
            raise ValueError(f"unsupported reason_code: {args.reason_code}")
        observation = NodeObservation(
            node_id=args.node_id,
            payout_address=args.payout_address,
            host=args.host,
            port=args.port,
            height=args.height,
            epoch_index=config.epoch_index_for_height(args.height),
            timestamp=args.timestamp,
            outcome=args.outcome,
            reason_code=args.reason_code,
            latency_ms=args.latency_ms,
            handshake_ok=_parse_bool(args.handshake_ok),
            network_ok=_parse_bool(args.network_ok),
            registration_status=args.registration_status,
            warmup_status=_parse_bool(args.warmup_status),
            banned=_parse_bool(args.banned),
            registration_source="manual",
            warmup_source="manual",
            ban_source="manual",
            endpoint_source="manual",
            public_ip=args.public_ip,
            fingerprint=args.fingerprint,
        )
        observer.ingest_observation(observation)
        _print_json({"ingested": True, "epoch_index": observation.epoch_index, "node_id": observation.node_id})
        return 0

    if args.command == "import-node-state":
        observer.initialize()
        node_data_path = args.node_data if args.node_data is not None else config.node_data_path
        if node_data_path is None:
            raise ValueError("node data path required via --node-data or config.node_data_path")
        service = NodeService.open_sqlite(node_data_path, network=config.network)
        observations = observer.ingest_node_service_snapshot(service)
        _print_json(
            {
                "imported": len(observations),
                "epoch_index": None if not observations else observations[0].epoch_index,
                "node_ids": [observation.node_id for observation in observations],
            }
        )
        return 0

    if args.command == "recompute-epoch":
        observer.initialize()
        epoch_index = args.epoch_index
        if epoch_index is None:
            epoch_index = observer.latest_epoch_index()
        if epoch_index is None:
            _print_json({"epoch_index": None, "node_count": 0})
            return 0
        summaries = observer.recompute_epoch(epoch_index)
        _print_json(build_epoch_summary(epoch_index, summaries))
        return 0

    if args.command == "propose-batch":
        observer.initialize()
        epoch_index = args.epoch_index
        summaries = store.list_epoch_summaries(epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(epoch_index)
        batch, items = build_dry_run_batch(
            epoch_index=epoch_index,
            network=config.network,
            summaries=summaries,
            created_at=args.created_at if args.created_at is not None else int(time.time()),
            created_by=args.operator,
            operator_note=args.note,
        )
        batch = finalize_batch_review_snapshot(batch, items)
        store.insert_payout_batch(batch, items)
        _print_json(payout_batch_report(batch, items))
        return 0

    if args.command == "show-batch":
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            _print_json({"batch_id": args.batch_id, "found": False})
            return 0
        batch, items = payload
        _print_json(payout_batch_report(batch, items))
        return 0

    if args.command == "list-batches":
        observer.initialize()
        _print_json(payout_batch_list_report(store.list_payout_batches()))
        return 0

    if args.command in {"approve-batch", "reject-batch", "simulate-batch"}:
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            raise ValueError(f"unknown batch_id: {args.batch_id}")
        batch, items = payload
        status = {
            "approve-batch": "approved",
            "reject-batch": "rejected",
            "simulate-batch": "simulated",
        }[args.command]
        updated = transition_batch(
            batch,
            status=status,
            reviewed_at=args.timestamp if args.timestamp is not None else int(time.time()),
            reviewed_by=args.operator,
            operator_note=args.note,
        )
        updated = finalize_batch_review_snapshot(updated, items)
        store.update_payout_batch(updated)
        _print_json(payout_batch_report(updated, items))
        return 0

    if args.command == "batch-items":
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            _print_json({"batch_id": args.batch_id, "found": False})
            return 0
        _batch, items = payload
        _print_json(batch_items_report(items))
        return 0

    if args.command in {"review-batch", "batch-audit"}:
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            raise ValueError(f"unknown batch_id: {args.batch_id}")
        batch, items = payload
        summaries = store.list_epoch_summaries(batch.epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(batch.epoch_index)
        validation = validate_batch(batch=batch, items=items, epoch_summaries=summaries)
        if args.command == "review-batch":
            _print_json(batch_review_report(batch, items, epoch_summaries=summaries, validation=validation))
        else:
            _print_json(batch_audit_report(batch, items, validation=validation))
        return 0

    if args.command == "compare-epoch-batch":
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            raise ValueError(f"unknown batch_id: {args.batch_id}")
        batch, items = payload
        summaries = store.list_epoch_summaries(args.epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(args.epoch_index)
        _print_json(compare_epoch_to_batch(epoch_index=args.epoch_index, batch=batch, items=items, epoch_summaries=summaries))
        return 0

    if args.command == "plan-transaction":
        observer.initialize()
        payload = store.get_payout_batch(args.batch_id)
        if payload is None:
            raise ValueError(f"unknown batch_id: {args.batch_id}")
        batch, items = payload
        funding_utxos = _load_planning_utxos(args.utxo_file)
        plan, plan_inputs, plan_outputs = build_transaction_plan(
            batch=batch,
            items=items,
            funding_utxos=funding_utxos,
            funding_assumption=args.funding_assumption,
            change_address=args.change_address,
            fee_rate_chipbits_per_weight_unit=args.fee_rate_chipbits_per_weight_unit,
            dust_threshold_chipbits=args.dust_threshold_chipbits,
            min_input_confirmations=args.min_input_confirmations,
            created_at=args.created_at if args.created_at is not None else int(time.time()),
            created_by=args.operator,
            dust_policy=args.dust_policy,
        )
        store.insert_transaction_plan(plan, plan_inputs, plan_outputs)
        _print_json(transaction_plan_report(plan, plan_inputs, plan_outputs))
        return 0

    if args.command == "show-transaction-plan":
        observer.initialize()
        payload = store.get_transaction_plan(args.plan_id)
        if payload is None:
            _print_json({"plan_id": args.plan_id, "found": False})
            return 0
        plan, plan_inputs, plan_outputs = payload
        _print_json(transaction_plan_report(plan, plan_inputs, plan_outputs))
        return 0

    if args.command == "list-transaction-plans":
        observer.initialize()
        _print_json(transaction_plan_list_report(store.list_transaction_plans()))
        return 0

    if args.command == "build-unsigned-transaction":
        observer.initialize()
        payload = store.get_transaction_plan(args.plan_id)
        if payload is None:
            raise ValueError(f"unknown plan_id: {args.plan_id}")
        plan, plan_inputs, plan_outputs = payload
        artifact, _unsigned_tx = build_unsigned_transaction_artifact(
            plan=plan,
            inputs=plan_inputs,
            outputs=plan_outputs,
            created_at=args.created_at if args.created_at is not None else int(time.time()),
            created_by=args.operator,
        )
        store.insert_transaction_artifact(artifact)
        _print_json(transaction_artifact_report(artifact))
        return 0

    if args.command in {"show-unsigned-transaction", "show-signed-transaction"}:
        observer.initialize()
        artifact = store.get_transaction_artifact(args.artifact_id)
        if artifact is None:
            _print_json({"artifact_id": args.artifact_id, "found": False})
            return 0
        _print_json(transaction_artifact_report(artifact))
        return 0

    if args.command == "list-signed-transactions":
        observer.initialize()
        _print_json(transaction_artifact_list_report(store.list_transaction_artifacts(signed_only=True)))
        return 0

    if args.command == "preflight-broadcast":
        observer.initialize()
        artifact = store.get_transaction_artifact(args.artifact_id)
        if artifact is None:
            raise ValueError(f"unknown artifact_id: {args.artifact_id}")
        plan_payload = store.get_transaction_plan(artifact.plan_id)
        if plan_payload is None:
            raise ValueError(f"missing plan for artifact: {artifact.plan_id}")
        batch_payload = store.get_payout_batch(artifact.batch_id)
        if batch_payload is None:
            raise ValueError(f"missing batch for artifact: {artifact.batch_id}")
        plan, plan_inputs, plan_outputs = plan_payload
        batch, _batch_items = batch_payload
        preflight, _report, input_outpoints = build_broadcast_preflight(
            artifact=artifact,
            plan=plan,
            batch=batch,
            inputs=plan_inputs,
            outputs=plan_outputs,
            network=config.network,
            created_at=args.created_at if args.created_at is not None else int(time.time()),
            created_by=args.operator,
            existing_ready_input_conflicts=store.find_preflight_input_conflicts(),
        )
        store.insert_broadcast_preflight(preflight, input_outpoints=input_outpoints)
        _print_json(broadcast_preflight_report(preflight, input_outpoints=input_outpoints))
        return 0

    if args.command == "show-broadcast-preflight":
        observer.initialize()
        payload = store.get_broadcast_preflight(args.preflight_id)
        if payload is None:
            _print_json({"preflight_id": args.preflight_id, "found": False})
            return 0
        preflight, input_outpoints = payload
        _print_json(broadcast_preflight_report(preflight, input_outpoints=input_outpoints))
        return 0

    if args.command == "list-broadcast-preflights":
        observer.initialize()
        _print_json(broadcast_preflight_list_report(store.list_broadcast_preflights()))
        return 0

    if args.command == "export-signed-transaction":
        observer.initialize()
        artifact = store.get_transaction_artifact(args.artifact_id)
        if artifact is None:
            raise ValueError(f"unknown artifact_id: {args.artifact_id}")
        _print_json(export_signed_transaction_artifact(artifact))
        return 0

    if args.command == "sign-transaction":
        observer.initialize()
        artifact = store.get_transaction_artifact(args.artifact_id)
        if artifact is None:
            raise ValueError(f"unknown artifact_id: {args.artifact_id}")
        payload = store.get_transaction_plan(artifact.plan_id)
        if payload is None:
            raise ValueError(f"missing plan for artifact: {artifact.plan_id}")
        plan, plan_inputs, plan_outputs = payload
        signer = ExplicitPrivateKeySigner(Path(args.key_file).read_text(encoding="utf-8").strip())
        signed_artifact, _signed_tx = sign_transaction_artifact(
            artifact=artifact,
            plan=plan,
            inputs=plan_inputs,
            outputs=plan_outputs,
            signer=signer,
            created_at=args.created_at if args.created_at is not None else int(time.time()),
            created_by=args.operator,
        )
        store.insert_transaction_artifact(signed_artifact)
        _print_json(transaction_artifact_report(signed_artifact))
        return 0

    observer.initialize()
    epoch_index = args.epoch_index
    if epoch_index is None:
        epoch_index = observer.latest_epoch_index()
    if epoch_index is None:
        _print_json({"epoch_index": None, "node_count": 0})
        return 0

    if args.command == "current-epoch-summary":
        summaries = store.list_epoch_summaries(epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(epoch_index)
        _print_json(build_epoch_summary(epoch_index, summaries))
        return 0

    if args.command == "eligible-nodes":
        summaries = store.list_epoch_summaries(epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(epoch_index)
        _print_json(eligible_nodes_report(summaries))
        return 0

    if args.command == "rejected-nodes":
        summaries = store.list_epoch_summaries(epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(epoch_index)
        _print_json(rejected_nodes_report(summaries))
        return 0

    if args.command == "concentration-report":
        summaries = store.list_epoch_summaries(epoch_index)
        if not summaries:
            summaries = observer.recompute_epoch(epoch_index)
        _print_json(concentration_report(summaries))
        return 0

    if args.command == "observation-stats":
        observations = store.list_observations(epoch_index=epoch_index)
        _print_json(observation_stats_report(epoch_index, observations))
        return 0

    parser.error("unsupported command")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chipcoin-reward-observer")
    parser.add_argument("--config", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("store-status")

    ingest = subparsers.add_parser("ingest-observation")
    ingest.add_argument("--node-id", required=True)
    ingest.add_argument("--payout-address", required=True)
    ingest.add_argument("--host", required=True)
    ingest.add_argument("--port", type=int, required=True)
    ingest.add_argument("--height", type=int, required=True)
    ingest.add_argument("--timestamp", type=int, required=True)
    ingest.add_argument("--outcome", choices=("success", "failure", "unchecked"), required=True)
    ingest.add_argument("--reason-code")
    ingest.add_argument("--latency-ms", type=int)
    ingest.add_argument("--handshake-ok", default="true")
    ingest.add_argument("--network-ok", default="true")
    ingest.add_argument("--registration-status", choices=("registered", "expired", "unregistered"), default="registered")
    ingest.add_argument("--warmup-status", default="true")
    ingest.add_argument("--banned", default="false")
    ingest.add_argument("--public-ip")
    ingest.add_argument("--fingerprint")

    recompute = subparsers.add_parser("recompute-epoch")
    recompute.add_argument("--epoch-index", type=int)

    import_node_state = subparsers.add_parser("import-node-state")
    import_node_state.add_argument("--node-data")

    propose_batch = subparsers.add_parser("propose-batch")
    propose_batch.add_argument("--epoch-index", type=int, required=True)
    propose_batch.add_argument("--operator")
    propose_batch.add_argument("--note")
    propose_batch.add_argument("--created-at", type=int)

    show_batch = subparsers.add_parser("show-batch")
    show_batch.add_argument("--batch-id", required=True)

    batch_items = subparsers.add_parser("batch-items")
    batch_items.add_argument("--batch-id", required=True)

    subparsers.add_parser("list-batches")

    approve_batch = subparsers.add_parser("approve-batch")
    approve_batch.add_argument("--batch-id", required=True)
    approve_batch.add_argument("--operator")
    approve_batch.add_argument("--note")
    approve_batch.add_argument("--timestamp", type=int)

    reject_batch = subparsers.add_parser("reject-batch")
    reject_batch.add_argument("--batch-id", required=True)
    reject_batch.add_argument("--operator")
    reject_batch.add_argument("--note")
    reject_batch.add_argument("--timestamp", type=int)

    simulate_batch = subparsers.add_parser("simulate-batch")
    simulate_batch.add_argument("--batch-id", required=True)
    simulate_batch.add_argument("--operator")
    simulate_batch.add_argument("--note")
    simulate_batch.add_argument("--timestamp", type=int)

    review_batch = subparsers.add_parser("review-batch")
    review_batch.add_argument("--batch-id", required=True)

    batch_audit = subparsers.add_parser("batch-audit")
    batch_audit.add_argument("--batch-id", required=True)

    compare_epoch_batch = subparsers.add_parser("compare-epoch-batch")
    compare_epoch_batch.add_argument("--epoch-index", type=int, required=True)
    compare_epoch_batch.add_argument("--batch-id", required=True)

    plan_transaction = subparsers.add_parser("plan-transaction")
    plan_transaction.add_argument("--batch-id", required=True)
    plan_transaction.add_argument("--utxo-file", required=True)
    plan_transaction.add_argument("--funding-assumption", default="manual_utxo_set")
    plan_transaction.add_argument("--change-address", required=True)
    plan_transaction.add_argument("--fee-rate-chipbits-per-weight-unit", type=int, default=1)
    plan_transaction.add_argument("--dust-threshold-chipbits", type=int, default=546)
    plan_transaction.add_argument("--min-input-confirmations", type=int, default=1)
    plan_transaction.add_argument("--dust-policy", default="reject")
    plan_transaction.add_argument("--created-at", type=int)
    plan_transaction.add_argument("--operator")

    show_transaction_plan = subparsers.add_parser("show-transaction-plan")
    show_transaction_plan.add_argument("--plan-id", required=True)

    subparsers.add_parser("list-transaction-plans")

    build_unsigned_tx = subparsers.add_parser("build-unsigned-transaction")
    build_unsigned_tx.add_argument("--plan-id", required=True)
    build_unsigned_tx.add_argument("--created-at", type=int)
    build_unsigned_tx.add_argument("--operator")

    show_unsigned_tx = subparsers.add_parser("show-unsigned-transaction")
    show_unsigned_tx.add_argument("--artifact-id", required=True)

    sign_tx = subparsers.add_parser("sign-transaction")
    sign_tx.add_argument("--artifact-id", required=True)
    sign_tx.add_argument("--key-file", required=True)
    sign_tx.add_argument("--created-at", type=int)
    sign_tx.add_argument("--operator")

    show_signed_tx = subparsers.add_parser("show-signed-transaction")
    show_signed_tx.add_argument("--artifact-id", required=True)

    subparsers.add_parser("list-signed-transactions")

    preflight_broadcast = subparsers.add_parser("preflight-broadcast")
    preflight_broadcast.add_argument("--artifact-id", required=True)
    preflight_broadcast.add_argument("--created-at", type=int)
    preflight_broadcast.add_argument("--operator")

    show_preflight = subparsers.add_parser("show-broadcast-preflight")
    show_preflight.add_argument("--preflight-id", required=True)

    export_signed = subparsers.add_parser("export-signed-transaction")
    export_signed.add_argument("--artifact-id", required=True)

    subparsers.add_parser("list-broadcast-preflights")

    summary = subparsers.add_parser("current-epoch-summary")
    summary.add_argument("--epoch-index", type=int)

    eligible = subparsers.add_parser("eligible-nodes")
    eligible.add_argument("--epoch-index", type=int)

    rejected = subparsers.add_parser("rejected-nodes")
    rejected.add_argument("--epoch-index", type=int)

    concentration = subparsers.add_parser("concentration-report")
    concentration.add_argument("--epoch-index", type=int)

    observation_stats = subparsers.add_parser("observation-stats")
    observation_stats.add_argument("--epoch-index", type=int)

    return parser


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {raw}")


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def _load_planning_utxos(path: str) -> list[PlanningUtxo]:
    raw = json.loads(open(path, "r", encoding="utf-8").read())
    if not isinstance(raw, list):
        raise ValueError("utxo file must contain a JSON array")
    return [
        PlanningUtxo(
            txid=str(item["txid"]),
            index=int(item["index"]),
            amount_chipbits=int(item["amount_chipbits"]),
            recipient=str(item["recipient"]),
            confirmations=int(item["confirmations"]),
            coinbase=bool(item.get("coinbase", False)),
        )
        for item in raw
    ]
