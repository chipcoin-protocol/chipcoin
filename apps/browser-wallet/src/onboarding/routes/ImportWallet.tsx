import { useState } from "react";

export function ImportWallet({ onContinue, pq = false }: { onContinue(privateKeyHex: string): void; pq?: boolean }): JSX.Element {
  const [privateKeyHex, setPrivateKeyHex] = useState("");
  return (
    <section>
      <h2>{pq ? "Import PQ wallet" : "Import private key"}</h2>
      <p>{pq ? "Import the 32-byte ML-DSA-44 seed exported by the Chipcoin CLI." : "This is the fallback path for advanced users. If you have a recovery phrase, use wallet recovery instead."}</p>
      <textarea value={privateKeyHex} onChange={(event) => setPrivateKeyHex(event.target.value)} placeholder={pq ? "64-character ML-DSA seed hex" : "Private key hex"} />
      <button disabled={!privateKeyHex.trim()} onClick={() => onContinue(privateKeyHex)}>Continue</button>
    </section>
  );
}
