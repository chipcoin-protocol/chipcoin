"""Minimal SQLite persistence for observer-only reward tracking."""

from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3
from pathlib import Path

from .models import (
    BroadcastPreflight,
    NodeEpochSummary,
    NodeIdentity,
    NodeObservation,
    PayoutBatch,
    PayoutBatchItem,
    TransactionArtifact,
    TransactionPlan,
    TransactionPlanInput,
    TransactionPlanOutput,
)
from .schema import SCHEMA_SQL, SCHEMA_VERSION


class RewardObserverStore:
    """Thin SQLite store for observations and epoch summaries."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        """Initialize all required tables."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            connection.commit()

    def store_status(self) -> dict[str, int | str | None]:
        """Return simple store diagnostics."""

        with self._connect() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key = ?", ("schema_version",)).fetchone()
            observation_count = connection.execute("SELECT COUNT(*) AS count FROM observations").fetchone()["count"]
            summary_count = connection.execute("SELECT COUNT(*) AS count FROM epoch_node_summaries").fetchone()["count"]
            batch_count = connection.execute("SELECT COUNT(*) AS count FROM payout_batches").fetchone()["count"]
            plan_count = connection.execute("SELECT COUNT(*) AS count FROM transaction_plans").fetchone()["count"]
            artifact_count = connection.execute("SELECT COUNT(*) AS count FROM transaction_artifacts").fetchone()["count"]
            preflight_count = connection.execute("SELECT COUNT(*) AS count FROM broadcast_preflights").fetchone()["count"]
            latest_epoch_row = connection.execute("SELECT MAX(epoch_index) AS epoch_index FROM observations").fetchone()
            return {
                "path": str(self.path),
                "schema_version": None if row is None else int(row["value"]),
                "observation_count": int(observation_count),
                "epoch_summary_count": int(summary_count),
                "batch_count": int(batch_count),
                "plan_count": int(plan_count),
                "artifact_count": int(artifact_count),
                "preflight_count": int(preflight_count),
                "latest_epoch_index": latest_epoch_row["epoch_index"],
            }

    def upsert_node(self, identity: NodeIdentity, *, last_seen: int) -> None:
        """Insert or update one node identity row."""

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT first_seen FROM nodes WHERE node_id = ?",
                (identity.node_id,),
            ).fetchone()
            first_seen = identity.first_seen if existing is None else int(existing["first_seen"])
            connection.execute(
                """
                INSERT OR REPLACE INTO nodes(node_id, payout_address, host, port, first_seen, last_seen)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.node_id,
                    identity.payout_address,
                    identity.host,
                    identity.port,
                    first_seen,
                    last_seen,
                ),
            )
            connection.commit()

    def get_node(self, node_id: str) -> NodeIdentity | None:
        """Return one stored node identity when present."""

        with self._connect() as connection:
            row = connection.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
            if row is None:
                return None
            return NodeIdentity(
                node_id=str(row["node_id"]),
                payout_address=str(row["payout_address"]),
                host=str(row["host"]),
                port=int(row["port"]),
                first_seen=int(row["first_seen"]),
            )

    def append_observation(self, observation: NodeObservation) -> None:
        """Persist one raw observation and update node identity metadata."""

        self.upsert_node(
            NodeIdentity(
                node_id=observation.node_id,
                payout_address=observation.payout_address,
                host=observation.host,
                port=observation.port,
                first_seen=observation.timestamp,
            ),
            last_seen=observation.timestamp,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO observations(
                    node_id, payout_address, host, port, height, epoch_index, observed_at,
                    outcome, reason_code, latency_ms, handshake_ok, network_ok,
                    registration_status, warmup_status, banned, registration_source,
                    warmup_source, ban_source, endpoint_source, public_ip, fingerprint
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.node_id,
                    observation.payout_address,
                    observation.host,
                    observation.port,
                    observation.height,
                    observation.epoch_index,
                    observation.timestamp,
                    observation.outcome,
                    observation.reason_code,
                    observation.latency_ms,
                    int(observation.handshake_ok),
                    int(observation.network_ok),
                    observation.registration_status,
                    int(observation.warmup_status),
                    int(observation.banned),
                    observation.registration_source,
                    observation.warmup_source,
                    observation.ban_source,
                    observation.endpoint_source,
                    observation.public_ip,
                    observation.fingerprint,
                ),
            )
            connection.commit()

    def list_observations(self, *, epoch_index: int | None = None) -> list[NodeObservation]:
        """Return stored observations, optionally filtered to one epoch."""

        query = "SELECT * FROM observations"
        params: tuple[object, ...] = ()
        if epoch_index is not None:
            query += " WHERE epoch_index = ?"
            params = (epoch_index,)
        query += " ORDER BY epoch_index, node_id, observed_at, id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            NodeObservation(
                node_id=str(row["node_id"]),
                payout_address=str(row["payout_address"]),
                host=str(row["host"]),
                port=int(row["port"]),
                height=int(row["height"]),
                epoch_index=int(row["epoch_index"]),
                timestamp=int(row["observed_at"]),
                outcome=str(row["outcome"]),
                reason_code=None if row["reason_code"] is None else str(row["reason_code"]),
                latency_ms=None if row["latency_ms"] is None else int(row["latency_ms"]),
                handshake_ok=bool(row["handshake_ok"]),
                network_ok=bool(row["network_ok"]),
                registration_status=str(row["registration_status"]),
                warmup_status=bool(row["warmup_status"]),
                banned=bool(row["banned"]),
                registration_source=str(row["registration_source"]),
                warmup_source=str(row["warmup_source"]),
                ban_source=str(row["ban_source"]),
                endpoint_source=str(row["endpoint_source"]),
                public_ip=None if row["public_ip"] is None else str(row["public_ip"]),
                fingerprint=None if row["fingerprint"] is None else str(row["fingerprint"]),
            )
            for row in rows
        ]

    def replace_epoch_summaries(self, epoch_index: int, summaries: list[NodeEpochSummary]) -> None:
        """Replace all stored summaries for one epoch."""

        with self._connect() as connection:
            connection.execute("DELETE FROM epoch_node_summaries WHERE epoch_index = ?", (epoch_index,))
            for summary in summaries:
                payload = asdict(summary)
                connection.execute(
                    """
                    INSERT INTO epoch_node_summaries(
                        epoch_index, node_id, payout_address, host, port, first_seen, last_success,
                        success_count, failure_count, consecutive_failures, handshake_ok, network_ok,
                        registration_status, warmup_status, concentration_status, final_eligible,
                        rejection_reason, registration_source, warmup_source, ban_source, endpoint_source,
                        public_ip, subnet_key, fingerprint, checked_observation_count, observation_count
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["epoch_index"],
                        payload["node_id"],
                        payload["payout_address"],
                        payload["host"],
                        payload["port"],
                        payload["first_seen"],
                        payload["last_success"],
                        payload["success_count"],
                        payload["failure_count"],
                        payload["consecutive_failures"],
                        int(payload["handshake_ok"]),
                        int(payload["network_ok"]),
                        payload["registration_status"],
                        int(payload["warmup_status"]),
                        payload["concentration_status"],
                        int(payload["final_eligible"]),
                        payload["rejection_reason"],
                        payload["registration_source"],
                        payload["warmup_source"],
                        payload["ban_source"],
                        payload["endpoint_source"],
                        payload["public_ip"],
                        payload["subnet_key"],
                        payload["fingerprint"],
                        payload["checked_observation_count"],
                        payload["observation_count"],
                    ),
                )
            connection.commit()

    def list_epoch_summaries(self, epoch_index: int) -> list[NodeEpochSummary]:
        """Return one epoch's stored node summaries."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM epoch_node_summaries WHERE epoch_index = ? ORDER BY node_id, payout_address",
                (epoch_index,),
            ).fetchall()
        return [
            NodeEpochSummary(
                epoch_index=int(row["epoch_index"]),
                node_id=str(row["node_id"]),
                payout_address=str(row["payout_address"]),
                host=str(row["host"]),
                port=int(row["port"]),
                first_seen=int(row["first_seen"]),
                last_success=None if row["last_success"] is None else int(row["last_success"]),
                success_count=int(row["success_count"]),
                failure_count=int(row["failure_count"]),
                consecutive_failures=int(row["consecutive_failures"]),
                handshake_ok=bool(row["handshake_ok"]),
                network_ok=bool(row["network_ok"]),
                registration_status=str(row["registration_status"]),
                warmup_status=bool(row["warmup_status"]),
                concentration_status=str(row["concentration_status"]),
                final_eligible=bool(row["final_eligible"]),
                rejection_reason=None if row["rejection_reason"] is None else str(row["rejection_reason"]),
                registration_source=str(row["registration_source"]),
                warmup_source=str(row["warmup_source"]),
                ban_source=str(row["ban_source"]),
                endpoint_source=str(row["endpoint_source"]),
                public_ip=None if row["public_ip"] is None else str(row["public_ip"]),
                subnet_key=None if row["subnet_key"] is None else str(row["subnet_key"]),
                fingerprint=None if row["fingerprint"] is None else str(row["fingerprint"]),
                checked_observation_count=int(row["checked_observation_count"]),
                observation_count=int(row["observation_count"]),
            )
            for row in rows
        ]

    def latest_epoch_index(self) -> int | None:
        """Return the latest epoch seen in observations or summaries."""

        with self._connect() as connection:
            obs_row = connection.execute("SELECT MAX(epoch_index) AS epoch_index FROM observations").fetchone()
            sum_row = connection.execute("SELECT MAX(epoch_index) AS epoch_index FROM epoch_node_summaries").fetchone()
        values = [row["epoch_index"] for row in (obs_row, sum_row) if row["epoch_index"] is not None]
        if not values:
            return None
        return max(int(value) for value in values)

    def insert_payout_batch(self, batch: PayoutBatch, items: list[PayoutBatchItem]) -> None:
        """Persist one dry-run payout batch and all its items."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO payout_batches(
                    batch_id, epoch_index, network, status, scheduled_node_reward_chipbits,
                    eligible_node_count, rejected_node_count, allocated_total_chipbits,
                    unallocated_total_chipbits, zero_allocation_reason, provisional_evidence_count,
                    created_at, approved_at, reviewed_at, created_by, reviewed_by, operator_note,
                    review_result, review_reason, review_snapshot_hash, command_version
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.batch_id,
                    batch.epoch_index,
                    batch.network,
                    batch.status,
                    batch.scheduled_node_reward_chipbits,
                    batch.eligible_node_count,
                    batch.rejected_node_count,
                    batch.allocated_total_chipbits,
                    batch.unallocated_total_chipbits,
                    batch.zero_allocation_reason,
                    batch.provisional_evidence_count,
                    batch.created_at,
                    batch.approved_at,
                    batch.reviewed_at,
                    batch.created_by,
                    batch.reviewed_by,
                    batch.operator_note,
                    batch.review_result,
                    batch.review_reason,
                    batch.review_snapshot_hash,
                    batch.command_version,
                ),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO payout_batch_items(
                        batch_id, allocation_rank, node_id, payout_address, allocated_chipbits,
                        remainder_assigned, provisional_fields_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.batch_id,
                        item.allocation_rank,
                        item.node_id,
                        item.payout_address,
                        item.allocated_chipbits,
                        int(item.remainder_assigned),
                        json.dumps(list(item.provisional_fields), sort_keys=True),
                    ),
                )
            connection.commit()

    def get_payout_batch(self, batch_id: str) -> tuple[PayoutBatch, list[PayoutBatchItem]] | None:
        """Return one persisted batch and its items."""

        with self._connect() as connection:
            row = connection.execute("SELECT * FROM payout_batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if row is None:
                return None
            item_rows = connection.execute(
                "SELECT * FROM payout_batch_items WHERE batch_id = ? ORDER BY allocation_rank",
                (batch_id,),
            ).fetchall()
        return self._decode_batch(row), [self._decode_batch_item(item_row) for item_row in item_rows]

    def list_payout_batches(self) -> list[PayoutBatch]:
        """Return persisted dry-run payout batches in reverse chronological order."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM payout_batches ORDER BY created_at DESC, batch_id DESC"
            ).fetchall()
        return [self._decode_batch(row) for row in rows]

    def update_payout_batch(self, batch: PayoutBatch) -> None:
        """Persist one batch header state change without touching items."""

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE payout_batches
                SET status = ?, approved_at = ?, reviewed_at = ?, reviewed_by = ?, operator_note = ?,
                    review_result = ?, review_reason = ?, review_snapshot_hash = ?, command_version = ?
                WHERE batch_id = ?
                """,
                (
                    batch.status,
                    batch.approved_at,
                    batch.reviewed_at,
                    batch.reviewed_by,
                    batch.operator_note,
                    batch.review_result,
                    batch.review_reason,
                    batch.review_snapshot_hash,
                    batch.command_version,
                    batch.batch_id,
                ),
            )
            connection.commit()

    def _decode_batch(self, row: sqlite3.Row) -> PayoutBatch:
        return PayoutBatch(
            batch_id=str(row["batch_id"]),
            epoch_index=int(row["epoch_index"]),
            network=str(row["network"]),
            status=str(row["status"]),
            scheduled_node_reward_chipbits=int(row["scheduled_node_reward_chipbits"]),
            eligible_node_count=int(row["eligible_node_count"]),
            rejected_node_count=int(row["rejected_node_count"]),
            allocated_total_chipbits=int(row["allocated_total_chipbits"]),
            unallocated_total_chipbits=int(row["unallocated_total_chipbits"]),
            zero_allocation_reason=None
            if row["zero_allocation_reason"] is None
            else str(row["zero_allocation_reason"]),
            provisional_evidence_count=int(row["provisional_evidence_count"]),
            created_at=int(row["created_at"]),
            approved_at=None if row["approved_at"] is None else int(row["approved_at"]),
            reviewed_at=None if row["reviewed_at"] is None else int(row["reviewed_at"]),
            created_by=None if row["created_by"] is None else str(row["created_by"]),
            reviewed_by=None if row["reviewed_by"] is None else str(row["reviewed_by"]),
            operator_note=None if row["operator_note"] is None else str(row["operator_note"]),
            review_result=str(row["review_result"]),
            review_reason=None if row["review_reason"] is None else str(row["review_reason"]),
            review_snapshot_hash=None if row["review_snapshot_hash"] is None else str(row["review_snapshot_hash"]),
            command_version=None if row["command_version"] is None else str(row["command_version"]),
        )

    def _decode_batch_item(self, row: sqlite3.Row) -> PayoutBatchItem:
        provisional_fields = tuple(json.loads(str(row["provisional_fields_json"])))
        return PayoutBatchItem(
            batch_id=str(row["batch_id"]),
            allocation_rank=int(row["allocation_rank"]),
            node_id=str(row["node_id"]),
            payout_address=str(row["payout_address"]),
            allocated_chipbits=int(row["allocated_chipbits"]),
            remainder_assigned=bool(row["remainder_assigned"]),
            provisional_fields=provisional_fields,
        )

    def insert_transaction_plan(
        self,
        plan: TransactionPlan,
        inputs: list[TransactionPlanInput],
        outputs: list[TransactionPlanOutput],
    ) -> None:
        """Persist one dry transaction plan and its selected inputs/outputs."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transaction_plans(
                    plan_id, batch_id, status, funding_assumption, input_count, output_count,
                    estimated_fee_chipbits, total_input_chipbits, total_recipient_chipbits,
                    change_chipbits, dust_dropped_chipbits, insufficient_funds, created_at,
                    created_by, plan_snapshot_hash, fee_rate_chipbits_per_weight_unit,
                    dust_threshold_chipbits, min_input_confirmations, change_address, dust_policy,
                    provisional_warning_inherited, invalid_reason, command_version
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.batch_id,
                    plan.status,
                    plan.funding_assumption,
                    plan.input_count,
                    plan.output_count,
                    plan.estimated_fee_chipbits,
                    plan.total_input_chipbits,
                    plan.total_recipient_chipbits,
                    plan.change_chipbits,
                    plan.dust_dropped_chipbits,
                    int(plan.insufficient_funds),
                    plan.created_at,
                    plan.created_by,
                    plan.plan_snapshot_hash,
                    plan.fee_rate_chipbits_per_weight_unit,
                    plan.dust_threshold_chipbits,
                    plan.min_input_confirmations,
                    plan.change_address,
                    plan.dust_policy,
                    int(plan.provisional_warning_inherited),
                    plan.invalid_reason,
                    plan.command_version,
                ),
            )
            for item in inputs:
                connection.execute(
                    """
                    INSERT INTO transaction_plan_inputs(
                        plan_id, input_index, txid, vout, amount_chipbits, recipient, confirmations
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.plan_id,
                        item.input_index,
                        item.txid,
                        item.vout,
                        item.amount_chipbits,
                        item.recipient,
                        item.confirmations,
                    ),
                )
            for output in outputs:
                connection.execute(
                    """
                    INSERT INTO transaction_plan_outputs(
                        plan_id, output_index, output_kind, recipient, amount_chipbits, batch_node_id
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        output.plan_id,
                        output.output_index,
                        output.output_kind,
                        output.recipient,
                        output.amount_chipbits,
                        output.batch_node_id,
                    ),
                )
            connection.commit()

    def get_transaction_plan(
        self,
        plan_id: str,
    ) -> tuple[TransactionPlan, list[TransactionPlanInput], list[TransactionPlanOutput]] | None:
        """Return one persisted transaction plan with all components."""

        with self._connect() as connection:
            row = connection.execute("SELECT * FROM transaction_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            if row is None:
                return None
            input_rows = connection.execute(
                "SELECT * FROM transaction_plan_inputs WHERE plan_id = ? ORDER BY input_index",
                (plan_id,),
            ).fetchall()
            output_rows = connection.execute(
                "SELECT * FROM transaction_plan_outputs WHERE plan_id = ? ORDER BY output_index",
                (plan_id,),
            ).fetchall()
        return (
            self._decode_transaction_plan(row),
            [self._decode_transaction_plan_input(item) for item in input_rows],
            [self._decode_transaction_plan_output(item) for item in output_rows],
        )

    def list_transaction_plans(self) -> list[TransactionPlan]:
        """Return persisted dry transaction plans in reverse chronological order."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transaction_plans ORDER BY created_at DESC, plan_id DESC"
            ).fetchall()
        return [self._decode_transaction_plan(row) for row in rows]

    def _decode_transaction_plan(self, row: sqlite3.Row) -> TransactionPlan:
        return TransactionPlan(
            plan_id=str(row["plan_id"]),
            batch_id=str(row["batch_id"]),
            status=str(row["status"]),
            funding_assumption=str(row["funding_assumption"]),
            input_count=int(row["input_count"]),
            output_count=int(row["output_count"]),
            estimated_fee_chipbits=int(row["estimated_fee_chipbits"]),
            total_input_chipbits=int(row["total_input_chipbits"]),
            total_recipient_chipbits=int(row["total_recipient_chipbits"]),
            change_chipbits=int(row["change_chipbits"]),
            dust_dropped_chipbits=int(row["dust_dropped_chipbits"]),
            insufficient_funds=bool(row["insufficient_funds"]),
            created_at=int(row["created_at"]),
            created_by=None if row["created_by"] is None else str(row["created_by"]),
            plan_snapshot_hash=None if row["plan_snapshot_hash"] is None else str(row["plan_snapshot_hash"]),
            fee_rate_chipbits_per_weight_unit=int(row["fee_rate_chipbits_per_weight_unit"]),
            dust_threshold_chipbits=int(row["dust_threshold_chipbits"]),
            min_input_confirmations=int(row["min_input_confirmations"]),
            change_address=str(row["change_address"]),
            dust_policy=str(row["dust_policy"]),
            provisional_warning_inherited=bool(row["provisional_warning_inherited"]),
            invalid_reason=None if row["invalid_reason"] is None else str(row["invalid_reason"]),
            command_version=None if row["command_version"] is None else str(row["command_version"]),
        )

    def _decode_transaction_plan_input(self, row: sqlite3.Row) -> TransactionPlanInput:
        return TransactionPlanInput(
            plan_id=str(row["plan_id"]),
            input_index=int(row["input_index"]),
            txid=str(row["txid"]),
            vout=int(row["vout"]),
            amount_chipbits=int(row["amount_chipbits"]),
            recipient=str(row["recipient"]),
            confirmations=int(row["confirmations"]),
        )

    def _decode_transaction_plan_output(self, row: sqlite3.Row) -> TransactionPlanOutput:
        return TransactionPlanOutput(
            plan_id=str(row["plan_id"]),
            output_index=int(row["output_index"]),
            output_kind=str(row["output_kind"]),
            recipient=str(row["recipient"]),
            amount_chipbits=int(row["amount_chipbits"]),
            batch_node_id=None if row["batch_node_id"] is None else str(row["batch_node_id"]),
        )

    def insert_transaction_artifact(self, artifact: TransactionArtifact) -> None:
        """Persist one unsigned or signed local transaction artifact."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transaction_artifacts(
                    artifact_id, plan_id, batch_id, status, unsigned_tx_snapshot_hash,
                    signed_tx_snapshot_hash, signer_type, created_at, created_by,
                    validation_result, invalid_reason, broadcasted, sent, wallet_mutation, tx_hex
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.plan_id,
                    artifact.batch_id,
                    artifact.status,
                    artifact.unsigned_tx_snapshot_hash,
                    artifact.signed_tx_snapshot_hash,
                    artifact.signer_type,
                    artifact.created_at,
                    artifact.created_by,
                    artifact.validation_result,
                    artifact.invalid_reason,
                    int(artifact.broadcasted),
                    int(artifact.sent),
                    int(artifact.wallet_mutation),
                    artifact.tx_hex,
                ),
            )
            connection.commit()

    def get_transaction_artifact(self, artifact_id: str) -> TransactionArtifact | None:
        """Return one locally stored transaction artifact."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM transaction_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_transaction_artifact(row)

    def list_transaction_artifacts(self, *, signed_only: bool = False) -> list[TransactionArtifact]:
        """Return local transaction artifacts, optionally filtered to signed ones."""

        query = "SELECT * FROM transaction_artifacts"
        params: tuple[object, ...] = ()
        if signed_only:
            query += " WHERE status = ?"
            params = ("signed",)
        query += " ORDER BY created_at DESC, artifact_id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._decode_transaction_artifact(row) for row in rows]

    def _decode_transaction_artifact(self, row: sqlite3.Row) -> TransactionArtifact:
        return TransactionArtifact(
            artifact_id=str(row["artifact_id"]),
            plan_id=str(row["plan_id"]),
            batch_id=str(row["batch_id"]),
            status=str(row["status"]),
            unsigned_tx_snapshot_hash=str(row["unsigned_tx_snapshot_hash"]),
            signed_tx_snapshot_hash=None
            if row["signed_tx_snapshot_hash"] is None
            else str(row["signed_tx_snapshot_hash"]),
            signer_type=None if row["signer_type"] is None else str(row["signer_type"]),
            created_at=int(row["created_at"]),
            created_by=None if row["created_by"] is None else str(row["created_by"]),
            validation_result=str(row["validation_result"]),
            invalid_reason=None if row["invalid_reason"] is None else str(row["invalid_reason"]),
            broadcasted=bool(row["broadcasted"]),
            sent=bool(row["sent"]),
            wallet_mutation=bool(row["wallet_mutation"]),
            tx_hex=str(row["tx_hex"]),
        )

    def insert_broadcast_preflight(
        self,
        preflight: BroadcastPreflight,
        *,
        input_outpoints: list[tuple[int, str, int]],
    ) -> None:
        """Persist one local-only broadcast preflight plus its referenced inputs."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broadcast_preflights(
                    preflight_id, artifact_id, batch_id, plan_id, txid, serialization_hash,
                    status, preflight_result, blocking_reason, warning_count, created_at,
                    created_by, network, ready_for_manual_broadcast, warnings_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preflight.preflight_id,
                    preflight.artifact_id,
                    preflight.batch_id,
                    preflight.plan_id,
                    preflight.txid,
                    preflight.serialization_hash,
                    preflight.status,
                    preflight.preflight_result,
                    preflight.blocking_reason,
                    preflight.warning_count,
                    preflight.created_at,
                    preflight.created_by,
                    preflight.network,
                    int(preflight.ready_for_manual_broadcast),
                    preflight.warnings_json,
                ),
            )
            for input_index, txid, vout in input_outpoints:
                connection.execute(
                    """
                    INSERT INTO broadcast_preflight_inputs(preflight_id, input_index, txid, vout)
                    VALUES(?, ?, ?, ?)
                    """,
                    (preflight.preflight_id, input_index, txid, vout),
                )
            connection.commit()

    def get_broadcast_preflight(
        self, preflight_id: str
    ) -> tuple[BroadcastPreflight, list[tuple[int, str, int]]] | None:
        """Return one stored broadcast preflight and its referenced inputs."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM broadcast_preflights WHERE preflight_id = ?",
                (preflight_id,),
            ).fetchone()
            if row is None:
                return None
            input_rows = connection.execute(
                """
                SELECT input_index, txid, vout
                FROM broadcast_preflight_inputs
                WHERE preflight_id = ?
                ORDER BY input_index
                """,
                (preflight_id,),
            ).fetchall()
        return self._decode_broadcast_preflight(row), [
            (int(item["input_index"]), str(item["txid"]), int(item["vout"])) for item in input_rows
        ]

    def list_broadcast_preflights(self) -> list[BroadcastPreflight]:
        """Return stored broadcast preflights in reverse creation order."""

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM broadcast_preflights ORDER BY created_at DESC, preflight_id DESC"
            ).fetchall()
        return [self._decode_broadcast_preflight(row) for row in rows]

    def find_preflight_input_conflicts(
        self,
        *,
        excluded_preflight_id: str | None = None,
        only_ready: bool = True,
    ) -> dict[tuple[str, int], list[str]]:
        """Return local duplicate-input usage across stored preflights."""

        query = """
            SELECT i.txid, i.vout, i.preflight_id
            FROM broadcast_preflight_inputs AS i
            JOIN broadcast_preflights AS p ON p.preflight_id = i.preflight_id
        """
        clauses: list[str] = []
        params: list[object] = []
        if only_ready:
            clauses.append("p.ready_for_manual_broadcast = ?")
            params.append(1)
        if excluded_preflight_id is not None:
            clauses.append("p.preflight_id != ?")
            params.append(excluded_preflight_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        conflicts: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            outpoint = (str(row["txid"]), int(row["vout"]))
            conflicts.setdefault(outpoint, []).append(str(row["preflight_id"]))
        return conflicts

    def _decode_broadcast_preflight(self, row: sqlite3.Row) -> BroadcastPreflight:
        return BroadcastPreflight(
            preflight_id=str(row["preflight_id"]),
            artifact_id=str(row["artifact_id"]),
            batch_id=str(row["batch_id"]),
            plan_id=str(row["plan_id"]),
            txid=str(row["txid"]),
            serialization_hash=str(row["serialization_hash"]),
            status=str(row["status"]),
            preflight_result=str(row["preflight_result"]),
            blocking_reason=None if row["blocking_reason"] is None else str(row["blocking_reason"]),
            warning_count=int(row["warning_count"]),
            created_at=int(row["created_at"]),
            created_by=None if row["created_by"] is None else str(row["created_by"]),
            network=str(row["network"]),
            ready_for_manual_broadcast=bool(row["ready_for_manual_broadcast"]),
            warnings_json=str(row["warnings_json"]),
        )
