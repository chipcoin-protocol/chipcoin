# System Requirements

## Supported Baseline

The documented public baseline is conservative.

Documented and validated clone-to-run path:

- Linux host on x86_64
- Docker Engine with the `docker compose` plugin
- Python 3.11+

Node.js 20+ and npm are needed only to build the browser wallet.

## Browser Wallet

Documented browser targets:

- desktop Chrome
- desktop Firefox

Firefox workflows:

- temporary add-on loading through `about:debugging` for development
- Mozilla-signed `.xpi` for normal Firefox Release/Beta installation; see
  `apps/browser-wallet/README.md` for build and signing requirements

## Hardware Guidance

Minimum guidance for a local devnet node + miner setup:

- 2 CPU cores
- 4 GB RAM
- 5 GB free disk space

Recommended guidance:

- 4 CPU cores
- 8 GB RAM
- 10 GB free disk space

These numbers are practical operator guidance for the current devnet stack, not formal performance guarantees.

## Important Limits

- macOS is not part of the documented clean-install validation path yet
- Windows is not part of the documented clean-install validation path yet
- ARM platforms are not part of the documented clean-install validation path yet
- Mainnet is the default for new wizard installations; Testnet and Devnet are
  selected explicitly

## Runtime Notes

- Docker is the primary documented runtime path for `node` and `miner`
- Python tooling is still required for CLI and wallet helper flows
- Node.js and npm are only required for building the browser wallet, not for running `node` and `miner`

## Network And Firewall Requirements

For basic outbound participation, a node only needs normal outbound internet access.

For public peer reachability, use the selected network's P2P port:

- Mainnet: `TCP 8333`
- Testnet: `TCP 28444`
- Devnet: `TCP 18444`

Optional ports:

- Mainnet node HTTP: `127.0.0.1:8080`
- Testnet node HTTP: `127.0.0.1:28081`
- Devnet node HTTP: `127.0.0.1:8081`

Keep raw node HTTP private. Opening the selected P2P port helps an operator
contribute a publicly reachable peer, but is not mandatory for outbound-only
participation. Home setups may also need router port forwarding.
