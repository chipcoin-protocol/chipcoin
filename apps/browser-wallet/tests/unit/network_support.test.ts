import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NodeStatus } from "../../src/api/types";
import type { SubmittedTransactionRecord, WalletDataCache } from "../../src/state/app_state";

interface InMemoryStorageArea {
  get: (key: string, callback: (result: Record<string, unknown>) => void) => void;
  set: (items: Record<string, unknown>, callback: () => void) => void;
  remove: (key: string, callback: () => void) => void;
}

function installExtensionStorage(): void {
  const storage = new Map<string, unknown>();
  const local: InMemoryStorageArea = {
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

  (globalThis as { chrome?: unknown }).chrome = {
    storage: { local },
    alarms: {
      create: vi.fn(),
      clear: vi.fn(),
    },
  };
}

function nodeStatus(network: "devnet" | "testnet"): NodeStatus {
  return {
    api_version: "1",
    network,
    network_magic_hex: "00",
    height: network === "testnet" ? 1801 : 6539,
    tip_hash: network === "testnet"
      ? "00002087b2dfc6ee2d89c013e9a78f8b26454f9372882f2d61de604b04522847"
      : "00000090b56931663c98b02042a251396417de9dd93e328435648a6eafb83b21",
    current_bits: 0,
    current_target: "0",
    current_difficulty_ratio: "1",
    expected_next_bits: 0,
    expected_next_target: "0",
    cumulative_work: null,
    mempool_size: 0,
    peer_count: 1,
    handshaken_peer_count: 1,
    banned_peer_count: 0,
    sync: {
      mode: "synced",
      validated_tip_height: null,
      validated_tip_hash: null,
      best_header_height: null,
      best_header_hash: null,
      missing_block_count: 0,
      queued_block_count: 0,
      inflight_block_count: 0,
      inflight_block_hashes: [],
      header_peer_count: 0,
      header_peers: [],
      block_peer_count: 0,
      block_peers: [],
      stalled_peers: [],
      download_window: {
        start_height: null,
        end_height: null,
        size: 0,
      },
    },
    next_block_reward_winners: [],
  };
}

function installFetch(network: "devnet" | "testnet"): void {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/v1/health")) {
      return new Response(JSON.stringify({ status: "ok", api_version: "1", network }), { status: 200 });
    }
    if (url.endsWith("/v1/status")) {
      return new Response(JSON.stringify(nodeStatus(network)), { status: 200 });
    }
    if (url.includes("/v1/address/") && url.endsWith("/utxos")) {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url.includes("/v1/address/")) {
      return new Response(JSON.stringify({
        address: "CHCCfW1doC5nV2HXB3m5aJhJdiuQP8ft5dPkL",
        confirmed_balance_chipbits: 0,
        immature_balance_chipbits: 0,
        spendable_balance_chipbits: 0,
        utxo_count: 0,
      }), { status: 200 });
    }
    return new Response(JSON.stringify([]), { status: 200 });
  }));
}

