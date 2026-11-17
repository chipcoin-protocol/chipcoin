import { useEffect, useState } from "react";

import type { AppState } from "../../state/app_state";
import { DEFAULT_NETWORK, getSupportedNetwork, type SupportedNetworkId } from "../../shared/constants";
import { NetworkChoice } from "../../shared/NetworkChoice";
import { sendWalletMessage } from "../../shared/messages";
import { ConfigureNode } from "./ConfigureNode";
import { CreateWallet } from "./CreateWallet";
import { ImportWallet } from "./ImportWallet";
import { RecoverWallet } from "./RecoverWallet";
import { SetPassword } from "./SetPassword";

type Step = "welcome" | "create" | "recover" | "import" | "password" | "node";
type Mode = "create-seed" | "recover-seed" | "import-key" | "create-pq" | "import-pq";

export function OnboardingApp(): JSX.Element {
  const [step, setStep] = useState<Step>("welcome");
  const [mode, setMode] = useState<Mode>("import-pq");
  const [expectedNetwork, setExpectedNetwork] = useState<SupportedNetworkId>(DEFAULT_NETWORK);
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [privateKeyHex, setPrivateKeyHex] = useState("");
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [isNetworkBusy, setIsNetworkBusy] = useState(true);
  const selectedNetwork = getSupportedNetwork(expectedNetwork);

  useEffect(() => {
    void sendWalletMessage<AppState>({ type: "wallet:getState" })
      .then((state) => setExpectedNetwork(state.expectedNetwork))
      .catch(() => setNetworkError("Unable to load current network settings."))
      .finally(() => setIsNetworkBusy(false));
  }, []);

  async function handleNetworkChange(networkId: SupportedNetworkId): Promise<void> {
    if (isNetworkBusy) return;
    setIsNetworkBusy(true);
    setNetworkError(null);
    try {
      const network = getSupportedNetwork(networkId);
      const state = await sendWalletMessage<AppState>({
        type: "wallet:updateNode",
        expectedNetwork: networkId,
        nodeApiBaseUrl: network.defaultNodeApiBaseUrl,
      });
      setExpectedNetwork(state.expectedNetwork);
      setMode("import-pq");
    } catch (error) {
      setNetworkError(error instanceof Error ? error.message : "Unable to change network.");
    } finally {
      setIsNetworkBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <h1>Chipcoin Wallet Onboarding</h1>
      {step === "welcome" && (
        <section className="panel stack">
          <p>Import a {selectedNetwork.label} ML-DSA-44 wallet or create a new one. Keep its seed offline.</p>
          <NetworkChoice value={expectedNetwork} disabled={isNetworkBusy} onChange={(network) => void handleNetworkChange(network)} />
          {networkError ? <p className="message error">{networkError}</p> : null}
          <button className="primary-button wallet-setup-primary" disabled={isNetworkBusy} onClick={() => { setMode("import-pq"); setStep("import"); }}>Import {selectedNetwork.label} Wallet</button>
          <button className="secondary-button" disabled={isNetworkBusy} onClick={() => { setMode("create-pq"); setStep("password"); }}>Create {selectedNetwork.label} Wallet</button>
          {expectedNetwork !== "mainnet" ? (
            <div className="stack">
              <p className="message">Legacy wallet options for {selectedNetwork.label}:</p>
              <button disabled={isNetworkBusy} onClick={() => { setMode("create-seed"); setStep("create"); }}>Create legacy wallet</button>
              <button disabled={isNetworkBusy} onClick={() => { setMode("recover-seed"); setStep("recover"); }}>Recover legacy wallet</button>
              <button disabled={isNetworkBusy} onClick={() => { setMode("import-key"); setStep("import"); }}>Import legacy key</button>
            </div>
          ) : null}
        </section>
      )}
      {step === "create" && <CreateWallet onContinue={(value) => { setRecoveryPhrase(value); setStep("password"); }} />}
      {step === "recover" && <RecoverWallet onContinue={(value) => { setRecoveryPhrase(value); setStep("password"); }} />}
      {step === "import" && <ImportWallet pq={mode === "import-pq"} onContinue={(value) => { setPrivateKeyHex(value); setStep("password"); }} />}
      {step === "password" && (
        <SetPassword
          mode={mode}
          recoveryPhrase={recoveryPhrase}
          privateKeyHex={privateKeyHex}
          onCreated={() => setStep("node")}
        />
      )}
      {step === "node" && <ConfigureNode />}
    </main>
  );
}
