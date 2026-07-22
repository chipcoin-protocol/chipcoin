"""Operational post-quantum activation smoke workflow."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
from typing import Any
from wsgiref.util import setup_testing_defaults
import io
import shutil

from ..consensus.models import Block, OutPoint, Transaction
from ..consensus.params import TESTNET_PARAMS
from ..consensus.pow import verify_proof_of_work
from ..consensus.pq_activation import PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT, pq_support_activation_height, pq_support_is_active
from ..consensus.validation import ValidationError
from ..crypto.addresses import is_valid_address, parse_address
from ..crypto.pq import SIG_SCHEME_ML_DSA_44
from ..interfaces.http_api import HttpApiApp
from ..node.service import NodeService
from ..wallet.signer import TransactionSigner, wallet_key_from_mldsa44_seed, wallet_key_from_private_key


DEFAULT_PQ_SMOKE_ACTIVATION_HEIGHT = 20
TESTNET_PQ_ACTIVATION_HEIGHT = PQ_SUPPORT_TESTNET_ACTIVATION_HEIGHT
PQ_SMOKE_NETWORK = "testnet"
PQ_SMOKE_SCHEME_NAME = "ML-DSA-44"


@dataclass(frozen=True)
class PqSmokeStage:
    """One smoke-test stage result."""

    label: str
    status: str = "PASS"


@dataclass(frozen=True)
class PqSmokeResult:
    """Structured result for the operational PQ smoke workflow."""

    ready: bool
    activation_height: int
    final_local_height: int
    pq_scheme: str
    stages: tuple[PqSmokeStage, ...]
    state_path: str
    state_preserved: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_json_payload(self) -> dict[str, Any]:
        """Return a stable machine-readable result."""

        return {
            "ready": self.ready,
            "activation_height": self.activation_height,
            "final_local_height": self.final_local_height,
            "pq_scheme": self.pq_scheme,
            "state_path": self.state_path,
            "state_preserved": self.state_preserved,
            "stages": [{"status": stage.status, "label": stage.label} for stage in self.stages],
            "details": self.details,
        }


class PqSmokeError(RuntimeError):
    """Operational failure with a concise user-facing stage and reason."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def make_pq_readiness_params(*, activation_height: int):
    """Return test-only consensus params for deterministic local PQ activation."""

    validate_activation_height(activation_height)
    return replace(
        TESTNET_PARAMS,
        coinbase_maturity=0,
        genesis_bits=0x207FFFFF,
        difficulty_adjustment_window=1000,
        target_block_time_activation_height=0,
        legacy_target_block_time_seconds=None,
        pq_support_activation_height=activation_height,
    )


def validate_activation_height(activation_height: int) -> None:
    """Reject unsafe or nonsensical local smoke activation heights."""

    if activation_height < 2:
        raise PqSmokeError("configuration", "activation height must be at least 2")
    if activation_height > 10_000:
        raise PqSmokeError("configuration", "activation height must be at most 10000 for the local smoke test")


