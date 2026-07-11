import { describe, expect, it } from "vitest";

import { addressKind, addressToPublicKeyHash, isValidAddress, parseAddress, privateKeyHexToAddress } from "../../src/crypto/addresses";

const FROZEN_CHCQ_ADDRESS = "CHCQCqjJWcT8Jqxvmn9xspxBWnTojXQp93Wqu9sP5F6GkFd1f5xKiRhE";

describe("address helpers", () => {
  it("derives a valid CHC address from private key hex", () => {
    const address = privateKeyHexToAddress("0000000000000000000000000000000000000000000000000000000000000001");
    expect(address.startsWith("CHC")).toBe(true);
    expect(isValidAddress(address)).toBe(true);
  });

  it("rejects malformed addresses", () => {
    expect(isValidAddress("not-a-valid-address")).toBe(false);
  });

  it("parses frozen CHCQ addresses with longest-prefix-first semantics", () => {
    const info = parseAddress(FROZEN_CHCQ_ADDRESS);
    expect(info.kind).toBe("pq");
    expect(info.prefix).toBe("CHCQ");
    expect(info.version).toBe(0x50);
    expect(info.schemeId).toBe(10);
    expect(info.hashOrCommitment).toHaveLength(32);
    expect(addressKind(FROZEN_CHCQ_ADDRESS)).toBe("pq");
    expect(isValidAddress(FROZEN_CHCQ_ADDRESS)).toBe(true);
  });

  it("does not expose CHCQ addresses as legacy public key hashes", () => {
    expect(() => addressToPublicKeyHash(FROZEN_CHCQ_ADDRESS)).toThrow("legacy CHC");
  });
});
