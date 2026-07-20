#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { ml_dsa44 } from "@noble/post-quantum/ml-dsa.js";

function fromHex(hex) {
  return Uint8Array.from(Buffer.from(hex, "hex"));
}

function toHex(bytes) {
  return Buffer.from(bytes).toString("hex");
}

const fixturePath = process.argv[2];
if (!fixturePath) {
  console.error("usage: node scripts/mldsa44-browser-sign-vector.mjs <fixture.json>");
  process.exit(2);
}

const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const seed = fromHex(fixture.seed_hex);
const message = fromHex(fixture.message_hex);
const keyPair = ml_dsa44.keygen(seed);
const signature = ml_dsa44.internal.sign(message, keyPair.secretKey, { extraEntropy: false });

console.log(JSON.stringify({
  public_key_hex: toHex(keyPair.publicKey),
  signature_hex: toHex(signature),
  signature_verifies: ml_dsa44.internal.verify(signature, message, keyPair.publicKey),
}));
