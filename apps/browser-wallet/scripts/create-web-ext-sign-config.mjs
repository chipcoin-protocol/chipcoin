#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export function writeSignConfig(path, secret) {
  if (typeof secret !== "string" || secret.length === 0) {
    throw new Error("AMO signing secret is required");
  }
  const contents = `module.exports = ${JSON.stringify({ sign: { apiSecret: secret } })};\n`;
  writeFileSync(path, contents, { encoding: "utf8", flag: "wx", mode: 0o600 });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const outputPath = process.argv[2];
  if (!outputPath) {
    process.exitCode = 2;
  } else {
    try {
      writeSignConfig(outputPath, readFileSync(0, "utf8"));
    } catch {
      process.exitCode = 1;
    }
  }
}
