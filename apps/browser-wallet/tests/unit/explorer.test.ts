import { describe, expect, it } from "vitest";

import {
  explorerAddressUrl,
  explorerTransactionUrl,
  normalizeExplorerBaseUrl,
} from "../../src/shared/explorer";

describe("explorer links", () => {
  it("uses the public explorer route with an explicit network", () => {
    expect(explorerTransactionUrl("https://explorer.chipcoinprotocol.com", "testnet", "abc"))
      .toBe("https://explorer.chipcoinprotocol.com/#/testnet/tx/abc");
  });

  it("removes a readonly API suffix from the configured explorer URL", () => {
    expect(normalizeExplorerBaseUrl("https://explorer.chipcoinprotocol.com/api/testnet/"))
      .toBe("https://explorer.chipcoinprotocol.com");
    expect(explorerAddressUrl("https://explorer.chipcoinprotocol.com/api/testnet", "testnet", "CHCQ example"))
      .toBe("https://explorer.chipcoinprotocol.com/#/testnet/address/CHCQ%20example");
  });
});
