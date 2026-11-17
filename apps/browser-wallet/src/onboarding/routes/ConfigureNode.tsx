import { useEffect, useState } from "react";

import type { AppState } from "../../state/app_state";
import { DEFAULT_NETWORK, getSupportedNetwork, type SupportedNetworkId } from "../../shared/constants";
import { NetworkChoice } from "../../shared/NetworkChoice";
import { sendWalletMessage } from "../../shared/messages";

export function ConfigureNode(): JSX.Element {
  const [expectedNetwork, setExpectedNetwork] = useState<SupportedNetworkId>(DEFAULT_NETWORK);
  const [nodeApiBaseUrl, setNodeApiBaseUrl] = useState(getSupportedNetwork(DEFAULT_NETWORK).defaultNodeApiBaseUrl);
  const [message, setMessage] = useState<string | null>(null);
  const selectedNetwork = getSupportedNetwork(expectedNetwork);

  useEffect(() => {
    void sendWalletMessage<AppState>({ type: "wallet:getState" }).then((state) => {
      setExpectedNetwork(state.expectedNetwork);
      setNodeApiBaseUrl(state.nodeApiBaseUrl);
    }).catch(() => setMessage("Unable to load current node settings."));
  }, []);

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
      <NetworkChoice value={expectedNetwork} onChange={handleNetworkChange} />
      <p>{selectedNetwork.description}</p>
      <p>Endpoint mode: {selectedNetwork.defaultEndpointLabel}</p>
      <input value={nodeApiBaseUrl} onChange={(event) => setNodeApiBaseUrl(event.target.value)} placeholder="Node API endpoint" />
      {selectedNetwork.localNodeApiBaseUrl ? <p>Local node API option: {selectedNetwork.localNodeApiBaseUrl}</p> : null}
      <p>{selectedNetwork.httpSafetyNote}</p>
      <button onClick={() => void handleSave()}>Save node endpoint</button>
      {message ? <p>{message}</p> : null}
    </section>
  );
}
