# Mainnet Network Ports

Mainnet is live. The public repository's generic Compose profile starts a new
node with private P2P and loopback-only HTTP. Publishing a peer requires an
explicit operator choice and a reachable public address; it does not require
exposing the raw HTTP API.

| Component | Endpoint / port | Exposure |
| --- | --- | --- |
| Mainnet node P2P | `8333/tcp` | `127.0.0.1` by default; publish on a public interface only for an intentionally public peer |
| Mainnet node HTTP API | `127.0.0.1:8080` | Local operator access only; use an allowlisted HTTPS proxy for public wallet reads and transaction submission |
| Mainnet bootstrap seed | `https://mainnet-bootstrap.chipcoinprotocol.com` | HTTPS discovery service; does not participate in consensus |
| Mainnet wallet-safe API | `https://mainnet-api.chipcoinprotocol.com` | Allowlisted HTTPS wallet API; not the raw node API |
| Explorer | `https://explorer.chipcoinprotocol.com` | Public web UI and read-only API |

The bootstrap seed and Explorer have their own deployment configurations;
their private backend ports are not part of the generic Core Compose profile.
Use the selected host's deployment file when checking those bindings.

## Network separation

| Profile | P2P | Node HTTP host | Bootstrap |
| --- | --- | --- | --- |
| Mainnet | `8333/tcp` | `127.0.0.1:8080` | `https://mainnet-bootstrap.chipcoinprotocol.com` |
| Testnet | `28444/tcp` | `127.0.0.1:28081` | `https://bootstrap.chipcoinprotocol.com` |
| Devnet | `18444/tcp` | `127.0.0.1:8081` | Separate development profile |

Do not reuse a database, wallet, peer cache, or runtime directory across
networks. To publish a Mainnet peer, set `NODE_P2P_PUBLISH_HOST` deliberately,
open or forward `8333/tcp`, and verify reachability from outside the host.
Keep node HTTP on loopback. `BOOTSTRAP_ANNOUNCE_ENABLED` defaults to `false`;
enable it only for a reachable endpoint and configure `NODE_PUBLIC_HOST` and
`NODE_PUBLIC_P2P_PORT` to match. An announcement is a discovery hint, not proof
of node identity; peers must complete the P2P handshake.
