import { useEffect, useState } from "react";

import { SUPPORTED_NETWORKS, getSupportedNetwork, type SupportedNetworkId } from "./constants";

export function NetworkChoice({
  value,
  onChange,
  disabled = false,
}: {
  value: SupportedNetworkId;
  onChange(network: SupportedNetworkId): void;
  disabled?: boolean;
}): JSX.Element {
  const [showOtherNetworks, setShowOtherNetworks] = useState(value !== "mainnet");
  const selected = getSupportedNetwork(value);

  useEffect(() => {
    if (value !== "mainnet") {
      setShowOtherNetworks(true);
    }
  }, [value]);

  return (
    <div className="stack network-choice">
      <p className="network-primary"><strong>Network: {selected.label}</strong><br />{selected.statusLabel}</p>
      <button
        type="button"
        className="network-options-toggle"
        aria-expanded={showOtherNetworks}
        disabled={disabled}
        onClick={() => setShowOtherNetworks((open) => !open)}
      >
        {showOtherNetworks ? "Hide test networks" : "Testnet / advanced networks"}
      </button>
      {showOtherNetworks ? (
        <label className="stack">
          <span>Network</span>
          <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value as SupportedNetworkId)}>
            {SUPPORTED_NETWORKS.map((network) => (
              <option key={network.id} value={network.id}>{network.label}</option>
            ))}
          </select>
        </label>
      ) : null}
      {value !== "mainnet" ? (
        <p className="network-test-warning">{selected.label} is for testing. Its coins are separate from Mainnet CHC.</p>
      ) : null}
    </div>
  );
}