def run_pq_smoke(*, activation_height: int = DEFAULT_PQ_SMOKE_ACTIVATION_HEIGHT, keep_state: bool = False) -> PqSmokeResult:
    """Run the operational CHCQ activation smoke workflow in a temporary node."""

    validate_activation_height(activation_height)
    state_path = Path(mkdtemp(prefix="chipcoin-pq-smoke-")) if keep_state else None
    tempdir: TemporaryDirectory[str] | None = None
    if state_path is None:
        tempdir = TemporaryDirectory(prefix="chipcoin-pq-smoke-")
        state_path = Path(tempdir.name)

    stages: list[PqSmokeStage] = []
    details: dict[str, Any] = {"api_metadata_source": "HttpApiApp"}
    try:
        _assert_production_activation_unchanged()
        params = make_pq_readiness_params(activation_height=activation_height)
        service = _make_service(state_path / "node.sqlite3", params=params)
        app = HttpApiApp(service)

        legacy_owner = _legacy_wallet(0)
        legacy_destination = _legacy_wallet(1)
        miner = _legacy_wallet(2)
        pq_owner = wallet_key_from_mldsa44_seed(bytes(range(32)))

        pq_info = parse_address(pq_owner.address)
        if not is_valid_address(pq_owner.address):
            raise PqSmokeError("created CHCQ address", "generated CHCQ address is syntactically invalid")
        if pq_info.kind != "pq" or pq_info.scheme_id != SIG_SCHEME_ML_DSA_44:
            raise PqSmokeError("created CHCQ address", "generated CHCQ address did not resolve to ML-DSA-44")
        stages.append(PqSmokeStage("created CHCQ address"))

        funding_block = mine_next_block(service, legacy_owner.address)
        funding_tx = funding_block.transactions[0]
        funding_outpoint = OutPoint(txid=funding_tx.txid(), index=0)
        funding_value = int(funding_tx.outputs[0].value)

        pre_activation_tx = _legacy_payment(
            funding_outpoint,
            value=funding_value,
            sender=legacy_owner,
            recipient=pq_owner.address,
            amount=400_000_000,
            fee=1_000,
        )
        _expect_rejection(
            "pre-activation rejected",
            lambda: service.receive_transaction(pre_activation_tx),
            "CHCQ outputs are not active",
        )
        if service.list_mempool_transactions():
            raise PqSmokeError("pre-activation rejected", "rejected CHCQ transaction entered the mempool")
        if service.list_spendable_outputs(pq_owner.address):
            raise PqSmokeError("pre-activation rejected", "pre-activation CHCQ UTXO was created")
        stages.append(PqSmokeStage("pre-activation rejected"))

        mine_to_height(service, activation_height, miner.address)
        tip = service.chain_tip()
        current_height = -1 if tip is None else tip.height
        if current_height < activation_height:
            raise PqSmokeError("activation reached", f"local height {current_height} is below activation height {activation_height}")
        if not pq_support_is_active(network=PQ_SMOKE_NETWORK, height=current_height, params=params):
            raise PqSmokeError("activation reached", "production activation policy reports inactive after local activation height")
        stages.append(PqSmokeStage("activation reached"))

        chc_to_chcq = _legacy_payment(
            funding_outpoint,
            value=funding_value,
            sender=legacy_owner,
            recipient=pq_owner.address,
            amount=400_000_000,
            fee=1_000,
        )
        service.receive_transaction(chc_to_chcq)
        mine_next_block(service, miner.address)
        chcq_outpoint = OutPoint(txid=chc_to_chcq.txid(), index=0)
        chcq_entry = service.chainstate.get(chcq_outpoint)
        if chcq_entry is None:
            raise PqSmokeError("CHC -> CHCQ mined", "expected CHCQ UTXO was not created")
        if int(chcq_entry.output.value) != 400_000_000:
            raise PqSmokeError("CHC -> CHCQ mined", "CHCQ UTXO amount does not match expected value")
        if parse_address(chcq_entry.output.recipient).scheme_id != SIG_SCHEME_ML_DSA_44:
            raise PqSmokeError("CHC -> CHCQ mined", "CHCQ UTXO does not carry ML-DSA-44 scheme")
        if service.find_transaction(chc_to_chcq.txid())["location"] != "chain":
            raise PqSmokeError("CHC -> CHCQ mined", "CHC -> CHCQ transaction is not indexed on chain")
        stages.append(PqSmokeStage("CHC -> CHCQ mined"))

        chcq_to_chc = _pq_payment(
            owner=pq_owner,
            outpoint=chcq_outpoint,
            value=400_000_000,
            recipient=legacy_destination.address,
            amount=399_999_000,
            fee=1_000,
        )
        if chcq_to_chc.inputs[0].sig_scheme_id != SIG_SCHEME_ML_DSA_44:
            raise PqSmokeError("CHCQ -> CHC mined", "CHCQ spend did not use ML-DSA-44 input scheme")
        service.receive_transaction(chcq_to_chc)
        mine_next_block(service, miner.address)
        if service.chainstate.get(chcq_outpoint) is not None:
            raise PqSmokeError("CHCQ -> CHC mined", "spent CHCQ UTXO remains unspent")
        legacy_received = OutPoint(txid=chcq_to_chc.txid(), index=0)
        legacy_entry = service.chainstate.get(legacy_received)
        if legacy_entry is None or legacy_entry.output.recipient != legacy_destination.address:
            raise PqSmokeError("CHCQ -> CHC mined", "legacy destination did not receive the CHCQ spend output")
        if service.find_transaction(chcq_to_chc.txid())["location"] != "chain":
            raise PqSmokeError("CHCQ -> CHC mined", "CHCQ -> CHC transaction is not indexed on chain")
        stages.append(PqSmokeStage("CHCQ -> CHC mined"))

        _validate_api_metadata(app, chc_to_chcq=chc_to_chcq, chcq_to_chc=chcq_to_chc, pq_address=pq_owner.address)
        stages.append(PqSmokeStage("API metadata OK"))

        final_tip = service.chain_tip()
        final_height = -1 if final_tip is None else final_tip.height
        details.update(
            {
                "chcq_address": pq_owner.address,
                "chc_to_chcq_txid": chc_to_chcq.txid(),
                "chcq_to_chc_txid": chcq_to_chc.txid(),
                "production_testnet_activation_height": pq_support_activation_height("testnet"),
            }
        )
        return PqSmokeResult(
            ready=True,
            activation_height=activation_height,
            final_local_height=final_height,
            pq_scheme=PQ_SMOKE_SCHEME_NAME,
            stages=tuple(stages),
            state_path=str(state_path),
            state_preserved=keep_state,
            details=details,
        )
    except PqSmokeError:
        raise
    except ValidationError as exc:
        raise PqSmokeError("validation", str(exc)) from exc
    except Exception as exc:
        raise PqSmokeError("unexpected", str(exc)) from exc
    finally:
        if tempdir is not None:
            tempdir.cleanup()
        elif not keep_state and state_path is not None and state_path.exists():
            shutil.rmtree(state_path, ignore_errors=True)


