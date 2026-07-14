import type { TxLookup } from "../api/types";
import { parseAddress } from "../crypto/addresses";

export const LEGACY_ECDSA_SCHEME_ID = 0;
export const ML_DSA_44_SCHEME_ID = 10;

export type SchemeUiKind = "legacy" | "pq" | "unknown";

export interface SchemeUiInfo {
  kind: SchemeUiKind;
  label: string;
  title: string;
  schemeId: number | null;
  schemeName: string | null;
}

export interface AddressSchemeMetadata {
  address?: string | null;
  address_kind?: string | null;
  address_scheme_id?: number | null;
}

export interface SignatureSchemeMetadata {
  sig_scheme_id?: number | null;
  sig_scheme_name?: string | null;
}

export interface SendRecipientValidation {
  status: "empty" | "invalid" | "sendable" | "blocked_pq" | "unsupported_scheme";
  scheme: SchemeUiInfo | null;
  error: string | null;
}

export interface WatchOnlyAddressValidation {
  status: "empty" | "invalid" | "watch_only" | "not_watch_only" | "unsupported_scheme";
  normalizedAddress: string | null;
  scheme: SchemeUiInfo | null;
  error: string | null;
}

const LEGACY_SCHEME: SchemeUiInfo = {
  kind: "legacy",
  label: "Legacy CHC",
  title: "Legacy ECDSA address",
  schemeId: LEGACY_ECDSA_SCHEME_ID,
  schemeName: "secp256k1-ecdsa",
};

const PQ_SCHEME: SchemeUiInfo = {
  kind: "pq",
  label: "Post-quantum CHCQ",
  title: "Post-quantum address. Browser signing is not available yet.",
  schemeId: ML_DSA_44_SCHEME_ID,
  schemeName: "mldsa44",
};

export function unknownScheme(args: { schemeId?: number | null; schemeName?: string | null } = {}): SchemeUiInfo {
  return {
    kind: "unknown",
    label: "Unknown scheme",
    title: "Unsupported or unknown address scheme",
    schemeId: args.schemeId ?? null,
    schemeName: args.schemeName ?? null,
  };
}

export function classifyAddressScheme(metadata: AddressSchemeMetadata): SchemeUiInfo {
  if (metadata.address_kind === "legacy" || metadata.address_scheme_id === LEGACY_ECDSA_SCHEME_ID) {
    return LEGACY_SCHEME;
  }
  if (metadata.address_kind === "pq") {
    return metadata.address_scheme_id === undefined || metadata.address_scheme_id === null || metadata.address_scheme_id === ML_DSA_44_SCHEME_ID
      ? PQ_SCHEME
      : unknownScheme({ schemeId: metadata.address_scheme_id });
  }
  if (metadata.address_scheme_id !== undefined && metadata.address_scheme_id !== null) {
    return metadata.address_scheme_id === ML_DSA_44_SCHEME_ID ? PQ_SCHEME : unknownScheme({ schemeId: metadata.address_scheme_id });
  }
  if (metadata.address_kind) {
    return unknownScheme();
  }

  if (metadata.address) {
    try {
      const parsed = parseAddress(metadata.address);
      if (parsed.kind === "legacy") {
        return LEGACY_SCHEME;
      }
      return parsed.schemeId === ML_DSA_44_SCHEME_ID ? PQ_SCHEME : unknownScheme({ schemeId: parsed.schemeId });
    } catch {
      return unknownScheme();
    }
  }

  return unknownScheme();
}

export function classifySignatureScheme(metadata: SignatureSchemeMetadata): SchemeUiInfo {
  if (metadata.sig_scheme_id === LEGACY_ECDSA_SCHEME_ID) {
    return LEGACY_SCHEME;
  }
  if (metadata.sig_scheme_id === ML_DSA_44_SCHEME_ID || normalizeSchemeName(metadata.sig_scheme_name) === "mldsa44") {
    return {
      ...PQ_SCHEME,
      label: "ML-DSA-44",
      schemeName: metadata.sig_scheme_name ?? PQ_SCHEME.schemeName,
    };
  }
  if (metadata.sig_scheme_id !== undefined && metadata.sig_scheme_id !== null || metadata.sig_scheme_name) {
    return unknownScheme({ schemeId: metadata.sig_scheme_id, schemeName: metadata.sig_scheme_name });
  }
  return unknownScheme();
}

