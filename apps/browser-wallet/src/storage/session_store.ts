import { DEFAULT_NETWORK, STORAGE_KEYS, networkScopedStorageKey, type SupportedNetworkId } from "../shared/constants";
import { storageGet, storageRemove, storageSet } from "../shared/browser";
import type { SubmittedTransactionRecord } from "../state/app_state";

function submittedTransactionsKey(network: SupportedNetworkId): string {
  return networkScopedStorageKey(STORAGE_KEYS.submittedTransactions, network);
}

export async function loadSubmittedTransactions(network: SupportedNetworkId = DEFAULT_NETWORK): Promise<SubmittedTransactionRecord[]> {
  const scoped = await storageGet<SubmittedTransactionRecord[]>(submittedTransactionsKey(network));
  if (scoped) {
    return scoped;
  }
  if (network === "devnet") {
    return (await storageGet<SubmittedTransactionRecord[]>(STORAGE_KEYS.submittedTransactions)) ?? [];
  }
  return [];
}

export async function saveSubmittedTransactions(
  entries: SubmittedTransactionRecord[],
  network: SupportedNetworkId = DEFAULT_NETWORK,
): Promise<void> {
  await storageSet(submittedTransactionsKey(network), entries);
}

export async function clearSubmittedTransactions(network: SupportedNetworkId = DEFAULT_NETWORK): Promise<void> {
  await storageRemove(submittedTransactionsKey(network));
}

export async function clearAllSubmittedTransactions(): Promise<void> {
  await Promise.all([
    clearSubmittedTransactions("devnet"),
    clearSubmittedTransactions("testnet"),
    storageRemove(STORAGE_KEYS.submittedTransactions),
  ]);
}