def mine_easy_block(block: Block) -> Block:
    """Mine an easy local block deterministically for tests and smoke runs."""

    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise PqSmokeError("mining", "could not find a valid nonce for the local easy target")


def mine_next_block(service: NodeService, miner_address: str) -> Block:
    """Mine and apply the next local candidate block."""

    block = mine_easy_block(service.build_candidate_block(miner_address).block)
    service.apply_block(block)
    return block


def mine_to_height(service: NodeService, target_height: int, miner_address: str) -> None:
    """Mine local blocks until the active tip reaches target_height."""

    while (service.chain_tip().height if service.chain_tip() else -1) < target_height:
        mine_next_block(service, miner_address)


def call_api_json(app: HttpApiApp, *, method: str, path: str, body: object | None = None) -> tuple[str, Any]:
    """Call the real in-process WSGI API serialization path."""

    encoded = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "CONTENT_LENGTH": str(len(encoded)),
            "wsgi.input": io.BytesIO(encoded),
        }
    )
    captured: dict[str, Any] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    raw = b"".join(app(environ, start_response))
    payload = None if not raw else json.loads(raw.decode("utf-8"))
    return captured["status"], payload


def _assert_production_activation_unchanged() -> None:
    actual = pq_support_activation_height("testnet")
    if actual != TESTNET_PQ_ACTIVATION_HEIGHT:
        raise PqSmokeError(
            "configuration",
            f"production testnet PQ activation height changed unexpectedly: {actual}",
        )


def _make_service(database_path: Path, *, params) -> NodeService:
    timestamps = iter(range(1_900_000_000, 1_900_010_000))
    return NodeService.open_sqlite(
        database_path,
        network=PQ_SMOKE_NETWORK,
        params=params,
        time_provider=lambda: next(timestamps),
    )


