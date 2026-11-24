"""Isolated mining API regressions; no production chain or wallet is used."""

from dataclasses import replace
from io import BytesIO
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, OutPoint, Transaction, TxOutput
from chipcoin.consensus.params import DEVNET_PARAMS, TESTNET_PARAMS
from chipcoin.consensus.params import MAINNET_PARAMS
from chipcoin.consensus.pq_activation import pq_support_activation_height
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.consensus.serialization import deserialize_transaction, serialize_block
from chipcoin.consensus.utxo import InMemoryUtxoView
from chipcoin.consensus.validation import ContextualValidationError, ValidationContext, _validate_transaction_outputs_for_activation
from chipcoin.crypto.addresses import public_key_to_pq_address
from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44, SIG_SCHEME_ML_DSA_65_RESERVED
from chipcoin.interfaces.http_api import HttpApiApp
from chipcoin.node.service import NodeService
from chipcoin.node.runtime import NodeRuntime
from chipcoin.wallet.signer import wallet_key_from_mldsa44_seed
import pytest
from tests.helpers import put_wallet_utxo, signed_payment, wallet_key


def _request(app, path, body):
    encoded = json.dumps(body).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(encoded)),
        "wsgi.input": BytesIO(encoded),
    }
    response = {}

    def start(status, _headers):
        response["status"] = status

    response["body"] = json.loads(b"".join(app(environ, start)).decode())
    return response


def _get_block_by_hash(app, block_hash):
    environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/v1/block", "QUERY_STRING": f"hash={block_hash}"}
    response = {}

    def start(status, _headers):
        response["status"] = status

    response["body"] = json.loads(b"".join(app(environ, start)).decode())
    return response


def _service(tmp_path, now):
    return NodeService.open_sqlite(
        tmp_path / "devnet.sqlite3",
        network="devnet",
        params=replace(DEVNET_PARAMS, genesis_bits=0x207FFFFF),
        time_provider=lambda: now[0],
    )


def _template(app):
    result = _request(app, "/mining/get-block-template", {
        "payout_address": wallet_key().address,
        "miner_id": "test-worker",
    })
    assert result["status"] == "200 OK"
    return result["body"]


def _solved_block(template, *, extra_nonce="1"):
    coinbase = Transaction(
        version=1,
        inputs=(),
        outputs=tuple(
            TxOutput(value=int(row["amount_chipbits"]), recipient=row["recipient"])
            for row in template["coinbase_tx"]["outputs"]
        ),
        metadata={"coinbase": "true", "height": str(template["height"]), "extra_nonce": extra_nonce},
    )
    transactions = [coinbase]
    for row in template["transactions"]:
        raw = bytes.fromhex(row["raw_hex"])
        transaction, offset = deserialize_transaction(raw)
        assert offset == len(raw)
        transactions.append(transaction)
    header = BlockHeader(
        version=template["version"],
        previous_block_hash=template["previous_block_hash"],
        merkle_root=merkle_root([tx.txid() for tx in transactions]),
        timestamp=template["curtime"],
        bits=template["bits"],
        nonce=0,
    )
    for nonce in range(10000):
        candidate = replace(header, nonce=nonce)
        if verify_proof_of_work(candidate):
            return Block(header=candidate, transactions=tuple(transactions))
    raise AssertionError("easy Devnet target did not produce a solution")


def _submit(app, block, template_id=None):
    body = {"serialized_block": serialize_block(block).hex()}
    if template_id is not None:
        body.update(template_id=template_id, miner_id="test-worker")
    return _request(app, "/mining/submit-block", body)


