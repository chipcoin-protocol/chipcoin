import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NodeStatus } from "../../src/api/types";
import { publicKeyHexToPqAddress } from "../../src/crypto/addresses";
import { bytesToHex, hexToBytes } from "../../src/crypto/keys";
import { createExperimentalMlDsa44Backend } from "../../src/crypto/mldsa44";
import { transactionSignatureDigest } from "../../src/crypto/serialization";
import type { SubmittedTransactionRecord, WalletDataCache, WatchOnlyAddressRecord } from "../../src/state/app_state";
import { buildSignedPqPaymentTransaction } from "../../src/wallet/build_transaction";

interface InMemoryStorageArea {
  get: (key: string, callback: (result: Record<string, unknown>) => void) => void;
  set: (items: Record<string, unknown>, callback: () => void) => void;
  remove: (key: string, callback: () => void) => void;
}

function storageArea(storage: Map<string, unknown>): InMemoryStorageArea {
  return {
    get: (key, callback) => callback({ [key]: storage.get(key) }),
    set: (items, callback) => {
      for (const [key, value] of Object.entries(items)) {
        storage.set(key, value);
      }
      callback();
    },
    remove: (key, callback) => {
      storage.delete(key);
      callback();
    },
  };
}

function installExtensionStorage(): void {
  const local = new Map<string, unknown>();
  const session = new Map<string, unknown>();
  (globalThis as { chrome?: unknown }).chrome = {
    storage: {
      local: storageArea(local),
      session: storageArea(session),
    },
    alarms: {
      create: vi.fn(),
      clear: vi.fn(),
    },
  };
}

function status(network: "mainnet" | "testnet"): NodeStatus {
  return {
    api_version: "1",
    network,
    network_magic_hex: network === "mainnet" ? "c0897c0d" : "fab4c0de",
    chain_id: network === "mainnet" ? "chipcoin-mainnet-1" : "chipcoin-testnet-1",
    genesis_hash: network === "mainnet"
      ? "00000238ef41c47992581c18fad544b4e24ecf1e79e7ffed629a215def4a337f"
      : null,
    height: 100,
    tip_hash: network === "mainnet" ? "11".repeat(32) : "22".repeat(32),
    current_bits: 0,
    current_target: "0",
    current_difficulty_ratio: "1",
    expected_next_bits: 0,
    expected_next_target: "0",
    cumulative_work: 1,
    mempool_size: 0,
    peer_count: 1,
    handshaken_peer_count: 1,
    banned_peer_count: 0,
    sync: {
      mode: "synced",
      validated_tip_height: 100,
      validated_tip_hash: network === "mainnet" ? "11".repeat(32) : "22".repeat(32),
      best_header_height: 100,
      best_header_hash: network === "mainnet" ? "11".repeat(32) : "22".repeat(32),
      missing_block_count: 0,
      queued_block_count: 0,
      inflight_block_count: 0,
      inflight_block_hashes: [],
      header_peer_count: 1,
      header_peers: [],
      block_peer_count: 1,
      block_peers: [],
      stalled_peers: [],
      download_window: { start_height: null, end_height: null, size: 0 },
    },
    next_block_reward_winners: [],
  };
}

function installFetch(): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const network = url.includes("mainnet") ? "mainnet" : "testnet";
    if (url.endsWith("/v1/health")) {
      return new Response(JSON.stringify({ status: "ok", api_version: "1", network }), { status: 200 });
    }
    if (url.endsWith("/v1/status")) {
      return new Response(JSON.stringify(status(network)), { status: 200 });
    }
    if (url.includes("/v1/address/") && url.endsWith("/utxos")) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url.includes("/v1/address/") && url.endsWith("/history")) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url.includes("/v1/address/")) {
      return new Response(JSON.stringify({
        address: "CHCQ",
        confirmed_balance_chipbits: 0,
        immature_balance_chipbits: 0,
        spendable_balance_chipbits: 0,
        utxo_count: 0,
      }), { status: 200 });
    }
    return new Response(JSON.stringify([]), { status: 200 });
  }));
}

function loginMessage(network: "mainnet" | "testnet", address: string): string {
  const now = Date.now();
  return [
    "Chipcoin Signed Login v1",
    "Domain: chipcoinprotocol.com",
    "Origin: https://chipcoinprotocol.com",
    `Network: ${network}`,
    `Address: ${address}`,
    "Scheme: 10",
    `Nonce: ${network}-replay-test`,
    `Issued At: ${new Date(now - 1_000).toISOString()}`,
    `Expires At: ${new Date(now + 600_000).toISOString()}`,
    "Statement: Sign in to chipcoinprotocol.com",
  ].join("\n");
}

