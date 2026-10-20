import json
import shutil
import subprocess
from pathlib import Path

from chipcoin.crypto.pq import SIG_SCHEME_ML_DSA_44
from chipcoin.crypto.pq.mldsa import (
    ML_DSA_44_PUBLIC_KEY_SIZE,
    ML_DSA_44_SIGNATURE_SIZE,
    derive_mldsa44_keypair,
    sign_mldsa44,
    verify_mldsa44,
)
from chipcoin.wallet.signer import wallet_key_from_mldsa44_seed


FIXTURE_PATH = Path("apps/browser-wallet/tests/fixtures/mldsa44-browser-vector-1.json")


def test_browser_mldsa44_fixture_matches_python_backend() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    seed = bytes.fromhex(fixture["seed_hex"])
    message = bytes.fromhex(fixture["message_hex"])
    private_key, public_key = derive_mldsa44_keypair(seed)
    signature = sign_mldsa44(seed, message)

    assert fixture["warning"].startswith("Test-only")
    assert fixture["test_only"] is True
    assert fixture["scheme_id"] == SIG_SCHEME_ML_DSA_44
    assert fixture["scheme_name"] == "mldsa44"
    assert fixture["address"] == wallet_key_from_mldsa44_seed(seed).address
    assert public_key.hex() == fixture["public_key_hex"]
    assert private_key.hex() == fixture["private_key_hex"]
    assert signature.hex() == fixture["signature_hex"]
    assert sign_mldsa44(seed, message) == signature
    assert len(public_key) == fixture["public_key_len"] == ML_DSA_44_PUBLIC_KEY_SIZE
    assert len(private_key) == fixture["private_key_len"] == 2560
    assert len(signature) == fixture["signature_len"] == ML_DSA_44_SIGNATURE_SIZE
    assert verify_mldsa44(public_key, message, signature) is True


def test_browser_mldsa44_signature_verifies_with_python_backend() -> None:
    if shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome"):
        browser_name = "chromium"
    elif shutil.which("firefox") or shutil.which("firefox-esr"):
        browser_name = "firefox"
    else:
        pytest.skip("A supported headless browser is required for ML-DSA interoperability.")
    result = subprocess.run(
        ["node", "scripts/run-mldsa44-browser-test.mjs", "--browser", browser_name],
        cwd=Path("apps/browser-wallet"),
        check=True,
        capture_output=True,
        text=True,
    )
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload = None
    decoder = json.JSONDecoder()
    for index, character in enumerate(result.stdout):
        if character != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(result.stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("browser") == browser_name:
            payload = candidate
    assert payload is not None, result.stdout
    public_key = bytes.fromhex(fixture["public_key_hex"])
    message = bytes.fromhex(fixture["message_hex"])
    signature = bytes.fromhex(fixture["signature_hex"])

    assert payload["ok"] is True
    assert payload["publicKeyMatches"] is True
    assert payload["signatureMatches"] is True
    assert payload["pythonSignatureVerifies"] is True
    assert verify_mldsa44(public_key, message, signature) is True
