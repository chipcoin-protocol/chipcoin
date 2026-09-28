import type { SupportedNetworkId } from "./constants";

export function normalizeExplorerBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return "";
  }
  try {
    const url = new URL(trimmed);
    url.pathname = url.pathname.replace(/\/api\/(?:devnet|testnet)\/?$/, "").replace(/\/+$/, "");
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return trimmed.replace(/\/api\/(?:devnet|testnet)\/?$/, "");
  }
}

export function explorerTransactionUrl(baseUrl: string, network: SupportedNetworkId, txid: string): string {
  return `${normalizeExplorerBaseUrl(baseUrl)}/#/${network}/tx/${encodeURIComponent(txid)}`;
}

export function explorerAddressUrl(baseUrl: string, network: SupportedNetworkId, address: string): string {
  return `${normalizeExplorerBaseUrl(baseUrl)}/#/${network}/address/${encodeURIComponent(address)}`;
}
