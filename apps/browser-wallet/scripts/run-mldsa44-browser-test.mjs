#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

class OperationalError extends Error {}

const browser = parseBrowserArg();
await runCommand("npm", ["run", "build:mldsa:browser-test"]);

try {
  if (browser === "firefox") {
    const result = await runFirefox();
    console.log(JSON.stringify({ browser, ...result }, null, 2));
  } else {
    const chromium = findExecutable(["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]);
    if (!chromium) {
      throw new OperationalError("Chromium/Chrome executable not found. Install chromium or google-chrome to run this test.");
    }
    throw new OperationalError(`Chromium executable found at ${chromium}, but this lightweight runner currently automates Firefox BiDi only.`);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`FAIL  ${browser} ML-DSA browser test`);
  console.error(`reason: ${message}`);
  process.exit(error instanceof OperationalError ? 2 : 1);
}

function parseBrowserArg() {
  const index = process.argv.indexOf("--browser");
  return index === -1 ? "firefox" : process.argv[index + 1];
}

async function runFirefox() {
  const firefox = findExecutable(["firefox", "firefox-esr"]);
  if (!firefox) {
    throw new OperationalError("Firefox executable not found.");
  }
  const profile = mkdtempSync(`${tmpdir()}/chipcoin-mldsa-firefox-`);
  const port = 9232;
  const proc = spawn(firefox, [
    "--headless",
    "--no-remote",
    "--profile",
    profile,
    "--remote-debugging-port",
    String(port),
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  proc.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  try {
    const wsUrl = await waitForFirefoxWebSocket(() => stderr);
    const client = await connectBidi(wsUrl);
    await client.send("session.new", { capabilities: { alwaysMatch: {} } });
    const created = await client.send("browsingContext.create", { type: "tab" });
    const context = created.result?.context;
    if (!context) {
      throw new Error(`Firefox BiDi did not return a browsing context: ${JSON.stringify(created)}`);
    }
    const url = pathToFileURL(resolve("dist-mldsa-browser-test/tests/browser/mldsa44_browser_harness.html")).href;
    await client.send("browsingContext.navigate", { context, url, wait: "complete" });
    const payload = await pollHarnessResult(client, context);
    await client.close();
    if (!payload.ok) {
      throw new Error(`browser harness failed: ${JSON.stringify(payload)}`);
    }
    return payload;
  } finally {
    proc.kill();
    await new Promise((resolveProcess) => {
      proc.once("exit", resolveProcess);
      setTimeout(resolveProcess, 1500);
    });
    rmSync(profile, { recursive: true, force: true });
  }
}

async function pollHarnessResult(client, context) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const response = await client.send("script.evaluate", {
      target: { context },
      expression: "JSON.stringify(window.__CHIPCOIN_MLDSA_BROWSER_RESULT__ ?? null)",
      awaitPromise: true,
    });
    const value = response.result?.result?.value;
    if (typeof value === "string" && value !== "null") {
      return JSON.parse(value);
    }
    await sleep(100);
  }
  throw new Error("browser harness did not produce a result before timeout");
}

async function connectBidi(wsUrl) {
  const url = new URL(wsUrl);
  if (url.pathname === "/") {
    url.pathname = "/session";
  }
  const socket = new WebSocket(url.href);
  await new Promise((resolveOpen, rejectOpen) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", () => {
      rejectOpen(new OperationalError(`could not open Firefox WebDriver BiDi websocket at ${url.href}`));
    }, { once: true });
  });
  let nextId = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  });
  return {
    send(method, params = {}) {
      const id = ++nextId;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolveMessage, rejectMessage) => {
        const timeout = setTimeout(() => {
          pending.delete(id);
          rejectMessage(new Error(`Firefox BiDi command timed out: ${method}`));
        }, 10_000);
        pending.set(id, (message) => {
          clearTimeout(timeout);
          if (message.error) {
            rejectMessage(new Error(`${method} failed: ${JSON.stringify(message)}`));
          } else {
            resolveMessage(message);
          }
        });
      });
    },
    close() {
      socket.close();
    },
  };
}

async function waitForFirefoxWebSocket(stderrProvider) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const match = stderrProvider().match(/WebDriver BiDi listening on (ws:\/\/[^\s]+)/);
    if (match) {
      return match[1];
    }
    await sleep(100);
  }
  throw new Error(`Firefox did not expose WebDriver BiDi endpoint. stderr: ${stderrProvider()}`);
}

function findExecutable(candidates) {
  for (const candidate of candidates) {
    const result = spawnSync("which", [candidate], { encoding: "utf8" });
    if (result.status === 0 && result.stdout.trim()) {
      return result.stdout.trim();
    }
  }
  return null;
}

async function runCommand(command, args) {
  await new Promise((resolveRun, rejectRun) => {
    const proc = spawn(command, args, { stdio: "inherit" });
    proc.on("exit", (code) => {
      if (code === 0) {
        resolveRun();
      } else {
        rejectRun(new Error(`${command} ${args.join(" ")} failed with exit code ${code}`));
      }
    });
    proc.on("error", rejectRun);
  });
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}
