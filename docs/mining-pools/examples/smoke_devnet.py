"""Mine and submit one block to the isolated handbook Devnet node.

This intentionally uses only a public test payout address. Never run on Mainnet.
"""

from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from chipcoin.consensus.merkle import merkle_root
from chipcoin.consensus.models import Block, BlockHeader, Transaction, TxOutput
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.consensus.serialization import deserialize_transaction, serialize_block


def request(base: str, path: str, body: dict | None = None) -> dict:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(base + path, data=encoded, headers={"Content-Type": "application/json"} if encoded else {})
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def main(base: str) -> None:
    fixture = Path("/pool-vectors.json")
    if not fixture.exists():
        fixture = Path(__file__).resolve().parents[1] / "test-vectors" / "v1.json"
    address = json.loads(fixture.read_text(encoding="utf-8"))["isolated_devnet_example"]["miner_address"]
    for attempt in range(20):
        try:
            status = request(base, "/v1/status")
            break
        except URLError:
            if attempt == 19:
                raise
            time.sleep(0.5)
    if status.get("network") != "devnet" or status.get("chain_id") != "chipcoin-devnet-1":
        raise SystemExit("Refusing to mine: expected isolated Devnet")
    template = request(base, "/mining/get-block-template", {
        "payout_address": address, "miner_id": "handbook-smoke", "template_mode": "full_block",
    })
    if template.get("network") != "devnet" or template.get("chain_id") != "chipcoin-devnet-1":
        raise SystemExit("Refusing mismatched template")
    coinbase = Transaction(
        version=template["coinbase_tx"]["version"], inputs=(),
        outputs=tuple(TxOutput(value=row["amount_chipbits"], recipient=row["recipient"])
                      for row in template["coinbase_tx"]["outputs"]),
        metadata={**template["coinbase_tx"]["metadata"], "extra_nonce": "handbook-smoke-1"},
    )
    transactions = [coinbase]
    for row in template["transactions"]:
        raw = bytes.fromhex(row["raw_hex"])
        tx, offset = deserialize_transaction(raw)
        if offset != len(raw) or tx.txid() != row["txid"]:
            raise SystemExit("Template transaction does not match its bytes")
        transactions.append(tx)
    header = BlockHeader(
        version=template["version"], previous_block_hash=template["previous_block_hash"],
        merkle_root=merkle_root([tx.txid() for tx in transactions]),
        timestamp=template["curtime"], bits=template["bits"], nonce=0,
    )
    for nonce in range(2_000_000):
        candidate = replace(header, nonce=nonce)
        if verify_proof_of_work(candidate):
            break
    else:
        raise SystemExit("No solution within the local test nonce budget")
    block = Block(header=candidate, transactions=tuple(transactions))
    raw_hex = serialize_block(block).hex()
    submitted = request(base, "/mining/submit-block", {"serialized_block": raw_hex})
    looked_up = request(base, "/v1/block?hash=" + block.block_hash())
    retry = request(base, "/mining/submit-block", {"serialized_block": raw_hex})
    if not (submitted.get("accepted") and looked_up.get("on_active_chain")
            and retry.get("reason") == "already_accepted"):
        raise SystemExit(json.dumps({"submission": submitted, "lookup": looked_up, "retry": retry}))
    print(json.dumps({"network": "devnet", "height": template["height"],
                      "block_hash": block.block_hash(), "submission": submitted["reason"],
                      "on_active_chain": looked_up["on_active_chain"], "retry": retry["reason"]}, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