def _legacy_wallet(index: int):
    private_keys = (
        "0000000000000000000000000000000000000000000000000000000000000001",
        "0000000000000000000000000000000000000000000000000000000000000002",
        "0000000000000000000000000000000000000000000000000000000000000003",
    )
    return wallet_key_from_private_key(bytes.fromhex(private_keys[index]))


def _legacy_payment(outpoint: OutPoint, *, value: int, sender, recipient: str, amount: int, fee: int) -> Transaction:
    return TransactionSigner(sender).build_signed_transaction(
        spend_candidates=[
            _spend_candidate(outpoint, value=value, recipient=sender.address),
        ],
        recipient=recipient,
        amount_chipbits=amount,
        fee_chipbits=fee,
        metadata={"kind": "payment", "purpose": "pq-smoke"},
        network=PQ_SMOKE_NETWORK,
    ).transaction


def _pq_payment(outpoint: OutPoint, *, owner, value: int, recipient: str, amount: int, fee: int) -> Transaction:
    return TransactionSigner(owner).build_signed_transaction(
        spend_candidates=[
            _spend_candidate(outpoint, value=value, recipient=owner.address),
        ],
        recipient=recipient,
        amount_chipbits=amount,
        fee_chipbits=fee,
        metadata={"kind": "payment", "purpose": "pq-smoke"},
        network=PQ_SMOKE_NETWORK,
    ).transaction


def _spend_candidate(outpoint: OutPoint, *, value: int, recipient: str):
    from ..wallet.models import SpendCandidate

    return SpendCandidate(txid=outpoint.txid, index=outpoint.index, amount_chipbits=value, recipient=recipient)


def _expect_rejection(stage: str, callable_, expected_message: str) -> None:
    try:
        callable_()
    except ValidationError as exc:
        if expected_message not in str(exc):
            raise PqSmokeError(stage, f"unexpected validation error: {exc}") from exc
        return
    raise PqSmokeError(stage, "transaction was accepted unexpectedly")


def _validate_api_metadata(app: HttpApiApp, *, chc_to_chcq: Transaction, chcq_to_chc: Transaction, pq_address: str) -> None:
    tx_status, tx_body = call_api_json(app, method="GET", path=f"/v1/tx/{chcq_to_chc.txid()}")
    if tx_status != "200 OK":
        raise PqSmokeError("API metadata OK", f"CHCQ spend lookup failed with {tx_status}")
    input_meta = tx_body["transaction"]["inputs"][0]
    if input_meta.get("sig_scheme_id") != SIG_SCHEME_ML_DSA_44 or input_meta.get("sig_scheme_name") != "mldsa44":
        raise PqSmokeError("API metadata OK", "CHCQ spend input metadata is missing ML-DSA-44 scheme")

    output_status, output_body = call_api_json(app, method="GET", path=f"/v1/tx/{chc_to_chcq.txid()}")
    if output_status != "200 OK":
        raise PqSmokeError("API metadata OK", f"CHC -> CHCQ lookup failed with {output_status}")
    output_meta = output_body["transaction"]["outputs"][0]
    if output_meta.get("address_kind") != "pq" or output_meta.get("address_scheme_id") != SIG_SCHEME_ML_DSA_44:
        raise PqSmokeError("API metadata OK", "CHCQ output metadata is missing PQ scheme")

    address_status, address_body = call_api_json(app, method="GET", path=f"/v1/address/{pq_address}")
    if address_status != "200 OK":
        raise PqSmokeError("API metadata OK", f"CHCQ address lookup failed with {address_status}")
    if address_body.get("address_kind") != "pq" or address_body.get("address_scheme_id") != SIG_SCHEME_ML_DSA_44:
        raise PqSmokeError("API metadata OK", "CHCQ address metadata is missing PQ scheme")
