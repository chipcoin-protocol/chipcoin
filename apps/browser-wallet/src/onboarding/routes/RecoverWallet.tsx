import { useState } from "react";

export function RecoverWallet({ onContinue }: { onContinue(recoveryPhrase: string): void }): JSX.Element {
  const [recoveryPhrase, setRecoveryPhrase] = useState("");

  return (
    <section>
      <h2>Recover wallet</h2>
      <p>Paste the recovery phrase for the wallet you want to restore.</p>
      <textarea
        value={recoveryPhrase}
        onChange={(event) => setRecoveryPhrase(event.target.value)}
        placeholder="Recovery phrase"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
      />
      <button disabled={!recoveryPhrase.trim()} onClick={() => onContinue(recoveryPhrase)}>Continue</button>
    </section>
  );
}
