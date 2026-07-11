import { ripemd160 } from "@noble/hashes/ripemd160";
import { sha256 } from "@noble/hashes/sha256";

import { bytesToHex, derivePublicKeyHex, hexToBytes } from "./keys";

const ADDRESS_PREFIX = "CHC";
const ADDRESS_VERSION = 0x1c;
const PQ_ADDRESS_PREFIX = "CHCQ";
const PQ_ADDRESS_VERSION = 0x50;
const PQ_PUBLIC_KEY_COMMITMENT_SIZE = 32;
const BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

export type AddressKind = "legacy" | "pq";

export interface AddressInfo {
  prefix: string;
  version: number;
  schemeId: number;
  kind: AddressKind;
  hashOrCommitment: Uint8Array;
}

export function privateKeyHexToAddress(privateKeyHex: string): string {
  return publicKeyHexToAddress(derivePublicKeyHex(privateKeyHex));
}

export function publicKeyHexToAddress(publicKeyHex: string): string {
  const publicKeyBytes = hexToBytes(publicKeyHex);
  const payload = new Uint8Array(21);
  payload[0] = ADDRESS_VERSION;
  payload.set(hash160(publicKeyBytes), 1);
  return ADDRESS_PREFIX + base58CheckEncode(payload);
}

export function isValidAddress(address: string): boolean {
  try {
    void parseAddress(address);
    return true;
  } catch {
    return false;
  }
}

export function parseAddress(address: string): AddressInfo {
  if (address.startsWith(PQ_ADDRESS_PREFIX)) {
    const payload = base58CheckDecode(address.slice(PQ_ADDRESS_PREFIX.length));
    if (payload.length !== 2 + PQ_PUBLIC_KEY_COMMITMENT_SIZE) {
      throw new Error("CHCQ address payload has an unexpected length.");
    }
    if (payload[0] !== PQ_ADDRESS_VERSION) {
      throw new Error("CHCQ address version byte is not recognised.");
    }
    return {
      prefix: PQ_ADDRESS_PREFIX,
      version: payload[0],
      schemeId: payload[1],
      kind: "pq",
      hashOrCommitment: payload.slice(2),
    };
  }

  if (!address.startsWith(ADDRESS_PREFIX)) {
    throw new Error("Address does not start with a recognised Chipcoin prefix.");
  }
  const payload = base58CheckDecode(address.slice(ADDRESS_PREFIX.length));
  if (payload.length !== 21) {
    throw new Error("Address payload has an unexpected length.");
  }
  if (payload[0] !== ADDRESS_VERSION) {
    throw new Error("Address version byte is not recognised.");
  }
  return {
    prefix: ADDRESS_PREFIX,
    version: payload[0],
    schemeId: 0,
    kind: "legacy",
    hashOrCommitment: payload.slice(1),
  };
}

export function addressKind(address: string): AddressKind {
  return parseAddress(address).kind;
}

export function addressToPublicKeyHash(address: string): Uint8Array {
  const info = parseAddress(address);
  if (info.kind !== "legacy") {
    throw new Error("Address is not a legacy CHC address.");
  }
  return info.hashOrCommitment;
}

function hash160(payload: Uint8Array): Uint8Array {
  return ripemd160(sha256(payload));
}

function doubleSha256(payload: Uint8Array): Uint8Array {
  return sha256(sha256(payload));
}

function base58CheckEncode(payload: Uint8Array): string {
  const checksum = doubleSha256(payload).slice(0, 4);
  const data = new Uint8Array(payload.length + checksum.length);
  data.set(payload);
  data.set(checksum, payload.length);

  let zeros = 0;
  while (zeros < data.length && data[zeros] === 0) {
    zeros += 1;
  }

  let value = BigInt(`0x${bytesToHex(data) || "0"}`);
  let encoded = "";
  while (value > 0n) {
    const remainder = Number(value % 58n);
    encoded = BASE58_ALPHABET[remainder] + encoded;
    value /= 58n;
  }
  return `${"1".repeat(zeros)}${encoded || "1"}`;
}

function base58CheckDecode(value: string): Uint8Array {
  let number = 0n;
  for (const character of value) {
    const index = BASE58_ALPHABET.indexOf(character);
    if (index === -1) {
      throw new Error("Address contains a non-Base58 character.");
    }
    number = number * 58n + BigInt(index);
  }

  let hex = number.toString(16);
  if (hex.length % 2 !== 0) {
    hex = `0${hex}`;
  }
  const zeroPrefixCount = value.length - value.replace(/^1+/, "").length;
  const raw = zeroPrefixCount > 0
    ? new Uint8Array([...new Uint8Array(zeroPrefixCount), ...hexToBytes(hex)])
    : hexToBytes(hex);
  if (raw.length < 5) {
    throw new Error("Address payload is too short.");
  }
  const payload = raw.slice(0, -4);
  const checksum = raw.slice(-4);
  const expected = doubleSha256(payload).slice(0, 4);
  if (bytesToHex(expected) !== bytesToHex(checksum)) {
    throw new Error("Address checksum is invalid.");
  }
  return payload;
}
