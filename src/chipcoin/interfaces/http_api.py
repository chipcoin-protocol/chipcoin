"""Optional HTTP API for local diagnostics and control."""

from __future__ import annotations

import argparse
import json
import logging
import os
from socketserver import ThreadingMixIn
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIServer, make_server

from ..consensus.validation import ValidationError
from ..crypto.addresses import is_valid_address
from ..node.service import NodeService
from ..utils.logging import configure_logging
from .presenters import format_tip, format_transaction_lookup


class ApiError(Exception):
    """Structured HTTP API error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Minimal threaded WSGI server so slow requests do not block the whole API."""

    daemon_threads = True


class HttpApiApp:
    """WSGI app exposing a small JSON API over the local node service."""

    API_VERSION = "v1"
    ADDRESS_HISTORY_DEFAULT_LIMIT = 50
    ADDRESS_HISTORY_MAX_LIMIT = 100
    MEMPOOL_DEFAULT_LIMIT = 100
    MEMPOOL_MAX_LIMIT = 1_000
    PEERS_DEFAULT_LIMIT = 200
    PEERS_MAX_LIMIT = 1_000
    MAX_DIAGNOSTIC_OFFSET = 100_000
    DEFAULT_JSON_BODY_MAX_BYTES = 1_000_000
    MINING_TEMPLATE_JSON_BODY_MAX_BYTES = 16_384
    TX_SUBMIT_JSON_BODY_MAX_BYTES = 262_144
    TX_SUBMIT_RAW_HEX_MAX_CHARS = 200_000
    BLOCK_SUBMIT_JSON_BODY_MAX_BYTES = 17_000_000
    BLOCK_SUBMIT_RAW_HEX_MAX_CHARS = 16_000_000

    def __init__(
        self,
        service: NodeService,
        *,
        allowed_origins: set[str] | None = None,
        mining_submit_handler=None,
        tx_submit_handler=None,
        status_cache_ttl_seconds: float | None = None,
    ) -> None:
        self.service = service
        self.allowed_origins = set() if allowed_origins is None else {origin for origin in allowed_origins if origin}
        self.logger = logging.getLogger("chipcoin.http_api")
        self._request_lock = threading.RLock()
        self.status_cache_ttl_seconds = (
            _status_cache_ttl_from_env() if status_cache_ttl_seconds is None else max(0.0, status_cache_ttl_seconds)
        )
        self._status_cache_lock = threading.RLock()
        self._status_cache_payload: dict[str, object] | None = None
        self._status_cache_expires_at = 0.0
        self.mining_submit_handler = mining_submit_handler
        self.tx_submit_handler = tx_submit_handler

    def __call__(self, environ, start_response):
        method = environ["REQUEST_METHOD"].upper()
        path = environ.get("PATH_INFO", "")
        query_string = environ.get("QUERY_STRING", "")
        origin = environ.get("HTTP_ORIGIN")
        started_at = time.perf_counter()
        status_code = 500

        def start_response_with_status(status: str, headers: list[tuple[str, str]], exc_info=None):
            nonlocal status_code
            status_code = int(status.split(" ", 1)[0])
            if exc_info is None:
                return start_response(status, headers)
            return start_response(status, headers, exc_info)

        try:
            if method == "OPTIONS" and (path.startswith("/v1/") or path.startswith("/mining/")):
                return self._options_response(start_response_with_status, origin)
            cached_status = self._cached_status_payload(method=method, path=path)
            if cached_status is not None:
                return self._json_response(start_response_with_status, 200, cached_status, origin=origin)
            with self._request_lock:
                payload = self._dispatch(method=method, path=path, environ=environ)
            return self._json_response(start_response_with_status, 200, payload, origin=origin)
        except ApiError as exc:
            return self._json_response(
                start_response_with_status,
                exc.status_code,
                {"error": {"code": exc.code, "message": exc.message}},
                origin=origin,
            )
        except Exception:
            return self._json_response(
                start_response_with_status,
                500,
                {"error": {"code": "internal_error", "message": "unexpected server error"}},
                origin=origin,
            )
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            target = path if not query_string else f"{path}?{query_string}"
            self._log_request(method=method, target=target, status_code=status_code, duration_ms=duration_ms)

    def _log_request(self, *, method: str, target: str, status_code: int, duration_ms: float) -> None:
        """Log high-frequency polling endpoints at debug unless they fail."""

        log = self.logger.debug if status_code < 400 and target == "/mining/status" else self.logger.info
        log("request method=%s path=%s status=%s duration_ms=%.2f", method, target, status_code, duration_ms)

    def _dispatch(self, *, method: str, path: str, environ) -> object:
        if method == "GET" and path == "/v1/health":
            return {"status": "ok", "api_version": self.API_VERSION, "network": self.service.network}

        if method == "GET" and path == "/v1/status":
            return self._fresh_status_payload()

        if method == "GET" and path == "/v1/supply":
            return {"api_version": self.API_VERSION, **self.service.supply_snapshot()}

        if method == "GET" and path == "/v1/rewards/epoch":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_optional_int(query, "epoch_index")
            node_id = self._parse_optional_text(query, "node_id")
            return {"api_version": self.API_VERSION, **self.service.native_reward_epoch_state(epoch_index=epoch_index, node_id=node_id)}

        if method == "GET" and path == "/v1/rewards/assignments":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_optional_int(query, "epoch_index")
            node_id = self._parse_optional_text(query, "node_id")
            return {
                "api_version": self.API_VERSION,
                "epoch_index": epoch_index,
                "node_id": node_id,
                "assignments": self.service.native_reward_assignments(epoch_index=epoch_index, node_id=node_id),
            }

        if method == "GET" and path == "/v1/rewards/node-status":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            node_id = self._parse_required_text(query, "node_id")
            epoch_index = self._parse_optional_int(query, "epoch_index", minimum=0)
            try:
                return {"api_version": self.API_VERSION, **self.service.reward_node_status(node_id=node_id, epoch_index=epoch_index)}
            except ValueError as exc:
                raise ApiError(404, "not_found", str(exc)) from exc

        if method == "GET" and path == "/v1/rewards/node-fees":
            return {"api_version": self.API_VERSION, **self.service.reward_node_fee_schedule()}

        if method == "GET" and path == "/v1/rewards/epoch-summary":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_required_int(query, "epoch_index", minimum=0)
            return {"api_version": self.API_VERSION, **self.service.reward_epoch_summary(epoch_index=epoch_index)}

        if method == "GET" and path == "/v1/rewards/attestations":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_optional_int(query, "epoch_index")
            return {
                "api_version": self.API_VERSION,
                "epoch_index": epoch_index,
                "attestations": self.service.native_reward_attestation_diagnostics(epoch_index=epoch_index),
            }

        if method == "GET" and path == "/v1/rewards/attestation-backlog":
            return {"api_version": self.API_VERSION, **self.service.reward_attestation_backlog_report()}

        if method == "GET" and path == "/v1/rewards/settlements":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_optional_int(query, "epoch_index")
            return {
                "api_version": self.API_VERSION,
                "epoch_index": epoch_index,
                "settlements": self.service.native_reward_settlement_diagnostics(epoch_index=epoch_index),
            }

        if method == "GET" and path == "/v1/rewards/settlement-report":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            epoch_index = self._parse_optional_int(query, "epoch_index")
            return {"api_version": self.API_VERSION, **self.service.native_reward_settlement_report(epoch_index=epoch_index)}

        if method == "GET" and path == "/mining/status":
            return self.service.mining_status()

        if method == "POST" and path == "/mining/get-block-template":
            return self._handle_get_block_template(environ)

        if method == "POST" and path == "/mining/submit-block":
            return self._handle_submit_block(environ)

        if method == "GET" and path == "/v1/tip":
            return format_tip(self.service.chain_tip())

        if method == "GET" and path == "/v1/blocks":
            return self._handle_blocks(environ)

        if method == "GET" and path == "/v1/block":
            return self._handle_block(environ)

        if method == "GET" and path.startswith("/v1/tx/"):
            txid = path.removeprefix("/v1/tx/").strip()
            if not txid:
                raise ApiError(404, "not_found", "transaction not found")
            result = self.service.find_transaction(txid)
            if result is None:
                raise ApiError(404, "not_found", "transaction not found")
            return format_transaction_lookup(result)

        if method == "POST" and path == "/v1/tx/submit":
            return self._handle_submit_tx(environ)

        if method == "GET" and path == "/v1/mempool":
            return self._handle_mempool(environ)

        if method == "GET" and path == "/v1/peers":
            return self._handle_peers(environ)

        if method == "GET" and path == "/v1/peers/summary":
            return self.service.peer_summary()

        if method == "GET" and path == "/v1/peers/public":
            return self.service.public_peers()

        if method == "GET" and path.startswith("/v1/address/"):
            return self._handle_address(method=method, path=path, environ=environ)

        raise ApiError(404, "not_found", "not found")

    def _cached_status_payload(self, *, method: str, path: str) -> dict[str, object] | None:
        if method != "GET" or path != "/v1/status" or self.status_cache_ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._status_cache_lock:
            if self._status_cache_payload is None or now >= self._status_cache_expires_at:
                return None
            return dict(self._status_cache_payload)

    def _fresh_status_payload(self) -> dict[str, object]:
        payload = {"api_version": self.API_VERSION, **self.service.status(include_supply=False)}
        if self.status_cache_ttl_seconds > 0:
            with self._status_cache_lock:
                self._status_cache_payload = dict(payload)
                self._status_cache_expires_at = time.monotonic() + self.status_cache_ttl_seconds
        return payload

    def _handle_blocks(self, environ) -> list[dict[str, object]]:
        query = parse_qs(environ.get("QUERY_STRING", ""))
        limit = self._parse_optional_int(query, "limit", minimum=1, maximum=100, default=20)
        tip = self.service.chain_tip()
        if tip is None:
            if "from_height" in query:
                requested = self._parse_optional_int(query, "from_height", minimum=0)
                if requested is not None and requested != 0:
                    raise ApiError(400, "invalid_request", "from_height is above the current tip height")
            return []

        from_height = self._parse_optional_int(query, "from_height", minimum=0, default=tip.height)
        assert from_height is not None
        if from_height > tip.height:
            raise ApiError(400, "invalid_request", "from_height is above the current tip height")
        start_height = max(0, from_height - limit + 1)
        rows = self.service.chain_window(start_height, from_height)
        rows.reverse()
        return rows

    def _parse_optional_text(self, query: dict[str, list[str]], name: str) -> str | None:
        values = query.get(name, [])
        if not values:
            return None
        value = values[-1].strip()
        return None if not value else value

    def _parse_required_text(self, query: dict[str, list[str]], name: str) -> str:
        value = self._require_single(query, name).strip()
        if not value:
            raise ApiError(400, "invalid_request", f"{name} is required")
        return value

    def _handle_block(self, environ) -> dict[str, object]:
        query = parse_qs(environ.get("QUERY_STRING", ""))
        has_hash = "hash" in query
        has_height = "height" in query
        if has_hash == has_height:
            raise ApiError(400, "invalid_request", "exactly one of hash or height is required")
        if has_hash:
            block_hash = self._require_single(query, "hash")
            payload = self.service.inspect_block(block_hash=block_hash)
        else:
            height = self._parse_required_int(query, "height", minimum=0)
            payload = self.service.inspect_block(height=height)
        if payload is None:
            raise ApiError(404, "not_found", "block not found")
        return payload

    def _handle_submit_tx(self, environ) -> dict[str, object]:
        payload = self._read_json(environ, max_body_bytes=self.TX_SUBMIT_JSON_BODY_MAX_BYTES)
        raw_hex = self._parse_required_hex_field(
            payload,
            "raw_hex",
            max_chars=self.TX_SUBMIT_RAW_HEX_MAX_CHARS,
        )
        try:
            if self.tx_submit_handler is not None:
                return self.tx_submit_handler(raw_hex=raw_hex)
            accepted = self.service.submit_raw_transaction(raw_hex)
        except ValidationError as exc:
            raise ApiError(400, "validation_error", str(exc)) from exc
        except ValueError as exc:
            raise ApiError(400, "invalid_request", str(exc)) from exc
        return {"accepted": True, "txid": accepted.transaction.txid(), "fee": accepted.fee}

    def _handle_get_block_template(self, environ) -> dict[str, object]:
        payload = self._read_json(environ, max_body_bytes=self.MINING_TEMPLATE_JSON_BODY_MAX_BYTES)
        payout_address = payload.get("payout_address")
        miner_id = payload.get("miner_id")
        template_mode = payload.get("template_mode", "full_block")
        if not isinstance(payout_address, str) or not payout_address.strip():
            raise ApiError(400, "invalid_request", "payout_address is required")
        if not is_valid_address(payout_address):
            raise ApiError(400, "invalid_request", "invalid payout_address")
        if not isinstance(miner_id, str) or not miner_id.strip():
            raise ApiError(400, "invalid_request", "miner_id is required")
        try:
            template = self.service.get_block_template(
                payout_address=payout_address.strip(),
                miner_id=miner_id.strip(),
                template_mode=template_mode,
            )
            self.logger.info(
                "mining template issued miner_id=%s template_id=%s height=%s previous_block_hash=%s template_expiry=%s template_ttl_seconds=%s",
                miner_id.strip(),
                template.get("template_id"),
                template.get("height"),
                template.get("previous_block_hash"),
                template.get("template_expiry"),
                self.service.mining_status().get("template_ttl_seconds"),
            )
            return template
        except ValueError as exc:
            raise ApiError(400, "invalid_request", str(exc)) from exc

    def _handle_submit_block(self, environ) -> dict[str, object]:
        payload = self._read_json(environ, max_body_bytes=self.BLOCK_SUBMIT_JSON_BODY_MAX_BYTES)
        template_id = payload.get("template_id")
        serialized_block = self._parse_required_hex_field(
            payload,
            "serialized_block",
            max_chars=self.BLOCK_SUBMIT_RAW_HEX_MAX_CHARS,
        )
        miner_id = payload.get("miner_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise ApiError(400, "invalid_request", "template_id is required")
        if not isinstance(miner_id, str) or not miner_id.strip():
            raise ApiError(400, "invalid_request", "miner_id is required")
        if self.mining_submit_handler is not None:
            return self.mining_submit_handler(
                template_id=template_id.strip(),
                serialized_block_hex=serialized_block,
                miner_id=miner_id.strip(),
            )
        return self.service.submit_mined_block(
            template_id=template_id.strip(),
            serialized_block_hex=serialized_block,
            miner_id=miner_id.strip(),
        )

    def _handle_address(self, *, method: str, path: str, environ) -> object:
        if method != "GET":
            raise ApiError(404, "not_found", "not found")
        base = "/v1/address/"
        remainder = path[len(base) :]
        address, separator, suffix = remainder.partition("/")
        if not address:
            raise ApiError(404, "not_found", "not found")
        if not is_valid_address(address):
            raise ApiError(400, "invalid_request", "invalid address")
        if not separator:
            return self.service.balance_diagnostics(address)
        if suffix == "utxos":
            return self.service.utxo_diagnostics(address)
        if suffix == "history":
            query = parse_qs(environ.get("QUERY_STRING", ""))
            limit = self._parse_optional_int(
                query,
                "limit",
                minimum=1,
                maximum=self.ADDRESS_HISTORY_MAX_LIMIT,
                default=self.ADDRESS_HISTORY_DEFAULT_LIMIT,
            )
            order = self._parse_optional_choice(query, "order", {"asc", "desc"}, default="desc")
            return self.service.address_history(address, limit=limit, descending=order == "desc")
        raise ApiError(404, "not_found", "not found")

    def _handle_mempool(self, environ) -> list[dict[str, object]]:
        query = parse_qs(environ.get("QUERY_STRING", ""))
        offset, limit = self._parse_pagination(
            query,
            default_limit=self.MEMPOOL_DEFAULT_LIMIT,
            max_limit=self.MEMPOOL_MAX_LIMIT,
        )
        rows = []
        for row in self.service.mempool_diagnostics()[offset : offset + limit]:
            fee_chipbits = int(row["fee_chipbits"])
            weight_units = int(row["weight_units"])
            enriched = dict(row)
            if weight_units > 0:
                enriched["fee_rate_chipbits_per_weight_unit"] = fee_chipbits / weight_units
            else:
                enriched["fee_rate_chipbits_per_weight_unit"] = 0.0
            rows.append(enriched)
        return rows

    def _handle_peers(self, environ) -> list[dict[str, object]]:
        query = parse_qs(environ.get("QUERY_STRING", ""))
        offset, limit = self._parse_pagination(
            query,
            default_limit=self.PEERS_DEFAULT_LIMIT,
            max_limit=self.PEERS_MAX_LIMIT,
        )
        return self.service.peer_diagnostics()[offset : offset + limit]

    def _parse_pagination(
        self,
        query: dict[str, list[str]],
        *,
        default_limit: int,
        max_limit: int,
    ) -> tuple[int, int]:
        offset = self._parse_optional_int(
            query,
            "offset",
            minimum=0,
            maximum=self.MAX_DIAGNOSTIC_OFFSET,
            default=0,
        )
        limit = self._parse_optional_int(
            query,
            "limit",
            minimum=1,
            maximum=max_limit,
            default=default_limit,
        )
        assert offset is not None
        assert limit is not None
        return offset, limit

    def _read_json(self, environ, *, max_body_bytes: int = DEFAULT_JSON_BODY_MAX_BYTES) -> dict:
        raw_content_length = environ.get("CONTENT_LENGTH") or "0"
        try:
            content_length = int(raw_content_length)
        except ValueError as exc:
            raise ApiError(400, "invalid_request", "CONTENT_LENGTH must be an integer") from exc
        if content_length < 0:
            raise ApiError(400, "invalid_request", "CONTENT_LENGTH must be >= 0")
        if content_length > max_body_bytes:
            raise ApiError(
                413,
                "payload_too_large",
                f"request body exceeds {max_body_bytes} bytes",
            )
        body = environ["wsgi.input"].read(content_length)
        if not body:
            return {}
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(400, "invalid_request", "request body must be valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ApiError(400, "invalid_request", "request body must be a JSON object")
        return decoded

    def _parse_required_hex_field(self, payload: dict, name: str, *, max_chars: int) -> str:
        raw_value = payload.get(name)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ApiError(400, "invalid_request", f"{name} is required")
        value = raw_value.strip()
        if len(value) > max_chars:
            raise ApiError(
                413,
                "payload_too_large",
                f"{name} exceeds {max_chars} hex characters",
            )
        if len(value) % 2 != 0:
            raise ApiError(400, "invalid_request", f"{name} must contain an even number of hex characters")
        return value

    def _parse_required_int(self, query: dict[str, list[str]], name: str, *, minimum: int | None = None) -> int:
        raw = self._require_single(query, name)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ApiError(400, "invalid_request", f"{name} must be an integer") from exc
        if minimum is not None and value < minimum:
            raise ApiError(400, "invalid_request", f"{name} must be >= {minimum}")
        return value

    def _parse_optional_int(
        self,
        query: dict[str, list[str]],
        name: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        if name not in query:
            return default
        value = self._parse_required_int(query, name, minimum=minimum)
        if maximum is not None and value > maximum:
            raise ApiError(400, "invalid_request", f"{name} must be between {minimum or 0} and {maximum}")
        return value

    def _parse_optional_choice(
        self,
        query: dict[str, list[str]],
        name: str,
        allowed: set[str],
        *,
        default: str,
    ) -> str:
        if name not in query:
            return default
        value = self._require_single(query, name)
        if value not in allowed:
            raise ApiError(400, "invalid_request", f"{name} must be {' or '.join(sorted(allowed))}")
        return value

    def _require_single(self, query: dict[str, list[str]], name: str) -> str:
        values = query.get(name)
        if not values:
            raise ApiError(400, "invalid_request", f"{name} is required")
        if len(values) != 1 or not values[0]:
            raise ApiError(400, "invalid_request", f"{name} must be provided exactly once")
        return values[0]

    def _cors_headers(self, origin: str | None) -> list[tuple[str, str]]:
        if origin is None or origin not in self.allowed_origins:
            return []
        return [
            ("Access-Control-Allow-Origin", origin),
            ("Vary", "Origin"),
        ]

    def _options_response(self, start_response, origin: str | None):
        headers = [("Content-Length", "0")]
        cors_headers = self._cors_headers(origin)
        if cors_headers:
            headers.extend(cors_headers)
            headers.extend(
                [
                    ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
                    ("Access-Control-Allow-Headers", "Content-Type"),
                ]
            )
        start_response("204 No Content", headers)
        return [b""]

    def _json_response(self, start_response, status_code: int, payload, *, origin: str | None):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        status_text = {
            200: "200 OK",
            204: "204 No Content",
            400: "400 Bad Request",
            404: "404 Not Found",
            413: "413 Payload Too Large",
            500: "500 Internal Server Error",
        }[status_code]
        headers = [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
        ]
        headers.extend(self._cors_headers(origin))
        start_response(
            status_text,
            headers,
        )
        return [body]


def load_allowed_origins_from_env() -> set[str]:
    """Return the configured CORS allow-list."""

    raw = os.environ.get("CHIPCOIN_HTTP_ALLOWED_ORIGINS", "")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _status_cache_ttl_from_env() -> float:
    raw = os.environ.get("CHIPCOIN_HTTP_STATUS_CACHE_TTL_SECONDS", "1.0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def create_app(
    data_path: Path,
    *,
    network: str = "mainnet",
    allowed_origins: set[str] | None = None,
) -> HttpApiApp:
    """Create the HTTP API app backed by a local node service."""

    return HttpApiApp(
        NodeService.open_sqlite(data_path, network=network),
        allowed_origins=load_allowed_origins_from_env() if allowed_origins is None else allowed_origins,
    )


def main(argv: list[str] | None = None) -> int:
    """Run the HTTP API server."""

    parser = argparse.ArgumentParser(prog="chipcoin-http")
    parser.add_argument("--data", default="chipcoin.sqlite3")
    parser.add_argument("--network", default="mainnet")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    args = parser.parse_args(argv)

    configure_logging(args.log_level)
    app = create_app(Path(args.data), network=args.network)
    with make_server(args.host, args.port, app, server_class=ThreadingWSGIServer) as server:
        server.serve_forever()
    return 0
