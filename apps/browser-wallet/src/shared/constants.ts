export type SupportedNetworkId = "mainnet" | "devnet" | "testnet";

export interface SupportedNetworkConfig {
  id: SupportedNetworkId;
  label: string;
  defaultEndpointLabel: string;
  defaultNodeApiBaseUrl: string;
  localNodeApiBaseUrl?: string;
  description: string;
  statusLabel: string;
  httpSafetyNote: string;
  chainId: string;
  networkMagicHex: string;
  canonicalGenesisHash: string | null;
}

export const MIN_PASSWORD_LENGTH = 10;
export const DEFAULT_AUTO_LOCK_MINUTES = 30;
export const AUTO_LOCK_MINUTES_OPTIONS = [5, 15, 30, 60, 120] as const;
declare const __CHIPCOIN_DEFAULT_NODE_ENDPOINT__: string;
declare const __CHIPCOIN_DEFAULT_EXPLORER_URL__: string;
export const DEFAULT_NODE_ENDPOINT = __CHIPCOIN_DEFAULT_NODE_ENDPOINT__;
export const DEFAULT_EXPLORER_URL = __CHIPCOIN_DEFAULT_EXPLORER_URL__;
export const DEFAULT_NETWORK: SupportedNetworkId = "testnet";
export const TESTNET_PQ_ACTIVATION_HEIGHT = 20_000;
export const ENABLE_EXPERIMENTAL_BROWSER_MLDSA = true;
export const SUPPORTED_NETWORKS: readonly SupportedNetworkConfig[] = [
  {
    id: "mainnet",
    label: "Mainnet",
    defaultEndpointLabel: "Public Mainnet API",
    defaultNodeApiBaseUrl: "https://mainnet-api.chipcoinprotocol.com",
    localNodeApiBaseUrl: "http://127.0.0.1:28081",
    description: "Production network. ML-DSA-44 wallets and CHCQ addresses are required from genesis.",
    statusLabel: "production mainnet",
    httpSafetyNote: "Use the wallet-safe public mainnet API or a trusted local node. Verify the connected network before signing.",
    chainId: "chipcoin-mainnet-1",
    networkMagicHex: "c0897c0d",
    canonicalGenesisHash: "00000001fb292c1575cc647774e249a7e399b8b2c7b30743bbe9e5090476476d",
  },
  {
    id: "devnet",
    label: "Devnet",
    defaultEndpointLabel: "Public Devnet API",
    defaultNodeApiBaseUrl: DEFAULT_NODE_ENDPOINT,
    description: "Legacy public devnet/fallback environment.",
    statusLabel: "legacy devnet",
    httpSafetyNote: "Public devnet endpoint is provided for convenience and may change.",
    chainId: "chipcoin-devnet-1",
    networkMagicHex: "fac3b6da",
    canonicalGenesisHash: null,
  },
  {
    id: "testnet",
    label: "Testnet",
    defaultEndpointLabel: "Public Testnet API",
    defaultNodeApiBaseUrl: "https://testnet-api.chipcoinprotocol.com",
    localNodeApiBaseUrl: "http://127.0.0.1:28081",
    description: "Public testnet candidate. Uses the wallet-safe public API by default; operators can switch to a local node API.",
    statusLabel: "public testnet candidate",
    httpSafetyNote: "The public testnet API only allows wallet-safe reads and transaction submit. Keep raw node HTTP local/private and do not use the readonly explorer API for wallet submissions.",
    chainId: "chipcoin-testnet-1",
    networkMagicHex: "fab4c0de",
    canonicalGenesisHash: null,
  },
] as const;
export const WALLET_FORMAT_VERSION = 3;
export const SUBMITTED_TX_POLL_ALARM = "chipcoin-submitted-tx-poll";
export const SUBMITTED_TX_POLL_BACKOFF_MS = [
  15_000,
  30_000,
  60_000,
  120_000,
  300_000,
  600_000,
] as const;
export const API_TIMEOUTS_MS = {
  health: 2_000,
  status: 20_000,
  summary: 20_000,
  utxos: 5_000,
  history: 5_000,
  txLookup: 10_000,
  txSubmit: 20_000,
} as const;
export const STORAGE_KEYS = {
  wallet: "chipcoin.wallet",
  settings: "chipcoin.settings",
  submittedTransactions: "chipcoin.submittedTransactions",
  walletDataCache: "chipcoin.walletDataCache",
  watchOnlyAddresses: "chipcoin.watchOnlyAddresses",
  connectedSites: "chipcoin.connectedSites",
  unlockedSession: "chipcoin.unlockedSession",
} as const;

export function isSupportedNetwork(value: string): value is SupportedNetworkId {
  return SUPPORTED_NETWORKS.some((network) => network.id === value);
}

export function getSupportedNetwork(value: string): SupportedNetworkConfig {
  const network = SUPPORTED_NETWORKS.find((entry) => entry.id === value);
  if (!network) {
    throw new Error(`Unsupported Chipcoin network: ${value}.`);
  }
  return network;
}

export function chainIdForNetwork(value: string): string {
  return getSupportedNetwork(value).chainId;
}

export function networkScopedStorageKey(baseKey: string, network: SupportedNetworkId): string {
  return `${baseKey}.${network}`;
}
