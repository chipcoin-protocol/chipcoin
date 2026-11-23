# Clean Install Checklist

This checklist is for verifying the public repository from a fresh clone.

## Docker Node (default Mainnet)

```bash
git clone https://github.com/chipcoin-protocol/chipcoin.git
cd chipcoin
./setup.sh
```

This path needs Git and Docker Compose on the host; it needs no host Python, GCC or virtual environment even for miner/reward wallet generation. Follow the exact Compose build/start/verification commands printed by the wizard. The wizard prepares a distinct Mainnet database
and keeps P2P private by default. Select Testnet or Devnet explicitly in the
wizard and use its printed environment file for that network.

## Optional Native Python CLI

For the advanced host-Python CLI or wizard, install host build dependencies yourself. On Ubuntu:

```bash
sudo apt-get install build-essential python3-dev python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
```

Checks:

- `chipcoin --help`
- `chipcoin mine --help`

## Explicit Testnet Installation

```bash
./setup.sh
```

Select Testnet explicitly in the wizard. The wizard prepares a separate `testnet/config/.env` and runtime. The node starts only when you run its printed Compose command.

Verify with the printed Compose `ps` command and
`curl http://127.0.0.1:28081/v1/status`. Start a miner separately only after
its wallet has been created and backed up.

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
