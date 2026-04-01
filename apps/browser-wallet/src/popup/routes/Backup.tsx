import { useState } from "react";

import { copyText } from "../../shared/clipboard";
import { sendWalletMessage } from "../../shared/messages";

const EXPORT_CONFIRMATION_TEXT = "EXPORT";

export function Backup(): JSX.Element {
  const [hasAcknowledgedRisk, setHasAcknowledgedRisk] = useState(false);
  const [confirmationText, setConfirmationText] = useState("");
  const [recoveryPhrase, setRecoveryPhrase] = useState<string | null>(null);
  const [privateKeyHex, setPrivateKeyHex] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const canReveal = hasAcknowledgedRisk && confirmationText.trim().toUpperCase() === EXPORT_CONFIRMATION_TEXT;

  async function handleRevealRecoveryPhrase(): Promise<void> {
    try {
      const response = await sendWalletMessage<{ recoveryPhrase: string }>({
        type: "wallet:exportRecoveryPhrase",
        confirmActiveSession: true,
      });
      setRecoveryPhrase(response.recoveryPhrase);
      setMessage("Recovery phrase revealed. Store it securely.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to reveal the recovery phrase.");
    }
  }

  async function handleReveal(): Promise<void> {
    try {
      const response = await sendWalletMessage<{ privateKeyHex: string }>({
        type: "wallet:exportPrivateKey",
        confirmActiveSession: true,
      });
      setPrivateKeyHex(response.privateKeyHex);
      setMessage("Private key revealed. Store it securely.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to reveal the private key.");
    }
  }

  function handleHide(): void {
    setRecoveryPhrase(null);
    setPrivateKeyHex(null);
    setMessage("Sensitive backup data hidden.");
  }

  return (
    <section className="panel">
      <h2>Backup / Export</h2>
      <div className="warning-panel">
        <p><strong>This is your private key. Anyone with it can take your funds.</strong></p>
        <p>Only reveal it if you are backing up or recovering this wallet on a trusted machine.</p>
      </div>
      <div className="stack">
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={hasAcknowledgedRisk}
            onChange={(event) => setHasAcknowledgedRisk(event.target.checked)}
          />
          <span>I understand that exposing this key gives full control of the wallet.</span>
        </label>
        <label className="stack">
          <span>Type <span className="mono">{EXPORT_CONFIRMATION_TEXT}</span> to enable export.</span>
          <input
            value={confirmationText}
            onChange={(event) => setConfirmationText(event.target.value)}
            placeholder={EXPORT_CONFIRMATION_TEXT}
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
          />
        </label>
        {!recoveryPhrase ? (
          <button className="secondary-button" disabled={!canReveal} onClick={() => void handleRevealRecoveryPhrase()}>
            Reveal recovery phrase
          </button>
        ) : (
          <>
            <textarea className="secret-box" readOnly value={recoveryPhrase} />
            <div className="button-row">
              <button className="secondary-button" onClick={() => void copyText(recoveryPhrase).then(() => setMessage("Recovery phrase copied."))}>
                Copy recovery phrase
              </button>
            </div>
          </>
        )}
        {!privateKeyHex ? (
          <button className="danger-button" disabled={!canReveal} onClick={() => void handleReveal()}>
            Reveal private key
          </button>
        ) : (
          <>
            <textarea className="secret-box" readOnly value={privateKeyHex} />
            <div className="button-row">
              <button className="secondary-button" onClick={() => void copyText(privateKeyHex).then(() => setMessage("Private key copied."))}>
                Copy private key
              </button>
              <button onClick={handleHide}>Hide private key</button>
            </div>
          </>
        )}
      </div>
      {message ? <p className="message">{message}</p> : null}
    </section>
  );
}
