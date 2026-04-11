"""Persistence boundary for bootstrap peer records."""

from __future__ import annotations

import sqlite3
from threading import Lock

from .models import PeerRecord


class PeerStore:
    """Minimal store abstraction for bootstrap peer records."""

    def list_peers(self, network: str, *, now: int, limit: int | None = None) -> list[PeerRecord]:
        """Return peers known for a network."""

        raise NotImplementedError

    def announce(self, record: PeerRecord) -> PeerRecord:
        """Insert or refresh a peer record."""

        raise NotImplementedError

    def prune(self, now: int) -> int:
        """Delete expired peer records and return the number removed."""

        raise NotImplementedError


class InMemoryPeerStore(PeerStore):
    """Thread-safe in-memory store for bootstrap peer records."""

    def __init__(self, *, peer_expiry_seconds: int, max_peers_per_network: int = 1024) -> None:
        self.peer_expiry_seconds = peer_expiry_seconds
        self.max_peers_per_network = max(1, max_peers_per_network)
        self._records: dict[tuple[str, int, str], PeerRecord] = {}
        self._lock = Lock()

    def list_peers(self, network: str, *, now: int, limit: int | None = None) -> list[PeerRecord]:
        """Return known peers for a network ordered by freshness."""

        self.prune(now)
        with self._lock:
            peers = [record for record in self._records.values() if record.network == network]
        peers = sorted(peers, key=lambda record: (-record.last_seen, record.host, record.p2p_port))
        if limit is None:
            return peers
        return peers[: max(1, limit)]

    def announce(self, record: PeerRecord) -> PeerRecord:
        """Insert or refresh a peer record by stable identity."""

        key = (record.host, record.p2p_port, record.network)
        with self._lock:
            current = self._records.get(key)
            if current is None:
                self._records[key] = record
            else:
                self._records[key] = PeerRecord(
                    host=current.host,
                    p2p_port=current.p2p_port,
                    network=current.network,
                    first_seen=current.first_seen,
                    last_seen=record.last_seen,
                    source=record.source or current.source,
                    software_version=record.software_version or current.software_version,
                    advertised_height=record.advertised_height,
                    node_id=record.node_id or current.node_id,
                )
            self._trim_network(record.network)
            return self._records[key]

    def prune(self, now: int) -> int:
        """Delete expired records based on the configured timeout."""

        threshold = now - self.peer_expiry_seconds
        with self._lock:
            expired_keys = [key for key, record in self._records.items() if record.last_seen < threshold]
            for key in expired_keys:
                del self._records[key]
        return len(expired_keys)

    def _trim_network(self, network: str) -> None:
        """Keep one network within the configured record cap."""

        network_records = [record for record in self._records.values() if record.network == network]
        overflow = len(network_records) - self.max_peers_per_network
        if overflow <= 0:
            return
        to_drop = sorted(
            network_records,
            key=lambda record: (record.last_seen, record.first_seen, record.host, record.p2p_port),
        )[:overflow]
        for record in to_drop:
            self._records.pop((record.host, record.p2p_port, record.network), None)


class SQLitePeerStore(PeerStore):
    """SQLite-backed peer store for production bootstrap discovery."""

    def __init__(self, connection: sqlite3.Connection, *, peer_expiry_seconds: int, max_peers_per_network: int = 1024) -> None:
        self.connection = connection
        self.peer_expiry_seconds = peer_expiry_seconds
        self.max_peers_per_network = max(1, max_peers_per_network)
        self._initialize_schema()

    def list_peers(self, network: str, *, now: int, limit: int | None = None) -> list[PeerRecord]:
        """Return non-expired peers for one network ordered by freshness."""

        self.prune(now)
        query = """
            SELECT
                host,
                p2p_port,
                network,
                first_seen,
                last_seen,
                source,
                software_version,
                advertised_height,
                node_id
            FROM peers
            WHERE network = ?
            ORDER BY last_seen DESC, host ASC, p2p_port ASC
        """
        params: tuple[object, ...] = (network,)
        if limit is not None:
            query += " LIMIT ?"
            params = (network, max(1, limit))
        rows = self.connection.execute(query, params).fetchall()
        return [
            PeerRecord(
                host=row["host"],
                p2p_port=int(row["p2p_port"]),
                network=row["network"],
                first_seen=int(row["first_seen"]),
                last_seen=int(row["last_seen"]),
                source=row["source"],
                software_version=row["software_version"],
                advertised_height=None if row["advertised_height"] is None else int(row["advertised_height"]),
                node_id=row["node_id"],
            )
            for row in rows
        ]

    def announce(self, record: PeerRecord) -> PeerRecord:
        """Insert or refresh one peer endpoint by stable network address."""

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO peers(
                    host,
                    p2p_port,
                    network,
                    first_seen,
                    last_seen,
                    source,
                    software_version,
                    advertised_height,
                    node_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, p2p_port, network) DO UPDATE SET
                    first_seen = peers.first_seen,
                    last_seen = excluded.last_seen,
                    source = excluded.source,
                    software_version = COALESCE(excluded.software_version, peers.software_version),
                    advertised_height = excluded.advertised_height,
                    node_id = COALESCE(excluded.node_id, peers.node_id)
                """,
                (
                    record.host,
                    record.p2p_port,
                    record.network,
                    record.first_seen,
                    record.last_seen,
                    record.source,
                    record.software_version,
                    record.advertised_height,
                    record.node_id,
                ),
            )
            self._trim_network(record.network)
        row = self.connection.execute(
            """
            SELECT host, p2p_port, network, first_seen, last_seen, source, software_version, advertised_height, node_id
            FROM peers
            WHERE host = ? AND p2p_port = ? AND network = ?
            """,
            (record.host, record.p2p_port, record.network),
        ).fetchone()
        return PeerRecord(
            host=row["host"],
            p2p_port=int(row["p2p_port"]),
            network=row["network"],
            first_seen=int(row["first_seen"]),
            last_seen=int(row["last_seen"]),
            source=row["source"],
            software_version=row["software_version"],
            advertised_height=None if row["advertised_height"] is None else int(row["advertised_height"]),
            node_id=row["node_id"],
        )

    def prune(self, now: int) -> int:
        """Delete expired peer records and return the number removed."""

        threshold = now - self.peer_expiry_seconds
        with self.connection:
            cursor = self.connection.execute("DELETE FROM peers WHERE last_seen < ?", (threshold,))
        return int(cursor.rowcount if cursor.rowcount is not None else 0)

    def _trim_network(self, network: str) -> None:
        """Keep one network within the configured maximum record count."""

        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM peers WHERE network = ?",
            (network,),
        ).fetchone()
        overflow = int(row["count"]) - self.max_peers_per_network
        if overflow <= 0:
            return
        self.connection.execute(
            """
            DELETE FROM peers
            WHERE rowid IN (
                SELECT rowid
                FROM peers
                WHERE network = ?
                ORDER BY last_seen ASC, first_seen ASC, host ASC, p2p_port ASC
                LIMIT ?
            )
            """,
            (network, overflow),
        )

    def _initialize_schema(self) -> None:
        """Create the bootstrap peer table when missing."""

        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS peers (
                    host TEXT NOT NULL,
                    p2p_port INTEGER NOT NULL,
                    network TEXT NOT NULL,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    software_version TEXT,
                    advertised_height INTEGER,
                    node_id TEXT,
                    PRIMARY KEY(host, p2p_port, network)
                )
                """
            )
