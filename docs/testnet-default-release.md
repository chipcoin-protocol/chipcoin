# Testnet Is Now The Default Runtime Profile

Chipcoin's public runtime default is now `testnet`. Devnet remains available
only as an explicit legacy/development profile.

## Operational Change

New installs should use:

```bash
cp .env.example .env
docker compose up -d --build node
```

The default Compose project is `chipcoin-testnet`.

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
