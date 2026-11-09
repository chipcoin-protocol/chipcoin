# Clean Install Checklist

This checklist is for verifying the public repository from a fresh clone.

## Docker Node (default Mainnet)

```bash
git clone <repo-url>
cd chipcoin
python3 scripts/setup/wizard.py
docker compose --env-file .env.mainnet config --quiet
docker compose --env-file .env.mainnet up -d --build node
docker compose --env-file .env.mainnet ps
```

This path needs Python 3 and Docker Compose on the host. The Docker builder
compiles the native ML-DSA-44 module; host GCC and a virtual environment are
unnecessary for a passive node. The wizard prepares a distinct Mainnet database
and keeps P2P private by default. Select Testnet or Devnet explicitly in the
wizard and use its printed environment file for that network.

## Optional Native Python CLI

For native CLI use, wallet creation/import in the wizard, or wizard snapshot
import, install host build dependencies first. On Ubuntu:

```bash
sudo apt-get install build-essential python3-dev python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Checks:

- `chipcoin --help`
- `chipcoin mine --help`

## Legacy Manual Testnet Runtime Config

```bash
cp .env.example .env
sudo mkdir -p /var/lib/chipcoin/data
sudo mkdir -p /var/lib/chipcoin/wallets
sudo mkdir -p /var/lib/chipcoin/logs
sudo chown -R "$USER:$USER" /var/lib/chipcoin
chipcoin wallet-generate --wallet-file /var/lib/chipcoin/wallets/chipcoin-wallet.json
```

Checks:

- `.env` exists locally only
- runtime paths in `.env` point to writable local paths before `docker compose up`
- wallet file is outside version control

## Legacy Manual Testnet Node And Miner

```bash
docker compose up --build node miner
```

Checks:

- `docker compose ps`
- `docker compose logs -f node`
- `docker compose logs -f miner`
- `curl http://127.0.0.1:8081/v1/status`
- `curl http://127.0.0.1:8081/mining/status`
- the node and miner containers are using runtime files outside the repository
- the miner starts without creating a local chain database

## Browser Wallet

```bash
cd apps/browser-wallet
npm install
./build-all.sh
```

Checks:

- `dist-chrome` exists
- `dist-firefox` exists
- extension loads in Chrome
- extension loads in Firefox
- wallet can create or import
- wallet can connect to the node API

## End-To-End

Checks:

- wallet shows address and balance
- a transaction can be sent
- the transaction appears through the node API
- the transaction can later be observed by the user in their chosen inspection tooling
- any failure in this section is treated as a documentation or onboarding gap until proven otherwise
