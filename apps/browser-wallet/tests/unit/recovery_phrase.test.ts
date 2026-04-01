import { describe, expect, it } from "vitest";

import {
  RECOVERY_PHRASE_WORD_COUNT,
  derivePrivateKeyHexFromRecoveryPhrase,
  validateRecoveryPhrase,
} from "../../src/crypto/recovery_phrase";

const FIXED_RECOVERY_PHRASE = [
  "amber-anchor",
  "amber-bloom",
  "amber-cabin",
  "amber-drift",
  "amber-ember",
  "amber-fable",
  "amber-grove",
  "amber-harvest",
  "amber-island",
  "amber-jewel",
  "amber-kernel",
  "amber-lantern",
  "amber-meadow",
  "amber-nectar",
  "amber-orchard",
  "amber-prairie",
  "linen-orchard",
].join(" ");

describe("recovery phrase", () => {
  it("normalizes and validates one fixed phrase", () => {
    expect(validateRecoveryPhrase(`  ${FIXED_RECOVERY_PHRASE.toUpperCase()}  `)).toBe(FIXED_RECOVERY_PHRASE);
    expect(FIXED_RECOVERY_PHRASE.split(" ")).toHaveLength(RECOVERY_PHRASE_WORD_COUNT);
  });

  it("derives the same private key from the same phrase", () => {
    expect(derivePrivateKeyHexFromRecoveryPhrase(FIXED_RECOVERY_PHRASE)).toBe(
      derivePrivateKeyHexFromRecoveryPhrase(FIXED_RECOVERY_PHRASE),
    );
  });

  it("rejects invalid recovery phrases", () => {
    expect(() => validateRecoveryPhrase("amber-anchor birch-bloom")).toThrow("Recovery phrase must contain");
    expect(() => validateRecoveryPhrase(`${FIXED_RECOVERY_PHRASE} extra-word`)).toThrow("Recovery phrase must contain");
    expect(() => validateRecoveryPhrase(FIXED_RECOVERY_PHRASE.replace("linen-orchard", "linen-prairie"))).toThrow("Recovery phrase checksum is invalid");
  });
});
