import React from "react";
import { describe, expect, it } from "vitest";

import type { TxLookup } from "../../src/api/types";
import { SchemeBadge } from "../../src/popup/components/SchemeBadge";
import { TransactionDetails } from "../../src/popup/components/TransactionDetails";
import { computeSendFormState } from "../../src/popup/routes/Send";
import {
  classifyAddressScheme,
  classifySignatureScheme,
  classifyTransactionSchemes,
  validateBrowserSendRecipient,
  validateWatchOnlyAddress,
} from "../../src/shared/address_scheme";
import { privateKeyHexToAddress } from "../../src/crypto/addresses";

const LEGACY_ADDRESS = privateKeyHexToAddress("0000000000000000000000000000000000000000000000000000000000000001");
const CHCQ_ADDRESS = "CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE";
const UNKNOWN_CHCQ_ADDRESS = "CHCQCqktC4zFT8vFxMYRRjzSpLkTJ7BNaUjXn8aB1ixNPKTHopwowUgX";

describe("address and signature scheme UI helpers", () => {
  it("classifies legacy CHC addresses", () => {
    expect(classifyAddressScheme({ address: LEGACY_ADDRESS })).toMatchObject({
      kind: "legacy",
      label: "Legacy CHC",
      schemeId: 0,
    });
  });

  it("classifies CHCQ addresses with longest-prefix-first parsing", () => {
    expect(classifyAddressScheme({ address: CHCQ_ADDRESS })).toMatchObject({
      kind: "pq",
      label: "Post-quantum CHCQ",
      schemeId: 10,
    });
  });

  it("classifies unsupported CHCQ scheme ids as unknown", () => {
    expect(classifyAddressScheme({ address: UNKNOWN_CHCQ_ADDRESS })).toMatchObject({
      kind: "unknown",
      label: "Unknown scheme",
      schemeId: 11,
    });
  });

  it("uses API metadata before local parsing", () => {
    expect(classifyAddressScheme({
      address: LEGACY_ADDRESS,
      address_kind: "pq",
      address_scheme_id: 10,
    })).toMatchObject({
      kind: "pq",
      label: "Post-quantum CHCQ",
    });
  });

  it("falls back to local parsing when API metadata is absent", () => {
    expect(classifyAddressScheme({ address: CHCQ_ADDRESS })).toMatchObject({
      kind: "pq",
      schemeId: 10,
    });
  });

  it("classifies ML-DSA-44 signature metadata", () => {
    expect(classifySignatureScheme({ sig_scheme_name: "ML-DSA-44" })).toMatchObject({
      kind: "pq",
      label: "ML-DSA-44",
    });
  });

  it("classifies mixed transaction schemes without inferring PQ from version alone", () => {
    const transaction = makeTxLookup({
      version: 2,
      inputs: [
        { sig_scheme_id: 0, sig_scheme_name: "secp256k1-ecdsa" },
        { sig_scheme_id: 10, sig_scheme_name: "mldsa44" },
      ],
      outputs: [
        { recipient: LEGACY_ADDRESS, address_kind: "legacy", address_scheme_id: 0 },
        { recipient: CHCQ_ADDRESS, address_kind: "pq", address_scheme_id: 10 },
      ],
    }).transaction;

    expect(classifyTransactionSchemes(transaction)).toMatchObject({
      label: "Mixed schemes",
    });
  });
});

describe("scheme badges", () => {
  it("renders a legacy CHC badge", () => {
    const element = SchemeBadge({ scheme: classifyAddressScheme({ address: LEGACY_ADDRESS }) });
    expect(element.props.children).toBe("Legacy CHC");
    expect(element.props.title).toBe("Legacy ECDSA address");
    expect(element.props["aria-label"]).toContain("Legacy CHC");
  });

  it("renders a CHCQ badge with accessible text", () => {
    const element = SchemeBadge({ scheme: classifyAddressScheme({ address: CHCQ_ADDRESS }) });
    expect(element.props.children).toBe("Post-quantum CHCQ");
    expect(element.props.title).toBe("Post-quantum address. Browser signing is not available yet.");
    expect(element.props["aria-label"]).toContain("Browser signing is not available yet");
  });

  it("renders transaction details with input and output scheme badges", () => {
    const element = TransactionDetails({ lookup: makeTxLookup({
      version: 2,
      inputs: [{ sig_scheme_id: 10, sig_scheme_name: "mldsa44" }],
      outputs: [{ recipient: CHCQ_ADDRESS, address_kind: "pq", address_scheme_id: 10 }],
    }) });
    expect(React.isValidElement(element)).toBe(true);
    expect(element.props.className).toBe("transaction-detail");
  });
});

