import type { AddressSummary, AddressUtxo, HistoryEntry, NodeStatus } from "../api/types";

export type SubmittedTransactionState = "submitted" | "confirmed" | "rejected" | "failed_to_submit";
export type WalletType = "private_key" | "seed_phrase";

export interface SubmittedTransactionRecord {
  txid: string;
  submittedAt: number;
  recipient: string;
  amountChipbits: number;
  feeChipbits: number;
  status: SubmittedTransactionState;
  confirmedAt?: number;
  errorMessage?: string;
  lastCheckedAt?: number;
  nextCheckAt?: number;
  pollAttempts?: number;
}

export interface WalletSettings {
  nodeApiBaseUrl: string;
  expectedNetwork: string;
  autoLockMinutes: number;
}

export interface EncryptedWalletRecord {
  walletFormatVersion: number;
  walletType: WalletType;
  address: string;
  publicKeyHex: string;
  encryptedWalletBlob: string;
  saltBase64: string;
  ivBase64: string;
  iterations: number;
  accountIndex: number;
  recoveryPhraseWordCount?: number;
  createdAt: number;
}

export interface UnlockedSession {
  walletType: WalletType;
  privateKeyHex: string;
  recoveryPhrase?: string;
  publicKeyHex: string;
  address: string;
  accountIndex: number;
  unlockedAt: number;
  expiresAt: number;
}

export interface WalletOverviewState {
  summary: AddressSummary | null;
  utxos: AddressUtxo[];
  history: HistoryEntry[];
  status: NodeStatus | null;
  submittedTransactions: SubmittedTransactionRecord[];
}

export interface WalletDataCache {
  summary: AddressSummary | null;
  utxos: AddressUtxo[];
  history: HistoryEntry[];
  updatedAt: number | null;
}

export interface AppState {
  hasWallet: boolean;
  isLocked: boolean;
  walletType: WalletType | null;
  accountIndex: number | null;
  recoveryPhraseWordCount: number | null;
  address: string | null;
  nodeApiBaseUrl: string;
  expectedNetwork: string;
  autoLockMinutes: number;
  nodeStatus: NodeStatus | null;
  overview: WalletOverviewState;
}