def _remine(block):
    for nonce in range(10000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("easy Devnet target did not produce a solution")


def test_full_block_survives_mempool_change_and_retry(tmp_path):
    now = [1_700_000_000]
    service = _service(tmp_path, now)
    app = HttpApiApp(service)
    template_a = _template(app)
    block_a = _solved_block(template_a)

    funding = OutPoint(txid="11" * 32, index=0)
    put_wallet_utxo(service, funding, value=100, owner=wallet_key())
    service.receive_transaction(signed_payment(funding, value=100, fee=10))
    template_b = _template(app)
    assert template_b["previous_block_hash"] == template_a["previous_block_hash"]
    assert template_b["transactions"] != template_a["transactions"]
    now[0] += 16

    first = _submit(app, block_a)
    assert first["status"] == "200 OK"
    assert first["body"]["reason"] == "accepted"
    assert first["body"]["block_hash"] == block_a.block_hash()
    retry = _submit(app, block_a)
    assert retry["body"]["reason"] == "already_accepted"
    assert retry["body"]["block_hash"] == block_a.block_hash()
    assert service.chain_tip().height == 0


def test_identical_new_template_id_can_submit_unchanged_old_block(tmp_path):
    now = [1_700_000_000]
    service = _service(tmp_path, now)
    app = HttpApiApp(service)
    template_a = _template(app)
    old_block = _solved_block(template_a)
    old_hash = old_block.block_hash()
    now[0] += 16
    assert _submit(app, old_block, template_a["template_id"])["body"]["reason"] == "unknown_or_expired_template"
    template_b = _template(app)
    for field in ("previous_block_hash", "bits", "coinbase_tx", "transactions"):
        assert template_b[field] == template_a[field]
    result = _submit(app, old_block, template_b["template_id"])["body"]
    assert result["reason"] == "accepted"
    assert result["block_hash"] == old_hash
    assert old_block.block_hash() == old_hash


def test_concurrent_identical_full_submissions_are_idempotent(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    app = HttpApiApp(service)
    block = _solved_block(_template(app))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _submit(app, block)["body"], range(4)))
    assert sorted(result["reason"] for result in results) == [
        "accepted", "already_accepted", "already_accepted", "already_accepted",
    ]
    assert all(result["block_hash"] == block.block_hash() for result in results)
    assert service.chain_tip().height == 0


def test_legacy_template_survives_mempool_change_but_expires(tmp_path):
    now = [1_700_000_000]
    service = _service(tmp_path, now)
    app = HttpApiApp(service)
    template_a = _template(app)
    block_a = _solved_block(template_a)
    funding = OutPoint(txid="22" * 32, index=0)
    put_wallet_utxo(service, funding, value=100, owner=wallet_key())
    service.receive_transaction(signed_payment(funding, value=100, fee=10))
    template_b = _template(app)
    assert template_b["transactions"] != template_a["transactions"]
    mismatched = _submit(app, block_a, template_b["template_id"])
    assert mismatched["body"]["reason"] in {"transaction_set_mismatch", "coinbase_outputs_mismatch"}
    result = _submit(app, block_a, template_a["template_id"])
    assert result["body"]["reason"] == "accepted"

    # The administrative TTL still bounds legacy reconstruction.
    next_template = _template(app)
    now[0] += 16
    expired = _submit(app, _solved_block(next_template), next_template["template_id"])
    assert expired["body"]["reason"] == "unknown_or_expired_template"


