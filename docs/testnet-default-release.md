# Historical Release Note: Testnet Default

This page records an earlier release when new installs selected Testnet. It is
historical, not the current setup procedure. New installations now select
Mainnet through `python3 scripts/setup/wizard.py` and write `.env.mainnet`.
Testnet and Devnet remain available through explicit selection.

## Operational Change

The former Testnet-only installation used:

```bash
cp .env.example .env
docker compose up -d --build node
```

This command still selects Testnet because `.env.example` is the Testnet
template. It is not the default path for a new Mainnet installation.

## Default Ports And Endpoints

- P2P: `28444/tcp`
- node HTTP: `127.0.0.1:28081`
- bootstrap: `https://bootstrap.chipcoinprotocol.com`
- signed snapshot manifest: `https://chipcoinprotocol.com/downloads/snapshots/testnet/latest.manifest.json`
- wallet-safe API: `https://testnet-api.chipcoinprotocol.com`
- explorer: `https://explorer.chipcoinprotocol.com/api/testnet/v1/status`

Expose P2P only. Do not expose raw node HTTP publicly.

## Devnet Legacy Path

Use `.env.devnet.example` only when you intentionally need the legacy devnet
profile:

```bash
cp .env.devnet.example .env.devnet
docker compose --env-file .env.devnet -p chipcoin-devnet up -d --build node
```