describe("browser wallet network support", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    installExtensionStorage();
  });

  it("uses testnet defaults and persists the selected network", async () => {
    const { loadSettings, saveSettings } = await import("../../src/storage/preferences_store");

    await expect(loadSettings()).resolves.toMatchObject({
      expectedNetwork: "testnet",
      nodeApiBaseUrl: "https://testnet-api.chipcoinprotocol.com",
    });

    await saveSettings({
      expectedNetwork: "devnet",
      nodeApiBaseUrl: "https://api.chipcoinprotocol.com",
      autoLockMinutes: 15,
    });

    await expect(loadSettings()).resolves.toMatchObject({
      expectedNetwork: "devnet",
      nodeApiBaseUrl: "https://api.chipcoinprotocol.com",
    });
  });

  it("accepts a node endpoint only when the selected network matches", async () => {
    installFetch("testnet");
    const session = await import("../../src/background/session");

    await session.createWallet("phase12-password");
    const state = await session.updateNodeEndpoint("https://testnet-api.chipcoinprotocol.com", "testnet");

    expect(state.expectedNetwork).toBe("testnet");
    expect(state.nodeApiBaseUrl).toBe("https://testnet-api.chipcoinprotocol.com");
  });

  it("rejects a node endpoint when the node reports the wrong network", async () => {
    installFetch("devnet");
    const session = await import("../../src/background/session");

    await session.createWallet("phase12-password");

    await expect(session.updateNodeEndpoint("http://127.0.0.1:28081", "testnet")).rejects.toThrow("Wrong network. Expected testnet, got devnet.");
  });

  it("separates submitted transactions and wallet data cache by network", async () => {
    const { loadSubmittedTransactions, saveSubmittedTransactions } = await import("../../src/storage/session_store");
    const { loadWalletDataCache, saveWalletDataCache } = await import("../../src/storage/wallet_data_store");

    const devnetTx: SubmittedTransactionRecord = {
      txid: "aa".repeat(32),
      submittedAt: 1,
      recipient: "CHCCdevnet",
      amountChipbits: 1,
      feeChipbits: 1,
      status: "submitted",
    };
    const testnetTx: SubmittedTransactionRecord = {
      txid: "bb".repeat(32),
      submittedAt: 2,
      recipient: "CHCCtestnet",
      amountChipbits: 2,
      feeChipbits: 1,
      status: "submitted",
    };
    const devnetCache: WalletDataCache = {
      summary: null,
      utxos: [],
      history: [{
        block_height: 10,
        block_hash: "devnet",
        txid: devnetTx.txid,
        incoming_chipbits: 1,
        outgoing_chipbits: 0,
        net_chipbits: 1,
        timestamp: null,
      }],
      updatedAt: 10,
    };
    const testnetCache: WalletDataCache = {
      summary: null,
      utxos: [],
      history: [{
        block_height: 20,
        block_hash: "testnet",
        txid: testnetTx.txid,
        incoming_chipbits: 2,
        outgoing_chipbits: 0,
        net_chipbits: 2,
        timestamp: null,
      }],
      updatedAt: 20,
    };

    await saveSubmittedTransactions([devnetTx], "devnet");
    await saveSubmittedTransactions([testnetTx], "testnet");
    await saveWalletDataCache(devnetCache, "devnet");
    await saveWalletDataCache(testnetCache, "testnet");

    await expect(loadSubmittedTransactions("devnet")).resolves.toEqual([devnetTx]);
    await expect(loadSubmittedTransactions("testnet")).resolves.toEqual([testnetTx]);
    await expect(loadWalletDataCache("devnet")).resolves.toEqual(devnetCache);
    await expect(loadWalletDataCache("testnet")).resolves.toEqual(testnetCache);
  });

  it("falls back to legacy devnet storage without leaking it into testnet", async () => {
    const { STORAGE_KEYS } = await import("../../src/shared/constants");
    const { storageSet } = await import("../../src/shared/browser");
    const { loadSubmittedTransactions } = await import("../../src/storage/session_store");
    const { loadWalletDataCache } = await import("../../src/storage/wallet_data_store");

    const legacyTx: SubmittedTransactionRecord = {
      txid: "cc".repeat(32),
      submittedAt: 3,
      recipient: "CHCClegacy",
      amountChipbits: 3,
      feeChipbits: 1,
      status: "submitted",
    };
    const legacyCache: WalletDataCache = {
      summary: null,
      utxos: [],
      history: [{
        block_height: 30,
        block_hash: "legacy-devnet",
        txid: legacyTx.txid,
        incoming_chipbits: 3,
        outgoing_chipbits: 0,
        net_chipbits: 3,
        timestamp: null,
      }],
      updatedAt: 30,
    };

    await storageSet(STORAGE_KEYS.submittedTransactions, [legacyTx]);
    await storageSet(STORAGE_KEYS.walletDataCache, legacyCache);

    await expect(loadSubmittedTransactions("devnet")).resolves.toEqual([legacyTx]);
    await expect(loadWalletDataCache("devnet")).resolves.toEqual(legacyCache);
    await expect(loadSubmittedTransactions("testnet")).resolves.toEqual([]);
    await expect(loadWalletDataCache("testnet")).resolves.toEqual({
      summary: null,
      utxos: [],
      history: [],
      updatedAt: null,
    });
  });
});
