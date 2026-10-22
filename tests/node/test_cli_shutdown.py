import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


def test_run_command_handles_sigterm_and_closes_runtime_cleanly(tmp_path: Path) -> None:
    repository = Path(__file__).parents[2]
    database = tmp_path / "node.sqlite3"
    script = f"""
import asyncio
from chipcoin.interfaces import cli

class FakeRuntime:
    def __init__(self, **kwargs):
        self._outbound_target_sources = {{}}
        self.stop_requested = asyncio.Event()

    async def start(self):
        print('runtime started network=devnet', flush=True)

    async def run_forever(self):
        await self.stop_requested.wait()

    async def stop(self):
        print('runtime stopping network=devnet', flush=True)
        self.stop_requested.set()
        print('runtime stopped network=devnet', flush=True)

cli.NodeRuntime = FakeRuntime
raise SystemExit(cli.main([
    '--data', {str(database)!r}, '--network', 'devnet', 'run',
    '--peer-discovery-enabled', 'false'
]))
"""
    environment = os.environ.copy()
    source_path = str(repository / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_path, environment.get("PYTHONPATH", "")) if item
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=repository,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    output: list[str] = []
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            for key, _ in selector.select(timeout=0.1):
                line = key.fileobj.readline()
                if line:
                    output.append(line)
                    if "runtime started network=devnet" in line:
                        break
            if any("runtime started network=devnet" in line for line in output):
                break
            if process.poll() is not None:
                break
        assert any("runtime started network=devnet" in line for line in output), "runtime did not start"
        process.send_signal(signal.SIGTERM)
        remainder, _ = process.communicate(timeout=12)
        output.append(remainder)
        assert process.returncode == 0
        assert any("runtime stopping network=devnet" in line for line in output)
        assert any("runtime stopped network=devnet" in line for line in output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
