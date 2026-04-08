"""HTTP client for the node mining API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request


class MiningApiError(Exception):
    """Raised when one mining endpoint cannot serve a valid response."""


@dataclass(frozen=True)
class MiningNodeClient:
    """Minimal JSON-over-HTTP client for template mining endpoints."""

    base_url: str
    timeout_seconds: float

    def status(self) -> dict[str, object]:
        """Fetch one miner-facing node status snapshot."""

        return self._request("GET", "/mining/status")

    def get_block_template(
        self,
        *,
        payout_address: str,
        miner_id: str,
        template_mode: str = "full_block",
    ) -> dict[str, object]:
        """Fetch one fresh mining template from the node."""

        return self._request(
            "POST",
            "/mining/get-block-template",
            {
                "payout_address": payout_address,
                "miner_id": miner_id,
                "template_mode": template_mode,
            },
        )

    def submit_block(
        self,
        *,
        template_id: str,
        serialized_block: str,
        miner_id: str,
    ) -> dict[str, object]:
        """Submit one solved block candidate back to the node."""

        return self._request(
            "POST",
            "/mining/submit-block",
            {
                "template_id": template_id,
                "serialized_block": serialized_block,
                "miner_id": miner_id,
            },
        )

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        url = f"{self.base_url.rstrip('/')}{path}"
        req = request.Request(url, method=method, data=body, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise MiningApiError(f"{method} {path} failed with HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise MiningApiError(f"{method} {path} failed: {exc.reason}") from exc
        decoded = {} if not raw else json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise MiningApiError(f"{method} {path} returned a non-object JSON payload")
        return decoded

