# PQ Height 20000 External Services Checklist

This checklist covers public services that may live outside this repository.
Do not edit or deploy external repositories from the node rollout task.

## Explorer

- Activation height displays `20000` for testnet.
- Devnet still displays `30000`.
- Countdown and progress derive from the API or current consensus metadata.
- PQ active boolean flips at height `20000`.
- Explanatory note states that the height was rescheduled from `30000` to
  `20000`.
- Transaction badges still distinguish legacy, transaction v2, ML-DSA input,
  and CHCQ output metadata.
- Address badges still distinguish CHC and CHCQ.
- `config.js` or equivalent environment config contains no stale testnet
  `30000` value.
- Service worker and browser cache are invalidated or asset version is bumped.
- API base URL points at the upgraded testnet API.
- Mobile display handles the new countdown and active state.
- No devnet/testnet labels are swapped.

## Website

- Post-Quantum page says testnet activation is scheduled at height `20000`.
- Live testnet page uses the updated countdown.
- Developer docs mention the mandatory testnet upgrade.
- Run-a-node page instructs operators to verify height `20000`.
- Browser wallet page states CHCQ recognition is available but browser PQ
  signing/send remain disabled.
- Announcement includes upgrade deadline and compatibility warning.
- Sitemap `lastmod` is updated if the publishing workflow uses it.
- Structured data is updated only if it contains activation details.

## Daily Report

- Activation height is `20000`.
- Blocks remaining and ETA are derived from the current height.
- Active/inactive state flips at height `20000`.
- No operational testnet countdown still assumes `30000`.
- Historical reports may keep old values only when clearly timestamped.

## Operational Dashboard

- `pq-operational-readiness` reports `activation_height=20000`.
- Remote API checks are flagged as deployment pending if public nodes still
  report the old software.
- Unknown peer version distribution is reported separately from failures.

## Bootstrap/Snapshot Service

- Snapshot metadata does not embed a stale PQ testnet activation height.
- Snapshot-producing host runs the upgraded package.
- Snapshot consumers do not need a database migration or format change.
