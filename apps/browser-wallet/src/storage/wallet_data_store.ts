import { DEFAULT_NETWORK, STORAGE_KEYS, networkScopedStorageKey, type SupportedNetworkId } from "../shared/constants";
import { storageGet, storageRemove, storageSet } from "../shared/browser";
import type { WalletDataCache } from "../state/app_state";

const EMPTY_WALLET_DATA_CACHE: WalletDataCache = {
  summary: null,
  utxos: [],
  history: [],
  updatedAt: null,
};

function walletDataCacheKey(network: SupportedNetworkId): string {
  return networkScopedStorageKey(STORAGE_KEYS.walletDataCache, network);
}

export async function loadWalletDataCache(network: SupportedNetworkId = DEFAULT_NETWORK): Promise<WalletDataCache> {
  const scoped = await storageGet<WalletDataCache>(walletDataCacheKey(network));
  if (scoped) {
    return scoped;
  }
  if (network === "devnet") {
    return (await storageGet<WalletDataCache>(STORAGE_KEYS.walletDataCache)) ?? EMPTY_WALLET_DATA_CACHE;
  }
  return EMPTY_WALLET_DATA_CACHE;
}

export async function saveWalletDataCache(cache: WalletDataCache, network: SupportedNetworkId = DEFAULT_NETWORK): Promise<void> {
  await storageSet(walletDataCacheKey(network), cache);
}

export async function clearWalletDataCache(network: SupportedNetworkId = DEFAULT_NETWORK): Promise<void> {
  await storageRemove(walletDataCacheKey(network));
}

export async function clearAllWalletDataCaches(): Promise<void> {
  await Promise.all([
    clearWalletDataCache("devnet"),
    clearWalletDataCache("testnet"),
    storageRemove(STORAGE_KEYS.walletDataCache),
  ]);
}
