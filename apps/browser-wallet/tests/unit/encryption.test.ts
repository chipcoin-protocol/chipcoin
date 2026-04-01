import { describe, expect, it } from "vitest";

import { decryptPrivateKeyHex, decryptWalletSecret, encryptPrivateKeyHex, encryptWalletSecret } from "../../src/crypto/encryption";

describe("wallet encryption", () => {
  it("round-trips encrypted private key material", async () => {
    const encrypted = await encryptPrivateKeyHex(
      "0000000000000000000000000000000000000000000000000000000000000001",
      "very-strong-password",
    );

    const decrypted = await decryptPrivateKeyHex(
      encrypted.encryptedWalletBlob,
      "very-strong-password",
      encrypted.saltBase64,
      encrypted.ivBase64,
      encrypted.iterations,
    );

    expect(decrypted).toBe("0000000000000000000000000000000000000000000000000000000000000001");
  });

  it("round-trips encrypted recovery phrase material", async () => {
    const encrypted = await encryptWalletSecret(
      {
        walletType: "seed_phrase",
        recoveryPhrase: "amber-anchor birch-bloom cinder-cabin dawn-drift ember-ember field-fable glint-grove harbor-harvest ivory-island juniper-jewel kindle-kernel linen-lantern meadow-meadow north-nectar opal-orchard pine-prairie ember-orchard",
        accountIndex: 0,
      },
      "very-strong-password",
    );

    const decrypted = await decryptWalletSecret(
      encrypted.encryptedWalletBlob,
      "very-strong-password",
      encrypted.saltBase64,
      encrypted.ivBase64,
      encrypted.iterations,
    );

    expect(decrypted.walletType).toBe("seed_phrase");
    expect(decrypted.recoveryPhrase).toContain("amber-anchor");
    expect(decrypted.accountIndex).toBe(0);
  });
});
