import { useState } from "react";

import type { AppState } from "../../state/app_state";
import { DEFAULT_NETWORK, SUPPORTED_NETWORKS, getSupportedNetwork, type SupportedNetworkId } from "../../shared/constants";
import { sendWalletMessage } from "../../shared/messages";

export function ConfigureNode(): JSX.Element {
  const [expectedNetwork, setExpectedNetwork] = useState<SupportedNetworkId>(DEFAULT_NETWORK);
  const [nodeApiBaseUrl, setNodeApiBaseUrl] = useState(getSupportedNetwork(DEFAULT_NETWORK).defaultNodeApiBaseUrl);
  const [message, setMessage] = useState<string | null>(null);
  const selectedNetwork = getSupportedNetwork(expectedNetwork);

  function handleNetworkChange(nextNetwork: SupportedNetworkId): void {
    setExpectedNetwork(nextNetwork);
    setNodeApiBaseUrl(getSupportedNetwork(nextNetwork).defaultNodeApiBaseUrl);
    setMessage(null);
  }

  async function handleSave(): Promise<void> {
    try {
      const state = await sendWalletMessage<AppState>({ type: "wallet:updateNode", nodeApiBaseUrl, expectedNetwork });
      setMessage(`Node configured for ${state.expectedNetwork}. You can now open the wallet popup.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to configure node endpoint.");
    }
  }

  return (
    <section>
      <h2>Configure node</h2>
      <label>
        Network
        <select value={expectedNetwork} onChange={(event) => handleNetworkChange(event.target.value as SupportedNetworkId)}>
          {SUPPORTED_NETWORKS.map((network) => (
            <option key={network.id} value={network.id}>{network.label}</option>
          ))}
        </select>
      </label>
      <p>{selectedNetwork.description}</p>
      <input value={nodeApiBaseUrl} onChange={(event) => setNodeApiBaseUrl(event.target.value)} placeholder="Node API endpoint" />
      <p>{selectedNetwork.httpSafetyNote}</p>
      <button onClick={() => void handleSave()}>Save node endpoint</button>
      {message ? <p>{message}</p> : null}
    </section>
  );
}