describe("send recipient validation", () => {
  it("allows legacy CHC recipients", () => {
    expect(validateBrowserSendRecipient(LEGACY_ADDRESS)).toMatchObject({
      status: "sendable",
      error: null,
    });
    expect(computeSendFormState({
      connectedNetwork: "testnet",
      expectedNetwork: "testnet",
      recipient: LEGACY_ADDRESS,
      amountChc: "1",
      feeChc: "0.00001",
      isSubmitting: false,
    })).toMatchObject({
      formError: null,
      isSubmitDisabled: false,
    });
  });

  it("recognizes CHCQ as valid but not sendable", () => {
    expect(validateBrowserSendRecipient(CHCQ_ADDRESS)).toMatchObject({
      status: "blocked_pq",
      error: "This is a valid post-quantum CHCQ address, but browser-wallet signing and sending are not enabled yet.",
    });
    expect(computeSendFormState({
      connectedNetwork: "testnet",
      expectedNetwork: "testnet",
      recipient: CHCQ_ADDRESS,
      amountChc: "1",
      feeChc: "0.00001",
      isSubmitting: false,
    })).toMatchObject({
      isSubmitDisabled: true,
      formError: "This is a valid post-quantum CHCQ address, but browser-wallet signing and sending are not enabled yet.",
    });
  });

  it("distinguishes invalid addresses from valid CHCQ recipients", () => {
    expect(validateBrowserSendRecipient("not-a-valid-address")).toMatchObject({
      status: "invalid",
      error: "Recipient must be a valid CHC or CHCQ address.",
    });
  });

  it("blocks unknown schemes with a specific error", () => {
    expect(validateBrowserSendRecipient(UNKNOWN_CHCQ_ADDRESS)).toMatchObject({
      status: "unsupported_scheme",
      error: "Recipient uses an unsupported or unknown address scheme.",
    });
  });
});

describe("watch-only CHCQ validation", () => {
  it("allows supported CHCQ addresses as watch-only", () => {
    expect(validateWatchOnlyAddress(CHCQ_ADDRESS)).toMatchObject({
      status: "watch_only",
      normalizedAddress: CHCQ_ADDRESS,
      error: null,
    });
  });

  it("rejects legacy CHC addresses for CHCQ watch-only tracking", () => {
    expect(validateWatchOnlyAddress(LEGACY_ADDRESS)).toMatchObject({
      status: "not_watch_only",
      error: "Legacy CHC addresses are already managed by the wallet and do not need CHCQ watch-only tracking.",
    });
  });

  it("rejects invalid watch-only addresses distinctly from valid CHCQ", () => {
    expect(validateWatchOnlyAddress("not-a-valid-address")).toMatchObject({
      status: "invalid",
      error: "Enter a valid CHCQ address.",
    });
  });

  it("rejects unsupported CHCQ schemes for watch-only tracking", () => {
    expect(validateWatchOnlyAddress(UNKNOWN_CHCQ_ADDRESS)).toMatchObject({
      status: "unsupported_scheme",
      error: "Only supported CHCQ post-quantum addresses can be added as watch-only.",
    });
  });
});

function makeTxLookup(args: {
  version: number;
  inputs: Array<{ sig_scheme_id?: number; sig_scheme_name?: string | null }>;
  outputs: Array<{ recipient: string; address_kind?: "legacy" | "pq"; address_scheme_id?: number }>;
}): TxLookup {
  return {
    location: "mempool",
    block_hash: null,
    height: null,
    transaction: {
      txid: "aa".repeat(32),
      version: args.version,
      locktime: 0,
      inputs: args.inputs.map((input, index) => ({
        txid: `${index}`.repeat(64).slice(0, 64),
        index,
        sequence: 0xffffffff,
        signature_hex: null,
        public_key_hex: null,
        sig_scheme_id: input.sig_scheme_id,
        sig_scheme_name: input.sig_scheme_name,
      })),
      outputs: args.outputs.map((output) => ({
        value: 100,
        recipient: output.recipient,
        address_kind: output.address_kind,
        address_scheme_id: output.address_scheme_id,
      })),
      metadata: {},
    },
  };
}
