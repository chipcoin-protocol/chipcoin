import { sha256 } from "@noble/hashes/sha256";

import { bytesToHex, normalizePrivateKeyHex } from "./keys";

const WORD_PREFIXES = [
  "amber",
  "birch",
  "cinder",
  "dawn",
  "ember",
  "field",
  "glint",
  "harbor",
  "ivory",
  "juniper",
  "kindle",
  "linen",
  "meadow",
  "north",
  "opal",
  "pine",
] as const;

const WORD_SUFFIXES = [
  "anchor",
  "bloom",
  "cabin",
  "drift",
  "ember",
  "fable",
  "grove",
  "harvest",
  "island",
  "jewel",
  "kernel",
  "lantern",
  "meadow",
  "nectar",
  "orchard",
  "prairie",
] as const;

export const RECOVERY_PHRASE_ENTROPY_BYTES = 16;
export const RECOVERY_PHRASE_WORD_COUNT = RECOVERY_PHRASE_ENTROPY_BYTES + 1;

export function generateRecoveryPhrase(): string {
  const entropy = crypto.getRandomValues(new Uint8Array(RECOVERY_PHRASE_ENTROPY_BYTES));
  return encodeRecoveryPhrase(entropy);
}

export function normalizeRecoveryPhrase(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

export function validateRecoveryPhrase(value: string): string {
  return encodeRecoveryPhrase(decodeRecoveryPhrase(value).slice(0, RECOVERY_PHRASE_ENTROPY_BYTES));
}

export function derivePrivateKeyHexFromRecoveryPhrase(recoveryPhrase: string, accountIndex = 0): string {
  if (!Number.isInteger(accountIndex) || accountIndex < 0 || accountIndex > 255) {
    throw new Error("Account index is invalid.");
  }
  const entropy = decodeRecoveryPhrase(recoveryPhrase).slice(0, RECOVERY_PHRASE_ENTROPY_BYTES);
  for (let counter = 0; counter < 256; counter += 1) {
    const digest = sha256(
      new Uint8Array([
        ...new TextEncoder().encode("chipcoin-recovery-v1"),
        ...entropy,
        accountIndex,
        counter,
      ]),
    );
    const candidate = bytesToHex(digest);
    try {
      return normalizePrivateKeyHex(candidate);
    } catch {
      continue;
    }
  }
  throw new Error("Unable to derive a valid wallet key from this recovery phrase.");
}

function encodeRecoveryPhrase(entropy: Uint8Array): string {
  if (entropy.length !== RECOVERY_PHRASE_ENTROPY_BYTES) {
    throw new Error("Recovery phrase entropy has an unexpected length.");
  }
  const checksum = sha256(entropy)[0];
  return [...entropy, checksum].map(byteToRecoveryWord).join(" ");
}

function decodeRecoveryPhrase(value: string): Uint8Array {
  const normalized = normalizeRecoveryPhrase(value);
  const words = normalized ? normalized.split(" ") : [];
  if (words.length !== RECOVERY_PHRASE_WORD_COUNT) {
    throw new Error(`Recovery phrase must contain ${RECOVERY_PHRASE_WORD_COUNT} words.`);
  }
  const bytes = Uint8Array.from(words.map(recoveryWordToByte));
  const entropy = bytes.slice(0, RECOVERY_PHRASE_ENTROPY_BYTES);
  const checksum = bytes[RECOVERY_PHRASE_ENTROPY_BYTES];
  if (sha256(entropy)[0] !== checksum) {
    throw new Error("Recovery phrase checksum is invalid.");
  }
  return bytes;
}

function byteToRecoveryWord(value: number): string {
  return `${WORD_PREFIXES[(value >> 4) & 0x0f]}-${WORD_SUFFIXES[value & 0x0f]}`;
}

function recoveryWordToByte(value: string): number {
  const [prefix, suffix] = value.split("-");
  if (!prefix || !suffix) {
    throw new Error(`Recovery word is invalid: ${value}`);
  }
  const prefixIndex = WORD_PREFIXES.indexOf(prefix as (typeof WORD_PREFIXES)[number]);
  const suffixIndex = WORD_SUFFIXES.indexOf(suffix as (typeof WORD_SUFFIXES)[number]);
  if (prefixIndex === -1 || suffixIndex === -1) {
    throw new Error(`Recovery word is invalid: ${value}`);
  }
  return (prefixIndex << 4) | suffixIndex;
}
