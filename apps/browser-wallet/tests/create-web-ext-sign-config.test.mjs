import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

import { writeSignConfig } from "../scripts/create-web-ext-sign-config.mjs";

test("AMO secret is written only to a private temporary config file", () => {
  const directory = mkdtempSync(join(tmpdir(), "chipcoin-web-ext-config-"));
  try {
    const path = join(directory, "web-ext.config.cjs");
    writeSignConfig(path, "test-secret-not-for-release");
    const mode = statSync(path).mode & 0o777;
    expect(mode).toBe(0o600);
    expect(readFileSync(path, "utf8")).toMatch(/apiSecret/);
    expect(() => writeSignConfig(path, "overwrite")).toThrow();
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("AMO signing config rejects an empty secret", () => {
  const directory = mkdtempSync(join(tmpdir(), "chipcoin-web-ext-config-"));
  try {
    expect(() => writeSignConfig(join(directory, "config.cjs"), "")).toThrow(/required/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("config writer accepts the secret over stdin without requiring an environment variable", () => {
  const directory = mkdtempSync(join(tmpdir(), "chipcoin-web-ext-config-"));
  const path = join(directory, "stdin-config.cjs");
  const testSecret = "stdin-amo-secret-fixture";
  try {
    const result = spawnSync(process.execPath, [
      resolve(dirname(fileURLToPath(import.meta.url)), "../scripts/create-web-ext-sign-config.mjs"),
      path,
    ], { input: testSecret, encoding: "utf8", env: { PATH: process.env.PATH ?? "" } });
    expect(result.status).toBe(0);
    expect(readFileSync(path, "utf8")).toContain(testSecret);
    expect(result.stdout).toBe("");
    expect(result.stderr).toBe("");
    expect(statSync(path).mode & 0o777).toBe(0o600);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("installed web-ext loads apiSecret from config rather than CLI arguments", (context) => {
  const directory = mkdtempSync(join(tmpdir(), "chipcoin-web-ext-config-"));
  const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const configPath = join(directory, "web-ext.config.cjs");
  const testSecret = "dummy-amo-secret-for-config-test";
  try {
    writeSignConfig(configPath, testSecret);
    const result = spawnSync(
      resolve(packageRoot, "node_modules/.bin/web-ext"),
      [
        "sign",
        "--config",
        configPath,
        "--no-config-discovery",
        "--source-dir",
        join(directory, "no-manifest"),
        "--artifacts-dir",
        directory,
        "--channel",
        "unlisted",
        "--api-key",
        "dummy-amo-issuer",
      ],
      { cwd: packageRoot, encoding: "utf8" },
    );
    if (result.error?.code === "EPERM") {
      context.skip("sandbox policy forbids spawning the installed web-ext executable");
      return;
    }
    const output = `${result.stdout ?? ""} ${result.stderr ?? ""}`.replaceAll(testSecret, "[redacted]");
    expect(result.status).not.toBe(0);
    expect(output).toMatch(/manifest|source directory/i);
    expect(output).not.toMatch(/unknown option|api-secret.*required/i);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("Firefox packaging never passes the AMO secret as an option", () => {
  const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const script = readFileSync(join(packageRoot, "package-firefox.sh"), "utf8");
  expect(script).not.toContain("--api-secret");
  expect(script).toContain("--config");
});

test("release wrapper fails closed on ADB actions and options", () => {
  const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const wrapper = join(packageRoot, "scripts/web-ext-release.sh");
  const invalidAction = spawnSync("bash", [wrapper, "run", "--target", "android"], { encoding: "utf8" });
  expect(invalidAction.status).toBe(64);
  const androidOption = spawnSync("bash", [wrapper, "sign", "--android-device", "emulator"], { encoding: "utf8" });
  expect(androidOption.status).toBe(64);
  expect(androidOption.stderr).toMatch(/Android\/ADB-related/);
});
