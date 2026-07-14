import { DEFAULT_NETWORK, STORAGE_KEYS, networkScopedStorageKey, type SupportedNetworkId } from "../shared/constants";
import { storageGet, storageRemove, storageSet } from "../shared/browser";
import type { WatchOnlyAddressRecord } from "../state/app_state";

function watchOnlyStorageKey(network: SupportedNetworkId): string {
  return networkScopedStorageKey(STORAGE_KEYS.watchOnlyAddresses, network);
}

export async function loadWatchOnlyAddressRecords(
  network: SupportedNetworkId = DEFAULT_NETWORK,
): Promise<WatchOnlyAddressRecord[]> {
  return (await storageGet<WatchOnlyAddressRecord[]>(watchOnlyStorageKey(network))) ?? [];
}

export async function saveWatchOnlyAddressRecords(
  records: WatchOnlyAddressRecord[],
  network: SupportedNetworkId = DEFAULT_NETWORK,
): Promise<void> {
  await storageSet(watchOnlyStorageKey(network), records);
}

export async function clearAllWatchOnlyAddressRecords(): Promise<void> {
  await Promise.all([
    storageRemove(watchOnlyStorageKey("devnet")),
    storageRemove(watchOnlyStorageKey("testnet")),
    storageRemove(STORAGE_KEYS.watchOnlyAddresses),
  ]);
}
