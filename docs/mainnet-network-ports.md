# Mainnet Network Port Profile

This is the candidate configuration only. It does not enable services, publish
ports, or authorize deployment.

| Component | Port | Transport | Binding / exposure |
| --- | ---: | --- | --- |
| Mainnet node P2P | 8333 | TCP | `127.0.0.1` by default; public peers explicitly set `NODE_P2P_PUBLISH_HOST=0.0.0.0` |
| Mainnet node API | container 8080; host 38084 | TCP/HTTP | host is fixed to `127.0.0.1`; never publish directly |
| Mainnet Bootstrap Seed | container 28081; host 28082 | TCP/HTTP | host is fixed to `127.0.0.1`; HTTPS proxy only |
| Explorer | 443 | TCP/HTTPS | public web edge; `/api/mainnet` is GET/OPTIONS-only and allowlisted |
| Wallet-safe node API | 443 | TCP/HTTPS | `mainnet-api.chipcoinprotocol.com`; allowlisted reads and transaction submission only |
| Bootstrap Seed | 443 | TCP/HTTPS | `mainnet-bootstrap.chipcoinprotocol.com`; separate mainnet instance |

The mainnet Bootstrap hostname is a proposed, not yet deployed DNS name. The
mainnet node's optional seed URL is `https://mainnet-bootstrap.chipcoinprotocol.com`.
The service is disabled until genesis, DNS, TLS, static peer and public launch
reviews are complete. Seed peers are untrusted hints; P2P identity is established
only by the normal network handshake.

## Network separation

| Profile | P2P | Node HTTP host | Bootstrap host |
| --- | --- | --- | --- |
| Devnet | 18444/TCP | `127.0.0.1:8081` | existing devnet/testnet seed service; network field filtered |
| Testnet | 28444/TCP | `127.0.0.1:28081` | `127.0.0.1:28080` behind HTTPS |
| Historical rehearsal | 8333/TCP on its isolated Docker network | `127.0.0.1:38081` and allocated siblings | isolated; do not reuse as public mainnet |
| Mainnet candidate | 8333/TCP, loopback until explicit public opt-in | `127.0.0.1:38084` | `127.0.0.1:28082` behind a separate HTTPS vhost |

No UDP listener is configured by the node's P2P service. Verify actual IPv4 and
IPv6 listeners and firewall state on the target host during deployment; this
source configuration alone cannot prove host-level exposure. Do not expose
`8080`, `38084`, `28081`, `28082`, `28080`, `8081`, or `8082` directly.

## Firewall plan (not applied)

- Public mainnet peer: allow inbound TCP 8333 only when the operator explicitly
  opts the node into public P2P; allow established traffic and outbound DNS,
  HTTPS and peer connections as required. Do not open UDP 8333.
- Private mainnet node: no unsolicited inbound P2P; keep API host binding on
  loopback. The outbound-only node may still connect and sync.
- Chipcom web edge: publicly allow TCP 443, plus TCP 80 only for HTTPS redirect
  and certificate maintenance. Do not publish 28080, 28082, 38084 or container
  ports. IPv6 exposure must be explicitly reviewed rather than inferred from
  IPv4 rules.
- Preserve existing testnet policy and ports; this candidate change does not
  apply firewall rules or alter active services.
