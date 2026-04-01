import { useState } from "react";

import type { AppState } from "../../state/app_state";
import { sendWalletMessage } from "../../shared/messages";

export function SetPassword({
  mode,
  recoveryPhrase,
  privateKeyHex,
  onCreated,
}: {
  mode: "create-seed" | "recover-seed" | "import-key";
  recoveryPhrase?: string;
  privateKeyHex: string;
  onCreated(state: AppState): void;
}): JSX.Element {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(): Promise<void> {
    try {
      const state = mode === "create-seed"
        ? await sendWalletMessage<AppState>({ type: "wallet:createFromSeed", password, recoveryPhrase: recoveryPhrase ?? "" })
        : mode === "recover-seed"
          ? await sendWalletMessage<AppState>({ type: "wallet:recoverFromSeed", password, recoveryPhrase: recoveryPhrase ?? "" })
          : await sendWalletMessage<AppState>({ type: "wallet:import", password, privateKeyHex });
      onCreated(state);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to finish wallet setup.");
    }
  }

  return (
    <section>
      <h2>Set password</h2>
      <p>Your wallet data stays in browser extension storage and is encrypted with this password. The recovery phrase is still your main backup.</p>
      <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" />
      <button onClick={() => void handleSubmit()}>Continue</button>
      {error ? <p>{error}</p> : null}
    </section>
  );
}
