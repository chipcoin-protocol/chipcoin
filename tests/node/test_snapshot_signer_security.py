from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from chipcoin.consensus.models import Block
from chipcoin.consensus.pow import verify_proof_of_work
from chipcoin.node.service import NodeService


def _mine_block(block: Block) -> Block:
    for nonce in range(2_000_000):
        header = replace(block.header, nonce=nonce)
        if verify_proof_of_work(header):
            return replace(block, header=header)
    raise AssertionError("Expected to find a valid nonce for the easy target.")


def test_snapshot_signer_private_key_canary_does_not_leak() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        source_db = root / "source.sqlite3"
        snapshot_path = root / "chain.snapshot"
        key_path = root / "snapshot-signing.key"
        command_evidence_path = root / "command-evidence.json"
        canary = "c1" * 32

        source = NodeService.open_sqlite(source_db, network="devnet")
        source.apply_block(_mine_block(source.build_candidate_block("CHCminer").block))
        source.export_snapshot_file(snapshot_path)
        source.connection.close()
        key_path.write_text(canary + "\n", encoding="ascii")
        key_path.chmod(0o600)

        child_code = (
            "import sys,time; time.sleep(1); "
            "from chipcoin.interfaces.cli import main; "
            "raise SystemExit(main(sys.argv[1:]))"
        )
        command = [
            sys.executable,
            "-c",
            child_code,
            "snapshot-sign",
            "--snapshot-file",
            str(snapshot_path),
            "--private-key-file",
            str(key_path),
        ]
        command_evidence_path.write_text(json.dumps(command), encoding="utf-8")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
        try:
            deadline = time.monotonic() + 0.8
            while not Path(f"/proc/{process.pid}/cmdline").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            cmdline = Path(f"/proc/{process.pid}/cmdline").read_bytes()
            environ = Path(f"/proc/{process.pid}/environ").read_bytes()
            assert canary.encode("ascii") not in cmdline
            assert canary.encode("ascii") not in environ
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

        assert process.returncode == 0
        assert canary.encode("ascii") not in stdout
        assert canary.encode("ascii") not in stderr
        signed_payload = snapshot_path.read_bytes()
        assert canary.encode("ascii") not in signed_payload

        for path in root.rglob("*"):
            if not path.is_file() or path == key_path:
                continue
            assert canary.encode("ascii") not in path.read_bytes(), path

        repository_diff = subprocess.run(
            ["git", "diff", "--no-ext-diff"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert canary.encode("ascii") not in repository_diff.stdout
        assert canary.encode("ascii") not in repository_diff.stderr


def test_snapshot_publisher_never_passes_private_key_material_in_argv() -> None:
    script = Path("scripts/ops/build-testnet-snapshot.sh").read_text(encoding="utf-8")

    assert "--private-key-hex" not in script
    assert '--private-key-file "$SNAPSHOT_SIGNING_KEY_FILE"' in script
    assert "$(tr" not in script


def test_snapshot_signer_produces_deterministic_output_for_identical_input() -> None:
    with TemporaryDirectory() as tempdir:
        root = Path(tempdir)
        source_db = root / "source.sqlite3"
        snapshot_a = root / "snapshot-a.bin"
        snapshot_b = root / "snapshot-b.bin"
        key_path = root / "snapshot-signing.key"
        source = NodeService.open_sqlite(source_db, network="devnet")
        source.apply_block(_mine_block(source.build_candidate_block("CHCminer").block))
        source.export_snapshot_file(snapshot_a)
        source.connection.close()
        shutil.copyfile(snapshot_a, snapshot_b)
        key_path.write_text(("d2" * 32) + "\n", encoding="ascii")
        key_path.chmod(0o600)

        child_code = "import sys; from chipcoin.interfaces.cli import main; raise SystemExit(main(sys.argv[1:]))"
        for snapshot_path in (snapshot_a, snapshot_b):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    child_code,
                    "snapshot-sign",
                    "--snapshot-file",
                    str(snapshot_path),
                    "--private-key-file",
                    str(key_path),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")

        assert snapshot_a.read_bytes() == snapshot_b.read_bytes()
