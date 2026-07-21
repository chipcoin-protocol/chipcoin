#!/usr/bin/env node
import { readFileSync } from "node:fs";

import {
  createExperimentalMlDsa44Backend,
} from "../src/crypto/mldsa44";

function fromHex(hex: string): Uint8Array {
  return Uint8Array.from(Buffer.from(hex, "hex"));
}

function toHex(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("hex");
}

const fixturePath = process.argv[2];
if (!fixturePath) {
  console.error("usage: vite-node scripts/mldsa44-browser-sign-vector.ts <fixture.json>");
  process.exit(2);
}

const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const backend = createExperimentalMlDsa44Backend({ enabled: true });
await backend.initialize();
const keyPair = await backend.generateKeyPair(fromHex(fixture.seed_hex));
const digest = fromHex(fixture.message_hex);
const signature = await backend.signDigest(digest, keyPair.privateKey);

console.log(JSON.stringify({
  public_key_hex: toHex(keyPair.publicKey),
  signature_hex: toHex(signature),
  signature_verifies: await backend.verifyDigest(digest, signature, keyPair.publicKey),
}));