def test_full_block_rejects_bad_pow_without_advancing_tip(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    app = HttpApiApp(service)
    block = _solved_block(_template(app))
    bad_nonce = next(
        nonce for nonce in range(10000)
        if not verify_proof_of_work(replace(block.header, nonce=nonce))
    )
    invalid = replace(block, header=replace(block.header, nonce=bad_nonce))
    result = _submit(app, invalid)
    assert result["body"]["accepted"] is False
    assert result["body"]["reason"].startswith("validation_error:")
    assert service.chain_tip() is None


def test_full_block_rejects_merkle_bits_and_coinbase_violations(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    app = HttpApiApp(service)
    block = _solved_block(_template(app))
    wrong_merkle = _remine(replace(block, header=replace(block.header, merkle_root="ab" * 32)))
    wrong_bits = _remine(replace(block, header=replace(block.header, bits=0x207FFFFE)))
    bad_coinbase = replace(block.transactions[0], outputs=(
        replace(block.transactions[0].outputs[0], value=block.transactions[0].outputs[0].value + 1),
    ))
    bad_transactions = (bad_coinbase, *block.transactions[1:])
    wrong_reward = _remine(replace(
        block,
        transactions=bad_transactions,
        header=replace(block.header, merkle_root=merkle_root([tx.txid() for tx in bad_transactions])),
    ))
    for invalid in (wrong_merkle, wrong_bits, wrong_reward):
        result = _submit(app, invalid)["body"]
        assert result["accepted"] is False
        assert result["stored"] is False
        assert result["consensus_validity"] == "invalid"
    assert service.chain_tip() is None


def test_legacy_template_cache_is_bounded(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    service.MAX_MINING_TEMPLATES = 4
    ids = [service.get_block_template(payout_address=wallet_key().address, miner_id="test-worker")["template_id"] for _ in range(6)]
    assert len(service._mining_templates) == 4
    assert ids[:2] not in [*service._mining_templates]


def test_legacy_jobs_stay_available_for_256_same_tip_requests(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    first = service.get_block_template(payout_address=wallet_key().address, miner_id="test-worker")
    for _ in range(255):
        service.get_block_template(payout_address=wallet_key().address, miner_id="test-worker")
    assert len(service._mining_templates) == 256
    block = _solved_block(first)
    assert service.prepare_mined_block_submission(
        template_id=first["template_id"], serialized_block_hex=serialize_block(block).hex(),
        miner_id="test-worker",
    )["accepted"] is True


def test_receive_block_must_report_storage_before_api_claims_it(tmp_path):
    from types import SimpleNamespace
    from chipcoin.node.sync import BlockIngestResult

    service = _service(tmp_path, [1_700_000_000])
    app = HttpApiApp(service)
    template = _template(app)
    first = _solved_block(template)
    side = _solved_block(template, extra_nonce="side")
    assert _submit(app, first)["body"]["accepted"] is True

    class FailedManager:
        def ingest_headers(self, _headers):
            return SimpleNamespace(parent_unknown=None)

        def receive_block(self, block):
            return BlockIngestResult(block_hash=block.block_hash(), activated_tip=first.block_hash(),
                                     reorged=False, parent_unknown="ee" * 32, accepted_blocks=0)

    result = service.accept_full_block(side, sync_manager=FailedManager())
    assert result["stored"] is False
    assert result["accepted"] is False
    assert result["reason"] == "unknown_parent"


def test_side_branch_storage_then_reorganization_and_retry(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    app = HttpApiApp(service)
    template = _template(app)
    a = _solved_block(template, extra_nonce="a")
    b = _solved_block(template, extra_nonce="b")
    assert a.block_hash() != b.block_hash()
    assert _submit(app, a)["body"]["on_active_chain"] is True

    side = _submit(app, b)["body"]
    assert side == {
        "accepted": False,
        "reason": "stored_side_branch",
        "block_hash": b.block_hash(),
        "became_tip": False,
        "stored": True,
        "on_active_chain": False,
        "consensus_validity": "pending",
    }
    assert _submit(app, b)["body"]["reason"] == "known_side_branch"
    side_lookup = _get_block_by_hash(app, b.block_hash())
    assert side_lookup["status"] == "200 OK"
    assert side_lookup["body"]["on_active_chain"] is False
    assert _get_block_by_hash(app, a.block_hash())["body"]["on_active_chain"] is True

    next_template = _template(app)
    candidate = _solved_block(next_template)
    header = replace(candidate.header, previous_block_hash=b.block_hash())
    child = None
    for nonce in range(10000):
        solved_header = replace(header, nonce=nonce)
        if verify_proof_of_work(solved_header):
            child = replace(candidate, header=solved_header)
            break
    assert child is not None
    result = _submit(app, child)["body"]
    assert result["on_active_chain"] is True
    assert result["became_tip"] is True
    assert service.chain_tip().block_hash == child.block_hash()
    assert _submit(app, b)["body"]["reason"] == "already_accepted"
    assert _submit(app, a)["body"]["reason"] == "known_side_branch"
    assert _get_block_by_hash(app, b.block_hash())["body"]["on_active_chain"] is True
    assert _get_block_by_hash(app, a.block_hash())["body"]["on_active_chain"] is False


@pytest.mark.parametrize("network,params", [("devnet", DEVNET_PARAMS), ("testnet", TESTNET_PARAMS)])
def test_template_rejects_chcq_before_activation_and_accepts_at_boundary(tmp_path, network, params):
    now = [1_700_000_000]
    service = NodeService.open_sqlite(
        tmp_path / f"{network}-activation.sqlite3", network=network,
        params=replace(params, genesis_bits=0x207FFFFF, pq_support_activation_height=1),
        time_provider=lambda: now[0],
    )
    app = HttpApiApp(service)
    pq_address = wallet_key_from_mldsa44_seed(bytes(range(32))).address
    rejected = _request(app, "/mining/get-block-template", {
        "payout_address": pq_address, "miner_id": "test-worker",
    })
    assert rejected["status"] == "400 Bad Request"
    assert "CHCQ payout addresses are not active" in rejected["body"]["error"]["message"]
    assert service._mining_templates == {}

    legacy = _template(app)
    assert _submit(app, _solved_block(legacy))["body"]["reason"] == "accepted"
    accepted = _request(app, "/mining/get-block-template", {
        "payout_address": pq_address, "miner_id": "test-worker",
    })
    assert accepted["status"] == "200 OK"
    assert accepted["body"]["height"] == 1


def test_http_error_after_commit_is_reconciled_by_retry(tmp_path):
    service = _service(tmp_path, [1_700_000_000])
    block = _solved_block(_template(HttpApiApp(service)))
    calls = [0]

    def handler(**kwargs):
        result = service.submit_mined_block(**kwargs)
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("simulated HTTP response failure after commit")
        return result

    app = HttpApiApp(service, mining_submit_handler=handler)
    first = _submit(app, block)
    assert first["status"].startswith("500")
    assert service.get_block_by_hash(block.block_hash()) is not None
    second = _submit(app, block)
    assert second["body"]["reason"] == "already_accepted"
    assert service.chain_tip().height == 0


def test_runtime_reports_committed_block_when_relay_fails(tmp_path, monkeypatch):
    service = _service(tmp_path, [1_700_000_000])
    block = _solved_block(_template(HttpApiApp(service)))
    runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=0)
    broadcasts = [0]

    async def failed_broadcast(_item):
        broadcasts[0] += 1
        raise OSError("simulated relay failure after commit")

    monkeypatch.setattr(runtime, "_broadcast_inventory", failed_broadcast)
    kwargs = {"template_id": None, "serialized_block_hex": serialize_block(block).hex(), "miner_id": ""}
    first = asyncio.run(runtime._submit_mined_block_from_http(**kwargs))
    assert first["reason"] == "accepted"
    assert first["relay_failed"] is True
    assert first["consensus_validity"] == "validated"
    assert first["on_active_chain"] is True
    retry = asyncio.run(runtime._submit_mined_block_from_http(**kwargs))
    assert retry["reason"] == "already_accepted"
    assert broadcasts == [1]


def test_runtime_refreshes_active_chain_status_after_concurrent_reorg(tmp_path, monkeypatch):
    service = _service(tmp_path, [1_700_000_000])
    template = _template(HttpApiApp(service))
    a = _solved_block(template, extra_nonce="a")
    b = _solved_block(template, extra_nonce="b")
    runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=0)

    async def competing_chain(_item):
        assert service.accept_full_block(b)["reason"] == "stored_side_branch"
        child = _solved_block(_template(HttpApiApp(service)))
        child = _remine(replace(child, header=replace(child.header, previous_block_hash=b.block_hash())))
        assert service.accept_full_block(child)["on_active_chain"] is True

    monkeypatch.setattr(runtime, "_broadcast_inventory", competing_chain)
    result = asyncio.run(runtime._submit_mined_block_from_http(
        template_id=None, serialized_block_hex=serialize_block(a).hex(), miner_id="",
    ))
    assert result["stored"] is True
    assert result["on_active_chain"] is False
    assert result["consensus_validity"] == "pending"
    assert result["reason"] == "known_side_branch"


def test_runtime_relays_stored_side_branch_like_existing_p2p_path(tmp_path, monkeypatch):
    service = _service(tmp_path, [1_700_000_000])
    template = _template(HttpApiApp(service))
    a = _solved_block(template, extra_nonce="a")
    b = _solved_block(template, extra_nonce="b")
    assert service.accept_full_block(a)["on_active_chain"] is True
    runtime = NodeRuntime(service=service, listen_host="127.0.0.1", listen_port=0)
    announced = []

    async def collect_inventory(item):
        announced.append(item.object_hash)

    monkeypatch.setattr(runtime, "_broadcast_inventory", collect_inventory)
    result = asyncio.run(runtime._submit_mined_block_from_http(
        template_id=None, serialized_block_hex=serialize_block(b).hex(), miner_id="",
    ))
    assert result["reason"] == "stored_side_branch"
    assert result["consensus_validity"] == "pending"
    assert announced == [b.block_hash()]


def test_pq_policy_is_network_specific_without_changing_pow():
    assert pq_support_activation_height("mainnet") == 0
    assert pq_support_activation_height("testnet") == 20_000
    assert pq_support_activation_height("devnet") == 30_000
    pq_address = wallet_key_from_mldsa44_seed(bytes(range(32))).address
    legacy_output = Transaction(version=1, inputs=(), outputs=(TxOutput(1, wallet_key().address),))
    pq_output = replace(legacy_output, outputs=(TxOutput(1, pq_address),))
    mainnet = ValidationContext(height=1, median_time_past=0, params=MAINNET_PARAMS,
                                utxo_view=InMemoryUtxoView(), network="mainnet")
    devnet = ValidationContext(height=1, median_time_past=0, params=DEVNET_PARAMS,
                               utxo_view=InMemoryUtxoView(), network="devnet")
    with pytest.raises(ContextualValidationError):
        _validate_transaction_outputs_for_activation(legacy_output, mainnet)
    _validate_transaction_outputs_for_activation(pq_output, mainnet)
    _validate_transaction_outputs_for_activation(legacy_output, devnet)
    with pytest.raises(ContextualValidationError):
        _validate_transaction_outputs_for_activation(pq_output, devnet)


def test_mainnet_template_rejects_chcq_scheme_rejected_by_consensus(tmp_path):
    service = NodeService.open_sqlite(tmp_path / "mainnet-scheme.sqlite3", network="mainnet")
    app = HttpApiApp(service)
    public_key = bytes([42]) * 1312  # Synthetic public bytes; no private key or signing.
    reserved_address = public_key_to_pq_address(public_key, scheme_id=SIG_SCHEME_ML_DSA_65_RESERVED)
    valid_address = public_key_to_pq_address(public_key, scheme_id=SIG_SCHEME_ML_DSA_44)
    context = ValidationContext(height=1, median_time_past=0, params=MAINNET_PARAMS,
                                utxo_view=InMemoryUtxoView(), network="mainnet")
    forbidden_output = Transaction(version=1, inputs=(), outputs=(TxOutput(1, reserved_address),))
    with pytest.raises(ContextualValidationError, match="must use ML-DSA-44 CHCQ"):
        _validate_transaction_outputs_for_activation(forbidden_output, context)
    with pytest.raises(ValueError, match="ML-DSA-44 CHCQ"):
        service.build_candidate_block(reserved_address)

    rejected = _request(app, "/mining/get-block-template", {
        "payout_address": reserved_address, "miner_id": "test-worker",
    })
    assert rejected["status"] == "400 Bad Request"
    assert rejected["body"]["error"]["code"] == "invalid_request"
    assert "ML-DSA-44 CHCQ" in rejected["body"]["error"]["message"]
    assert service._mining_templates == {}
    accepted = _request(app, "/mining/get-block-template", {
        "payout_address": valid_address, "miner_id": "test-worker",
    })
    assert accepted["status"] == "200 OK"
    assert accepted["body"]["network"] == "mainnet"
    service.connection.close()

    devnet = NodeService.open_sqlite(
        tmp_path / "devnet-scheme.sqlite3", network="devnet",
        params=replace(DEVNET_PARAMS, pq_support_activation_height=0),
    )
    devnet_context = ValidationContext(height=0, median_time_past=0, params=devnet.params,
                                       utxo_view=InMemoryUtxoView(), network="devnet")
    _validate_transaction_outputs_for_activation(forbidden_output, devnet_context)
    devnet_result = _request(HttpApiApp(devnet), "/mining/get-block-template", {
        "payout_address": reserved_address, "miner_id": "test-worker",
    })
    assert devnet_result["status"] == "200 OK"
    devnet.connection.close()
