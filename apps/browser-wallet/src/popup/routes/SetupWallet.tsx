import { useEffect, useState } from "react";

import type { AppState } from "../../state/app_state";
import { DEFAULT_NODE_ENDPOINT } from "../../shared/constants";
import { sendWalletMessage } from "../../shared/messages";

type SetupMode = "create-seed" | "recover-seed" | "import-key";

export function SetupWallet({ onCreated }: { onCreated(state: AppState): void }): JSX.Element {
  const [mode, setMode] = useState<SetupMode>("create-seed");
  const [password, setPassword] = useState("");
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [hasBackedUpSeed, setHasBackedUpSeed] = useState(false);
  const [privateKeyHex, setPrivateKeyHex] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingSeed, setIsGeneratingSeed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "create-seed" && !recoveryPhrase) {
      void handleGenerateRecoveryPhrase();
    }
  }, [mode, recoveryPhrase]);

  const canSubmit = password.trim().length > 0
    && (
      (mode === "create-seed" && Boolean(recoveryPhrase) && hasBackedUpSeed)
      || (mode === "recover-seed" && recoveryPhrase.trim().length > 0)
      || (mode === "import-key" && privateKeyHex.trim().length > 0)
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

  async function handleSubmit(): Promise<void> {
    if (!canSubmit || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const state = mode === "create-seed"
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
      <p className="message">Create a new wallet, recover from a saved recovery phrase, or import a private key as a fallback. The default node is <span className="mono">{DEFAULT_NODE_ENDPOINT}</span>.</p>
      <div className="nav-tabs">
        <button className={mode === "create-seed" ? "is-active" : ""} onClick={() => { setMode("create-seed"); setError(null); }}>
          Create
        </button>
        <button className={mode === "recover-seed" ? "is-active" : ""} onClick={() => { setMode("recover-seed"); setError(null); }}>
          Recover
        </button>
        <button className={mode === "import-key" ? "is-active" : ""} onClick={() => { setMode("import-key"); setError(null); }}>
          Import key
        </button>
      </div>
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
        <input
          type="password"
          value={password}
          onChange={(event) => { setPassword(event.target.value); setError(null); }}
          placeholder="Password"
        />
        <button className="primary-button" disabled={!canSubmit || isSubmitting} onClick={() => void handleSubmit()}>
          {isSubmitting ? "Setting up..." : mode === "create-seed" ? "Create wallet" : mode === "recover-seed" ? "Recover wallet" : "Import private key"}
        </button>
      </div>
      {error ? <p className="message error">{error}</p> : null}
    </section>
  );
}
