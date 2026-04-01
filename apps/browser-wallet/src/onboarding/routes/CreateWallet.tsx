import { useEffect, useState } from "react";

import { sendWalletMessage } from "../../shared/messages";

export function CreateWallet({ onContinue }: { onContinue(recoveryPhrase: string): void }): JSX.Element {
  const [recoveryPhrase, setRecoveryPhrase] = useState("");
  const [hasBackedUpSeed, setHasBackedUpSeed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void regenerateRecoveryPhrase();
  }, []);

  async function regenerateRecoveryPhrase(): Promise<void> {
    try {
      setError(null);
      const response = await sendWalletMessage<{ recoveryPhrase: string }>({ type: "wallet:generateRecoveryPhrase" });
      setRecoveryPhrase(response.recoveryPhrase);
      setHasBackedUpSeed(false);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to generate a recovery phrase.");
    }
  }

  return (
    <section>
      <h2>Create wallet</h2>
      <p>Write down this recovery phrase before you continue. It is the main way to recover this wallet later.</p>
      <textarea readOnly value={recoveryPhrase} />
      <div className="button-row">
        <button onClick={() => void regenerateRecoveryPhrase()}>Generate new phrase</button>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={hasBackedUpSeed}
          onChange={(event) => setHasBackedUpSeed(event.target.checked)}
        />
        <span>I wrote down this recovery phrase and understand it is required for recovery.</span>
      </label>
      <button disabled={!recoveryPhrase || !hasBackedUpSeed} onClick={() => onContinue(recoveryPhrase)}>Continue</button>
      {error ? <p>{error}</p> : null}
    </section>
  );
}
