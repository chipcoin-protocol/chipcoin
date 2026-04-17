"""Deterministic anti-concentration filters for observer-only rewards."""

from __future__ import annotations

from collections import defaultdict
import ipaddress

from .config import RewardObserverConfig
from .models import NodeEpochSummary


def subnet_key_for_ipv4(address: str | None, prefix: int) -> str | None:
    """Return one deterministic IPv4 subnet grouping key."""

    if address is None:
        return None
    try:
        ipv4 = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        return None
    network = ipaddress.IPv4Network(f"{ipv4}/{prefix}", strict=False)
    return str(network.network_address) + f"/{prefix}"


def apply_concentration_caps(
    summaries: list[NodeEpochSummary],
    config: RewardObserverConfig,
) -> list[NodeEpochSummary]:
    """Apply deterministic caps to already-baseline-eligible nodes."""

    ipv4_counts: dict[str, int] = defaultdict(int)
    subnet_counts: dict[str, int] = defaultdict(int)
    fingerprint_counts: dict[str, int] = defaultdict(int)
    updated: list[NodeEpochSummary] = []

    for summary in sorted(summaries, key=lambda item: (item.node_id, item.payout_address)):
        if not summary.final_eligible:
            updated.append(summary)
            continue

        subnet_key = subnet_key_for_ipv4(summary.public_ip, config.per_subnet_v4_prefix)
        rejection_reason: str | None = None
        concentration_status = "ok"

        if summary.public_ip is not None and ipv4_counts[summary.public_ip] >= config.per_public_ipv4_cap:
            rejection_reason = "ip_concentration_cap"
            concentration_status = "ip_concentration_cap"
        elif subnet_key is not None and subnet_counts[subnet_key] >= config.per_subnet_cap:
            rejection_reason = "subnet_concentration_cap"
            concentration_status = "subnet_concentration_cap"
        elif (
            config.fingerprint_cap is not None
            and summary.fingerprint is not None
            and fingerprint_counts[summary.fingerprint] >= config.fingerprint_cap
        ):
            rejection_reason = "fingerprint_concentration_cap"
            concentration_status = "fingerprint_concentration_cap"

        if rejection_reason is None:
            if summary.public_ip is not None:
                ipv4_counts[summary.public_ip] += 1
            if subnet_key is not None:
                subnet_counts[subnet_key] += 1
            if config.fingerprint_cap is not None and summary.fingerprint is not None:
                fingerprint_counts[summary.fingerprint] += 1

        updated.append(
            NodeEpochSummary(
                **{
                    **summary.__dict__,
                    "concentration_status": concentration_status,
                    "final_eligible": rejection_reason is None,
                    "rejection_reason": rejection_reason if rejection_reason is not None else summary.rejection_reason,
                    "subnet_key": subnet_key,
                }
            )
        )

    return updated