export function classifyTransactionSchemes(transaction: TxLookup["transaction"]): SchemeUiInfo {
  const inputSchemes = transaction.inputs
    .filter((input) => input.sig_scheme_id !== undefined || input.sig_scheme_name)
    .map((input) => classifySignatureScheme(input));
  const outputSchemes = transaction.outputs
    .filter((output) => output.address_kind !== undefined || output.address_scheme_id !== undefined)
    .map((output) => classifyAddressScheme({
      address: output.recipient,
      address_kind: output.address_kind,
      address_scheme_id: output.address_scheme_id,
    }));
  const schemes = [...inputSchemes, ...outputSchemes];
  if (schemes.length === 0) {
    return unknownScheme();
  }
  const distinct = new Set(schemes.map((scheme) => `${scheme.kind}:${scheme.schemeId ?? "none"}:${scheme.schemeName ?? "none"}`));
  if (distinct.size > 1) {
    return {
      kind: "unknown",
      label: "Mixed schemes",
      title: "Transaction contains multiple address or signature schemes",
      schemeId: null,
      schemeName: null,
    };
  }
  return schemes[0];
}

export function transactionVersionLabel(version: number): string {
  if (version === 1) {
    return "v1 legacy";
  }
  if (version === 2) {
    return "v2";
  }
  return `v${version}`;
}

export function validateBrowserSendRecipient(recipient: string): SendRecipientValidation {
  const trimmed = recipient.trim();
  if (!trimmed) {
    return { status: "empty", scheme: null, error: "Recipient address is required." };
  }

  let parsed: ReturnType<typeof parseAddress>;
  try {
    parsed = parseAddress(trimmed);
  } catch {
    return { status: "invalid", scheme: null, error: "Recipient must be a valid CHC or CHCQ address." };
  }

  const scheme = classifyAddressScheme({
    address: trimmed,
    address_kind: parsed.kind,
    address_scheme_id: parsed.schemeId,
  });
  if (scheme.kind === "legacy") {
    return { status: "sendable", scheme, error: null };
  }
  if (scheme.kind === "pq") {
    return {
      status: "blocked_pq",
      scheme,
      error: "This is a valid post-quantum CHCQ address, but browser-wallet signing and sending are not enabled yet.",
    };
  }
  return {
    status: "unsupported_scheme",
    scheme,
    error: "Recipient uses an unsupported or unknown address scheme.",
  };
}

export function validateWatchOnlyAddress(address: string): WatchOnlyAddressValidation {
  const trimmed = address.trim();
  if (!trimmed) {
    return { status: "empty", normalizedAddress: null, scheme: null, error: "Address is required." };
  }

  let parsed: ReturnType<typeof parseAddress>;
  try {
    parsed = parseAddress(trimmed);
  } catch {
    return { status: "invalid", normalizedAddress: null, scheme: null, error: "Enter a valid CHCQ address." };
  }

  const scheme = classifyAddressScheme({
    address: trimmed,
    address_kind: parsed.kind,
    address_scheme_id: parsed.schemeId,
  });
  if (scheme.kind === "pq") {
    return { status: "watch_only", normalizedAddress: trimmed, scheme, error: null };
  }
  if (scheme.kind === "legacy") {
    return {
      status: "not_watch_only",
      normalizedAddress: trimmed,
      scheme,
      error: "Legacy CHC addresses are already managed by the wallet and do not need CHCQ watch-only tracking.",
    };
  }
  return {
    status: "unsupported_scheme",
    normalizedAddress: trimmed,
    scheme,
    error: "Only supported CHCQ post-quantum addresses can be added as watch-only.",
  };
}

function normalizeSchemeName(value: string | null | undefined): string | null {
  return value ? value.toLowerCase().replace(/[^a-z0-9]/g, "") : null;
}
