# Apache Public API Proxies

This directory contains public-edge Apache templates for Chipcoin services.

## Testnet Wallet-Safe API

Template:

```text
deploy/apache/wallet-safe-api-testnet.conf
```

Public endpoint:

```text
https://testnet-api.chipcoinprotocol.com
```

Upstream on chipcom:

```text
http://127.0.0.1:28081
```

The proxy is intentionally wallet-safe. It allows only:

- `GET /v1/health`
- `GET /v1/status`
- `GET /v1/supply`
- `GET /v1/address/<address>`
- `GET /v1/address/<address>/utxos`
- `GET /v1/address/<address>/history`
- `GET /v1/tx/<64-char-hex-txid>`
- `POST /v1/tx/submit`
- `OPTIONS` for those browser wallet paths

It must block peerbook, mining, reward, admin, debug, snapshot/export, and all
other non-allowlisted paths. Do not proxy raw node HTTP publicly.

## Deployment Notes

1. In the domain/DNS panel, create DNS for `testnet-api.chipcoinprotocol.com` pointing at the Contabo public web edge.
   Use an `A` record for the Contabo IPv4 address. Add `AAAA` only if IPv6 is configured and reachable on that host.
2. Install the vhost template into `/etc/apache2/sites-available/`.
3. Add local TLS certificate directives, usually via Certbot.
4. Enable required Apache modules:

```bash
sudo a2enmod headers proxy proxy_http rewrite ssl
```

5. Enable the site and validate syntax:

```bash
sudo a2ensite wallet-safe-api-testnet.conf
sudo apache2ctl -t
sudo systemctl reload apache2
```

## CORS

The Phase 1 template uses `Access-Control-Allow-Origin: *` because the browser
wallet uses non-credentialed requests and the path allowlist is narrow. Before a
broader announcement, prefer replacing this with an explicit origin allowlist
for packaged wallet origins if they are stable.

## Rate Limiting

No request-rate limiting is assumed by this repo template. Before broader
public promotion, enable an Apache-supported limiter on chipcom, for example
`mod_evasive`, `mod_security`, or an upstream reverse-proxy/WAF rule. At minimum
rate-limit `POST /v1/tx/submit`.

## Reusable Mainnet Pattern

For future mainnet, duplicate the same wallet-safe API pattern with:

- separate hostname, for example `mainnet-api.chipcoinprotocol.com`
- mainnet upstream bound to localhost/private HTTP
- the same allowlist model
- stricter CORS and rate limiting before launch
