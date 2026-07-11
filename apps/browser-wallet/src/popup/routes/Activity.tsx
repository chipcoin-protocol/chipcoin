import { useEffect, useState } from "react";

import { ChipcoinApiClient } from "../../api/client";
import type { HistoryEntry, TxLookup } from "../../api/types";
import type { AppState } from "../../state/app_state";
import { DEFAULT_EXPLORER_URL } from "../../shared/constants";
import { formatChc, shortHash } from "../../shared/formatting";
import { sendWalletMessage } from "../../shared/messages";
import { unixToIso } from "../../shared/time";
import { AddressWithBadge } from "../components/AddressWithBadge";
import { TransactionDetails } from "../components/TransactionDetails";

export function Activity({ state }: { state: AppState }): JSX.Element {
  const [history, setHistory] = useState<HistoryEntry[]>(state.overview.history);
  const [txDetails, setTxDetails] = useState<Record<string, TxLookup>>({});
  const [isLoadingHistory, setIsLoadingHistory] = useState(state.overview.history.length === 0);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    setHistory(state.overview.history);
    setIsLoadingHistory(state.overview.history.length === 0);
    setHistoryError(null);
  }, [state.overview.history]);

  useEffect(() => {
    let cancelled = false;

    async function loadHistory(): Promise<void> {
      setIsLoadingHistory(true);
      try {
        const next = await sendWalletMessage<HistoryEntry[]>({ type: "wallet:getHistory" });
        if (!cancelled) {
          setHistory(next);
          setHistoryError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHistoryError(error instanceof Error ? error.message : "Unable to load confirmed history.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      }
    }

    void loadHistory();

    return () => {
      cancelled = true;
    };
  }, [state.address, state.nodeApiBaseUrl, state.expectedNetwork]);

  useEffect(() => {
    let cancelled = false;
    const txids = state.overview.submittedTransactions
      .filter((entry) => entry.status === "submitted" || entry.status === "confirmed")
      .slice(0, 5)
      .map((entry) => entry.txid);
    if (txids.length === 0) {
      setTxDetails({});
      return () => {
        cancelled = true;
      };
    }

    async function loadDetails(): Promise<void> {
      const client = ChipcoinApiClient.fromBaseUrl(state.nodeApiBaseUrl);
      const next: Record<string, TxLookup> = {};
      for (const txid of txids) {
        try {
          next[txid] = await client.tx(txid);
        } catch {
          // Details are optional; the compact activity row remains usable.
        }
      }
      if (!cancelled) {
        setTxDetails(next);
      }
    }

    void loadDetails();

    return () => {
      cancelled = true;
    };
  }, [state.nodeApiBaseUrl, state.overview.submittedTransactions]);

  function transactionUrl(txid: string): string {
    const explorerBaseUrl = DEFAULT_EXPLORER_URL.trim().replace(/\/+$/, "");
    if (explorerBaseUrl) {
      return `${explorerBaseUrl}/#/tx/${encodeURIComponent(txid)}`;
    }
    return `${state.nodeApiBaseUrl}/v1/tx/${txid}`;
  }

  return (
    <section className="panel">
      <h2>Activity</h2>
      <h3>Confirmed history</h3>
      {isLoadingHistory ? <p className="message">Loading confirmed history…</p> : historyError ? (
        <p className="message error">{historyError}</p>
      ) : history.length === 0 ? <p className="message">No confirmed history.</p> : (
        <ul className="activity-list">
          {history.map((entry) => (
            <li key={entry.txid}>
              <a className="tx-link" href={transactionUrl(entry.txid)} target="_blank" rel="noreferrer">
                <strong>{shortHash(entry.txid)}</strong>
              </a>{" "}
              {formatChc(entry.net_chipbits)} at {unixToIso(entry.timestamp)}
            </li>
          ))}
        </ul>
      )}
      <h3>Submitted transactions</h3>
      {state.overview.submittedTransactions.length === 0 ? <p className="message">No submitted transactions.</p> : (
        <ul className="activity-list">
          {state.overview.submittedTransactions.map((entry) => (
            <li key={entry.txid}>
              <a className="tx-link" href={transactionUrl(entry.txid)} target="_blank" rel="noreferrer">
                <strong>{shortHash(entry.txid)}</strong>
              </a>{" "}
              {entry.status} · {formatChc(entry.amountChipbits)} to <AddressWithBadge address={entry.recipient} short />
              {txDetails[entry.txid] ? <TransactionDetails lookup={txDetails[entry.txid]} /> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
