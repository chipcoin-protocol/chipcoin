import { useState } from "react";

export function ImportWallet({ onContinue }: { onContinue(privateKeyHex: string): void }): JSX.Element {
  const [privateKeyHex, setPrivateKeyHex] = useState("");
  return (
    <section>
      <h2>Import private key</h2>
      <p>This is the fallback path for advanced users. If you have a recovery phrase, use wallet recovery instead.</p>
      <textarea value={privateKeyHex} onChange={(event) => setPrivateKeyHex(event.target.value)} placeholder="Private key hex" />
      <button disabled={!privateKeyHex.trim()} onClick={() => onContinue(privateKeyHex)}>Continue</button>
    </section>
  );
}
