import { useState } from "react";

import type { AppState } from "../../state/app_state";
import { SUPPORTED_NETWORKS, getSupportedNetwork, type SupportedNetworkId } from "../../shared/constants";
import { sendWalletMessage } from "../../shared/messages";

export function Settings(
  { state, onUpdated, onOpenBackup }: { state: AppState; onUpdated(state: AppState): void; onOpenBackup(): void },
): JSX.Element {
  const [nodeApiBaseUrl, setNodeApiBaseUrl] = useState(state.nodeApiBaseUrl);
  const [expectedNetwork, setExpectedNetwork] = useState<SupportedNetworkId>(state.expectedNetwork);
  const [message, setMessage] = useState<string | null>(null);
  const selectedNetwork = getSupportedNetwork(expectedNetwork);

  function handleNetworkChange(networkId: SupportedNetworkId): void {
    const network = getSupportedNetwork(networkId);
    setExpectedNetwork(network.id);
    setNodeApiBaseUrl(network.defaultNodeApiBaseUrl);
    setMessage(null);
  }

  async function handleSave(): Promise<void> {
    try {
      const nextState = await sendWalletMessage<AppState>({ type: "wallet:updateNode", nodeApiBaseUrl, expectedNetwork });
      onUpdated(nextState);
      setMessage(`Node endpoint updated for ${selectedNetwork.label}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update node endpoint.");
    }
  }

  async function handleLock(): Promise<void> {
    const nextState = await sendWalletMessage<AppState>({ type: "wallet:lock" });
    onUpdated(nextState);
  }

  async function handleRemoveWallet(): Promise<void> {
    if (!globalThis.confirm("Remove this wallet from the extension? You will need the private key to import it again.")) {
      return;
    }
    const nextState = await sendWalletMessage<AppState>({ type: "wallet:remove" });
    setMessage("Wallet removed.");
    onUpdated(nextState);
  }

  return (
    <section className="panel">
      <h2>Settings</h2>
      <div className="stack">
        <label className="stack">
          <span>Network</span>
          <select value={expectedNetwork} onChange={(event) => handleNetworkChange(event.target.value as SupportedNetworkId)}>
            {SUPPORTED_NETWORKS.map((network) => (
              <option key={network.id} value={network.id}>{network.label}</option>
            ))}
          </select>
        </label>
        <p className="message">{selectedNetwork.description}</p>
        <p className="message">Endpoint mode: {selectedNetwork.defaultEndpointLabel}</p>
        <label className="stack">
          <span>Node API endpoint</span>
          <input value={nodeApiBaseUrl} onChange={(event) => setNodeApiBaseUrl(event.target.value)} placeholder="Node API endpoint" />
        </label>
        {selectedNetwork.localNodeApiBaseUrl ? (
          <p className="message">Advanced/operator local node API: <span className="mono">{selectedNetwork.localNodeApiBaseUrl}</span></p>
        ) : null}
        <p className="message">{selectedNetwork.httpSafetyNote}</p>
        <button className="primary-button" onClick={() => void handleSave()}>Save network endpoint</button>
        <button className="secondary-button" onClick={onOpenBackup}>Open backup / export</button>
        <button onClick={() => void handleLock()}>Lock wallet</button>
        <button className="danger-button" onClick={() => void handleRemoveWallet()}>Remove wallet</button>
      </div>
      {message ? <p className="message">{message}</p> : null}
    </section>
  );
}