describe("mainnet/testnet wallet and login isolation", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    installExtensionStorage();
    installFetch();
  });

  it("accepts same-network PQ login and rejects both cross-network replay directions", async () => {
    const session = await import("../../src/background/session");
    const { saveSettings } = await import("../../src/storage/preferences_store");
    const { verifyPqLoginMessageSignature } = await import("../../src/provider/login_message");

    const state = await session.importPqWallet("42".repeat(32), "cross-network-password");
    const address = state.address!;

    await saveSettings({
      expectedNetwork: "mainnet",
      nodeApiBaseUrl: "https://mainnet-api.chipcoinprotocol.com",
      autoLockMinutes: 30,
    });
    const mainnetMessage = loginMessage("mainnet", address);
    const mainnetSigned = await session.signProviderLoginMessage({
      message: mainnetMessage,
      origin: "https://chipcoinprotocol.com",
    });
    expect(await verifyPqLoginMessageSignature(
      mainnetSigned.public_key,
      mainnetSigned.signature,
      mainnetMessage,
      "mainnet",
    )).toBe(true);
    expect(await verifyPqLoginMessageSignature(
      mainnetSigned.public_key,
      mainnetSigned.signature,
      mainnetMessage,
      "testnet",
    )).toBe(false);

    await saveSettings({
      expectedNetwork: "testnet",
      nodeApiBaseUrl: "https://testnet-api.chipcoinprotocol.com",
      autoLockMinutes: 30,
    });
    await expect(session.signProviderLoginMessage({
      message: mainnetMessage,
      origin: "https://chipcoinprotocol.com",
    })).rejects.toThrow("UNSUPPORTED_NETWORK");

    const testnetMessage = loginMessage("testnet", address);
    const testnetSigned = await session.signProviderLoginMessage({
      message: testnetMessage,
      origin: "https://chipcoinprotocol.com",
    });
    expect(await verifyPqLoginMessageSignature(
      testnetSigned.public_key,
      testnetSigned.signature,
      testnetMessage,
      "testnet",
    )).toBe(true);
    expect(await verifyPqLoginMessageSignature(
      testnetSigned.public_key,
      testnetSigned.signature,
      testnetMessage,
      "mainnet",
    )).toBe(false);

    await saveSettings({
      expectedNetwork: "mainnet",
      nodeApiBaseUrl: "https://mainnet-api.chipcoinprotocol.com",
      autoLockMinutes: 30,
    });
    await expect(session.signProviderLoginMessage({
      message: testnetMessage,
      origin: "https://chipcoinprotocol.com",
    })).rejects.toThrow("UNSUPPORTED_NETWORK");
  });

  it("fails closed on endpoint network mismatch without silently switching", async () => {
    const session = await import("../../src/background/session");
    const { loadSettings } = await import("../../src/storage/preferences_store");

    await session.importPqWallet("43".repeat(32), "cross-network-password");
    await expect(session.updateNodeEndpoint(
      "https://testnet-api.chipcoinprotocol.com",
      "mainnet",
    )).rejects.toThrow("Wrong network. Expected mainnet, got testnet.");
    await expect(loadSettings()).resolves.toMatchObject({ expectedNetwork: "testnet" });

    await expect(
      session.updateNodeEndpoint("https://mainnet-api.chipcoinprotocol.com", "mainnet"),
    ).resolves.toMatchObject({ expectedNetwork: "mainnet" });
    await expect(loadSettings()).resolves.toMatchObject({ expectedNetwork: "mainnet" });
  });

  it("rejects the same browser-signed PQ transaction signature in the other network domain", async () => {
    const seedHex = "44".repeat(32);
    const backend = createExperimentalMlDsa44Backend();
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(seedHex));
    const address = publicKeyHexToPqAddress(bytesToHex(keyPair.publicKey));
    const utxos = [{
      txid: "77".repeat(32),
      vout: 0,
      amount_chipbits: 5_000_000,
      coinbase: false,
      mature: true,
      status: "unspent" as const,
      origin_height: 1,
    }];

    for (const [sourceNetwork, targetNetwork] of [["mainnet", "testnet"], ["testnet", "mainnet"]] as const) {
      const built = await buildSignedPqPaymentTransaction({
        pqSeedHex: seedHex,
        walletAddress: address,
        recipient: address,
        amountChipbits: 4_000_000,
        feeChipbits: 1_000,
        utxos,
        network: sourceNetwork,
      });
      const unsigned = {
        ...built.transaction,
        inputs: built.transaction.inputs.map((input) => ({ ...input, signatureHex: "", publicKeyHex: "" })),
      };
      const digest = (network: string) => transactionSignatureDigest({
        transaction: unsigned,
        inputIndex: 0,
        previousOutputValue: utxos[0].amount_chipbits,
        previousOutputRecipient: address,
        network,
      });
      const signature = hexToBytes(built.transaction.inputs[0].signatureHex);
      const publicKey = hexToBytes(built.transaction.inputs[0].publicKeyHex);
      const rawBefore = built.rawHex;

      expect(await backend.verifyDigest(digest(sourceNetwork), signature, publicKey)).toBe(true);
      expect(await backend.verifyDigest(digest(targetNetwork), signature, publicKey)).toBe(false);
      expect(built.rawHex).toBe(rawBefore);
    }
  });

  it("preserves isolated persisted state across mainnet to testnet to mainnet switching", async () => {
    const { saveSettings, loadSettings } = await import("../../src/storage/preferences_store");
    const { saveSubmittedTransactions, loadSubmittedTransactions } = await import("../../src/storage/session_store");
    const { saveWalletDataCache, loadWalletDataCache } = await import("../../src/storage/wallet_data_store");
    const { saveWatchOnlyAddressRecords, loadWatchOnlyAddressRecords } = await import("../../src/storage/watch_only_store");

    const mainnetTx: SubmittedTransactionRecord = {
      txid: "aa".repeat(32), submittedAt: 1, recipient: "mainnet", amountChipbits: 10, feeChipbits: 1, status: "submitted",
    };
    const testnetTx: SubmittedTransactionRecord = {
      txid: "bb".repeat(32), submittedAt: 2, recipient: "testnet", amountChipbits: 20, feeChipbits: 1, status: "submitted",
    };
    const mainnetCache: WalletDataCache = { summary: null, utxos: [], history: [], updatedAt: 101 };
    const testnetCache: WalletDataCache = { summary: null, utxos: [], history: [], updatedAt: 202 };
    const mainnetWatch: WatchOnlyAddressRecord[] = [{ address: "CHCQ-mainnet", label: "mainnet", addedAt: 1 }];
    const testnetWatch: WatchOnlyAddressRecord[] = [{ address: "CHCQ-testnet", label: "testnet", addedAt: 2 }];

    await saveSubmittedTransactions([mainnetTx], "mainnet");
    await saveWalletDataCache(mainnetCache, "mainnet");
    await saveWatchOnlyAddressRecords(mainnetWatch, "mainnet");
    await saveSubmittedTransactions([testnetTx], "testnet");
    await saveWalletDataCache(testnetCache, "testnet");
    await saveWatchOnlyAddressRecords(testnetWatch, "testnet");

    await saveSettings({ expectedNetwork: "mainnet", nodeApiBaseUrl: "https://mainnet-api.chipcoinprotocol.com", autoLockMinutes: 30 });
    await expect(loadSettings()).resolves.toMatchObject({ expectedNetwork: "mainnet" });
    await expect(loadSubmittedTransactions("mainnet")).resolves.toEqual([mainnetTx]);
    await expect(loadWalletDataCache("mainnet")).resolves.toEqual(mainnetCache);
    await expect(loadWatchOnlyAddressRecords("mainnet")).resolves.toEqual(mainnetWatch);

    await saveSettings({ expectedNetwork: "testnet", nodeApiBaseUrl: "https://testnet-api.chipcoinprotocol.com", autoLockMinutes: 30 });
    await expect(loadSubmittedTransactions("testnet")).resolves.toEqual([testnetTx]);
    await expect(loadWalletDataCache("testnet")).resolves.toEqual(testnetCache);
    await expect(loadWatchOnlyAddressRecords("testnet")).resolves.toEqual(testnetWatch);

    await saveSettings({ expectedNetwork: "mainnet", nodeApiBaseUrl: "https://mainnet-api.chipcoinprotocol.com", autoLockMinutes: 30 });
    await expect(loadSubmittedTransactions("mainnet")).resolves.toEqual([mainnetTx]);
    await expect(loadWalletDataCache("mainnet")).resolves.toEqual(mainnetCache);
    await expect(loadWatchOnlyAddressRecords("mainnet")).resolves.toEqual(mainnetWatch);
  });
});
