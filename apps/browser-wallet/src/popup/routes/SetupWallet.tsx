import { useEffect, useState } from "react";

import type { AppState } from "../../state/app_state";
import { getSupportedNetwork, type SupportedNetworkId } from "../../shared/constants";
import { NetworkChoice } from "../../shared/NetworkChoice";
import { sendWalletMessage } from "../../shared/messages";

type SetupMode = "create-seed" | "recover-seed" | "import-key" | "create-pq" | "import-pq";

export function SetupWallet({ state, onUpdated, onCreated }: {
  state: AppState;
  onUpdated(state: AppState): void;
  onCreated(state: AppState): void;
}): JSX.Element {
  const selectedNetwork = getSupportedNetwork(state.expectedNetwork);
  const [mode, setMode] = useState<SetupMode>("import-pq");
  const [password, setPassword] = useState("");
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [hasBackedUpSeed, setHasBackedUpSeed] = useState(false);
  const [privateKeyHex, setPrivateKeyHex] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingSeed, setIsGeneratingSeed] = useState(false);
  const [isChangingNetwork, setIsChangingNetwork] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "create-seed" && !recoveryPhrase) {
      void handleGenerateRecoveryPhrase();
    }
  }, [mode, recoveryPhrase]);

  const canSubmit = !isChangingNetwork && password.trim().length > 0
    && (
      (mode === "create-seed" && Boolean(recoveryPhrase) && hasBackedUpSeed)
      || (mode === "recover-seed" && recoveryPhrase.trim().length > 0)
      || (mode === "import-key" && privateKeyHex.trim().length > 0)
      || mode === "create-pq"
      || (mode === "import-pq" && privateKeyHex.trim().length > 0)
    );

  async function handleGenerateRecoveryPhrase(): Promise<void> {
    setIsGeneratingSeed(true);
    setError(null);
    try {
      const response = await sendWalletMessage<{ recoveryPhrase: string }>({ type: "wallet:generateRecoveryPhrase" });
      setRecoveryPhrase(response.recoveryPhrase);
      setHasBackedUpSeed(false);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to generate a recovery phrase.");
    } finally {
      setIsGeneratingSeed(false);
    }
  }

  async function handleNetworkChange(networkId: SupportedNetworkId): Promise<void> {
    setIsChangingNetwork(true);
    setError(null);
    try {
      const network = getSupportedNetwork(networkId);
      const nextState = await sendWalletMessage<AppState>({
        type: "wallet:updateNode",
        expectedNetwork: networkId,
        nodeApiBaseUrl: network.defaultNodeApiBaseUrl,
      });
      setMode("import-pq");
      onUpdated(nextState);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to change network.");
    } finally {
      setIsChangingNetwork(false);
    }
  }

  async function handleSubmit(): Promise<void> {
    if (!canSubmit || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const state = mode === "create-pq"
        ? await sendWalletMessage<AppState>({ type: "wallet:createPq", password })
        : mode === "import-pq"
          ? await sendWalletMessage<AppState>({ type: "wallet:importPq", password, pqSeedHex: privateKeyHex })
          : mode === "create-seed"
        ? await sendWalletMessage<AppState>({ type: "wallet:createFromSeed", password, recoveryPhrase })
        : mode === "recover-seed"
          ? await sendWalletMessage<AppState>({ type: "wallet:recoverFromSeed", password, recoveryPhrase })
          : await sendWalletMessage<AppState>({ type: "wallet:import", password, privateKeyHex });
      onCreated(state);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to set up the wallet.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <h2>Set Up Wallet</h2>
      <p className="message">Import your {selectedNetwork.label} wallet or create a new ML-DSA-44 wallet. Keep the seed offline.</p>
      <NetworkChoice value={state.expectedNetwork} disabled={isChangingNetwork || isSubmitting} onChange={(network) => void handleNetworkChange(network)} />
      <p className="message">Node API: <span className="mono">{selectedNetwork.defaultNodeApiBaseUrl}</span></p>
      <div className="nav-tabs two-up">
        <button className={mode === "import-pq" ? "is-active wallet-setup-primary" : ""} onClick={() => { setMode("import-pq"); setError(null); }}>
          Import {selectedNetwork.label} Wallet
        </button>
        <button className={mode === "create-pq" ? "is-active" : ""} onClick={() => { setMode("create-pq"); setError(null); }}>
          Create {selectedNetwork.label} Wallet
        </button>
      </div>
      {state.expectedNetwork !== "mainnet" ? (
        <div className="nav-tabs">
          <button className={mode === "create-seed" ? "is-active" : ""} onClick={() => { setMode("create-seed"); setError(null); }}>Create legacy</button>
          <button className={mode === "recover-seed" ? "is-active" : ""} onClick={() => { setMode("recover-seed"); setError(null); }}>Recover legacy</button>
          <button className={mode === "import-key" ? "is-active" : ""} onClick={() => { setMode("import-key"); setError(null); }}>Import legacy key</button>
        </div>
      ) : null}
      {isChangingNetwork ? <p className="message">Checking network…</p> : null}
      <div className="stack">
        {mode === "create-seed" ? (
          <>
            <p className="message">Write down this recovery phrase before continuing. It is the main way to recover this wallet later.</p>
            <textarea readOnly value={recoveryPhrase} />
            <button className="secondary-button" disabled={isGeneratingSeed} onClick={() => void handleGenerateRecoveryPhrase()}>
              {isGeneratingSeed ? "Generating..." : "Generate new phrase"}
            </button>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={hasBackedUpSeed}
                onChange={(event) => setHasBackedUpSeed(event.target.checked)}
              />
              <span>I wrote down this recovery phrase and understand it is required for recovery.</span>
            </label>
          </>
        ) : null}
        {mode === "recover-seed" ? (
          <textarea
            value={recoveryPhrase}
            onChange={(event) => { setRecoveryPhrase(event.target.value); setError(null); }}
            placeholder="Recovery phrase"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
          />
        ) : null}
        {mode === "import-key" ? (
          <>
            <p className="message">This is the fallback path for advanced users. If you have a recovery phrase, use wallet recovery instead.</p>
            <textarea
              value={privateKeyHex}
              onChange={(event) => { setPrivateKeyHex(event.target.value); setError(null); }}
              placeholder="Private key hex"
            />
          </>
        ) : null}
        {mode === "create-pq" ? <p className="message">Create an ML-DSA-44 wallet with a CHCQ address. Back up its seed after creation.</p> : null}
        {mode === "import-pq" ? (
          <>
            <p className="message">Import the 64-character ML-DSA seed hex exported by the Chipcoin CLI.</p>
            <textarea value={privateKeyHex} onChange={(event) => { setPrivateKeyHex(event.target.value); setError(null); }} placeholder="ML-DSA seed hex" />
          </>
        ) : null}
        <input
          type="password"
          value={password}
          onChange={(event) => { setPassword(event.target.value); setError(null); }}
          placeholder="Password"
        />
        <button className="primary-button" disabled={!canSubmit || isSubmitting} onClick={() => void handleSubmit()}>
          {isSubmitting ? "Setting up..." : mode === "create-pq" ? `Create ${selectedNetwork.label} Wallet` : mode === "import-pq" ? `Import ${selectedNetwork.label} Wallet` : mode === "create-seed" ? "Create legacy wallet" : mode === "recover-seed" ? "Recover legacy wallet" : "Import legacy key"}
        </button>
      </div>
      {error ? <p className="message error">{error}</p> : null}
    </section>
  );
}
