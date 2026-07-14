import { useState } from "react";

import type { AppState } from "../../state/app_state";
import { DEFAULT_EXPLORER_URL, TESTNET_PQ_ACTIVATION_HEIGHT } from "../../shared/constants";
import { formatChc, shortHash } from "../../shared/formatting";
import { sendWalletMessage } from "../../shared/messages";
import { unixToIso } from "../../shared/time";
import { validateWatchOnlyAddress } from "../../shared/address_scheme";
import { AddressWithBadge } from "../components/AddressWithBadge";

export function WatchOnly(
  { state, onUpdated }: { state: AppState; onUpdated(state: AppState): void },
): JSX.Element {
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const trimmedAddress = address.trim();
  const validation = validateWatchOnlyAddress(trimmedAddress);
  const watchOnlyAddresses = state.watchOnlyAddresses ?? [];
  const canAdd = validation.status === "watch_only" && !isSaving;

  async function handleAdd(): Promise<void> {
    const submitValidation = validateWatchOnlyAddress(trimmedAddress);
    if (submitValidation.status !== "watch_only" || !submitValidation.normalizedAddress) {
      setError(submitValidation.error ?? "Only supported CHCQ post-quantum addresses can be added as watch-only.");
      setMessage(null);
      return;
    }
    setIsSaving(true);
    try {
      const nextState = await sendWalletMessage<AppState>({
        type: "wallet:addWatchOnlyAddress",
        address: submitValidation.normalizedAddress,
        label,
      });
      onUpdated(nextState);
      setAddress("");
      setLabel("");
      setError(null);
      setMessage("CHCQ watch-only address added.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to add watch-only address.");
      setMessage(null);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRemove(removeAddress: string): Promise<void> {
    setIsSaving(true);
    try {
      const nextState = await sendWalletMessage<AppState>({ type: "wallet:removeWatchOnlyAddress", address: removeAddress });
      onUpdated(nextState);
      setError(null);
      setMessage("Watch-only address removed.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Unable to remove watch-only address.");
      setMessage(null);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="panel">
      <h2>Watch-only CHCQ</h2>
      <p className="message">
        Track CHCQ balances and history without importing keys. Browser wallet ML-DSA signing is not available yet,
        and consensus CHCQ outputs are scheduled for testnet height {TESTNET_PQ_ACTIVATION_HEIGHT}.
      </p>
      <div className="stack">
        <label className="stack">
          <span>CHCQ address</span>
          <input
            value={address}
            onChange={(event) => { setAddress(event.target.value); setError(null); setMessage(null); }}
            placeholder="CHCQ..."
          />
        </label>
        {trimmedAddress && validation.scheme ? (
          <p className="message recipient-status">
            Address: <AddressWithBadge address={trimmedAddress} />
          </p>
        ) : null}
        {trimmedAddress && validation.error ? <p className="message error">{validation.error}</p> : null}
        <label className="stack">
          <span>Label</span>
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Optional local label"
          />
        </label>
        <button className="primary-button" disabled={!canAdd} onClick={() => void handleAdd()}>
          {isSaving ? "Saving..." : "Add watch-only address"}
        </button>
      </div>
      {error ? <p className="message error">{error}</p> : null}
      {message ? <p className="message">{message}</p> : null}

      <h3>Tracked addresses</h3>
      {watchOnlyAddresses.length === 0 ? <p className="message">No CHCQ watch-only addresses.</p> : (
        <div className="watch-list">
          {watchOnlyAddresses.map((entry) => (
            <article className="watch-card" key={entry.address}>
              <div className="inline-row">
                <p>
                  {entry.label ? <strong>{entry.label}</strong> : <strong>CHCQ watch-only</strong>}<br />
                  <AddressWithBadge
                    address={entry.address}
                    metadata={{
                      address_kind: entry.summary?.address_kind,
                      address_scheme_id: entry.summary?.address_scheme_id,
                    }}
                  />
                </p>
                <button className="secondary-button" disabled={isSaving} onClick={() => void handleRemove(entry.address)}>
                  Remove
                </button>
              </div>
              {entry.error ? <p className="message error">{entry.error}</p> : (
                <div className="metric-grid">
                  <div className="metric-card">
                    <span className="metric-label">Confirmed</span>
                    <strong>{formatChc(entry.summary?.confirmed_balance_chipbits ?? 0)}</strong>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">Spendable in browser</span>
                    <strong>Not available</strong>
                  </div>
                </div>
              )}
              <p className="message">
                <a className="tx-link" href={addressExplorerUrl(state, entry.address)} target="_blank" rel="noreferrer">
                  Open in explorer
                </a>
              </p>
              <h4>Recent history</h4>
              {entry.history.length === 0 ? <p className="message">No recent history.</p> : (
                <ul className="activity-list">
                  {entry.history.slice(0, 5).map((historyEntry) => (
                    <li key={`${entry.address}-${historyEntry.txid}`}>
                      <a className="tx-link" href={txExplorerUrl(state, historyEntry.txid)} target="_blank" rel="noreferrer">
                        <strong>{shortHash(historyEntry.txid)}</strong>
                      </a>{" "}
                      {formatChc(historyEntry.net_chipbits)} at {unixToIso(historyEntry.timestamp)}
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function explorerBaseUrl(): string {
  return DEFAULT_EXPLORER_URL.trim().replace(/\/+$/, "");
}

function addressExplorerUrl(state: AppState, address: string): string {
  const base = explorerBaseUrl();
  if (base) {
    return `${base}/#/${state.expectedNetwork}/address/${encodeURIComponent(address)}`;
  }
  return `${state.nodeApiBaseUrl}/v1/address/${address}`;
}

function txExplorerUrl(state: AppState, txid: string): string {
  const base = explorerBaseUrl();
  if (base) {
    return `${base}/#/${state.expectedNetwork}/tx/${encodeURIComponent(txid)}`;
  }
  return `${state.nodeApiBaseUrl}/v1/tx/${txid}`;
}
