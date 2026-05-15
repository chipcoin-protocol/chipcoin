import {
  DEFAULT_AUTO_LOCK_MINUTES,
  DEFAULT_NETWORK,
  STORAGE_KEYS,
  getSupportedNetwork,
  isSupportedNetwork,
} from "../shared/constants";
import { storageGet, storageSet } from "../shared/browser";
import type { WalletSettings } from "../state/app_state";

const DEFAULT_SETTINGS: WalletSettings = {
  nodeApiBaseUrl: getSupportedNetwork(DEFAULT_NETWORK).defaultNodeApiBaseUrl,
  expectedNetwork: DEFAULT_NETWORK,
  autoLockMinutes: DEFAULT_AUTO_LOCK_MINUTES,
};

export async function loadSettings(): Promise<WalletSettings> {
  const saved = await storageGet<Partial<WalletSettings>>(STORAGE_KEYS.settings);
  const savedNetwork = String(saved?.expectedNetwork ?? "");
  const expectedNetwork = isSupportedNetwork(savedNetwork)
    ? savedNetwork
    : DEFAULT_SETTINGS.expectedNetwork;
  return {
    ...DEFAULT_SETTINGS,
    ...saved,
    expectedNetwork,
    nodeApiBaseUrl: saved?.nodeApiBaseUrl
      ?? getSupportedNetwork(expectedNetwork).defaultNodeApiBaseUrl,
  };
}

export async function saveSettings(settings: WalletSettings): Promise<void> {
  await storageSet(STORAGE_KEYS.settings, settings);
}
