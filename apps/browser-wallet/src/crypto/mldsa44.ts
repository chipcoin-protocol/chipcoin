import { ml_dsa44 } from "@noble/post-quantum/ml-dsa.js";

import { ENABLE_EXPERIMENTAL_BROWSER_MLDSA } from "../shared/constants";

export const ML_DSA_44_SCHEME_ID = 10;
export const ML_DSA_44_SCHEME_NAME = "mldsa44";
export const ML_DSA_44_SEED_SIZE = 32;
export const ML_DSA_44_PUBLIC_KEY_SIZE = 1312;
export const ML_DSA_44_PRIVATE_KEY_SIZE = 2560;
export const ML_DSA_44_SIGNATURE_SIZE = 2420;

export type MlDsa44ErrorCode =
  | "backend_unavailable"
  | "feature_disabled"
  | "invalid_message"
  | "invalid_private_key"
  | "invalid_public_key"
  | "invalid_seed"
  | "invalid_signature"
  | "not_initialized"
  | "unsupported_scheme";

export class MlDsa44BackendError extends Error {
  constructor(readonly code: MlDsa44ErrorCode, message: string) {
    super(message);
    this.name = "MlDsa44BackendError";
  }
}

export interface MlDsa44KeyPair {
  publicKey: Uint8Array;
  privateKey: Uint8Array;
}

export interface MlDsa44Backend {
  initialize(): Promise<void>;
  generateKeyPair(seed?: Uint8Array): Promise<MlDsa44KeyPair>;
  sign(message: Uint8Array, privateKey: Uint8Array): Promise<Uint8Array>;
  verify(message: Uint8Array, signature: Uint8Array, publicKey: Uint8Array): Promise<boolean>;
}

export interface MlDsa44BenchmarkResult {
  initMs: number;
  keygenMs: number;
  signMs: number;
  verifyMs: number;
}

interface BackendOptions {
  enabled?: boolean;
}

export function createExperimentalMlDsa44Backend(options: BackendOptions = {}): MlDsa44Backend {
  let initialized = false;
  let initializing: Promise<void> | null = null;
  const enabled = options.enabled ?? ENABLE_EXPERIMENTAL_BROWSER_MLDSA;

  async function initialize(): Promise<void> {
    if (!enabled) {
      throw new MlDsa44BackendError("feature_disabled", "Experimental browser ML-DSA-44 is disabled.");
    }
    if (initialized) {
      return;
    }
    if (!initializing) {
      initializing = Promise.resolve().then(() => {
        if (!ml_dsa44?.internal) {
          throw new MlDsa44BackendError("backend_unavailable", "ML-DSA-44 backend is not available.");
        }
        if (ml_dsa44.lengths.seed !== ML_DSA_44_SEED_SIZE
          || ml_dsa44.lengths.publicKey !== ML_DSA_44_PUBLIC_KEY_SIZE
          || ml_dsa44.lengths.secretKey !== ML_DSA_44_PRIVATE_KEY_SIZE
          || ml_dsa44.lengths.signature !== ML_DSA_44_SIGNATURE_SIZE) {
          throw new MlDsa44BackendError("backend_unavailable", "ML-DSA-44 backend constants do not match Chipcoin.");
        }
        initialized = true;
      }).finally(() => {
        initializing = null;
      });
    }
    await initializing;
  }

  function ensureInitialized(): void {
    if (!initialized) {
      throw new MlDsa44BackendError("not_initialized", "Initialize ML-DSA-44 before using it.");
    }
  }

  return {
    initialize,
    async generateKeyPair(seed?: Uint8Array): Promise<MlDsa44KeyPair> {
      ensureInitialized();
      if (seed !== undefined) {
        expectBytes(seed, ML_DSA_44_SEED_SIZE, "invalid_seed", "ML-DSA-44 seed");
      }
      const keyPair = ml_dsa44.keygen(seed);
      return {
        publicKey: copyBytes(keyPair.publicKey),
        privateKey: copyBytes(keyPair.secretKey),
      };
    },
    async sign(message: Uint8Array, privateKey: Uint8Array): Promise<Uint8Array> {
      ensureInitialized();
      expectBytes(message, ML_DSA_44_SEED_SIZE, "invalid_message", "Chipcoin ML-DSA signing digest");
      expectBytes(privateKey, ML_DSA_44_PRIVATE_KEY_SIZE, "invalid_private_key", "ML-DSA-44 private key");
      return copyBytes(ml_dsa44.internal.sign(message, privateKey, { extraEntropy: false }));
    },
    async verify(message: Uint8Array, signature: Uint8Array, publicKey: Uint8Array): Promise<boolean> {
      ensureInitialized();
      expectBytes(message, ML_DSA_44_SEED_SIZE, "invalid_message", "Chipcoin ML-DSA signing digest");
      expectBytes(signature, ML_DSA_44_SIGNATURE_SIZE, "invalid_signature", "ML-DSA-44 signature");
      expectBytes(publicKey, ML_DSA_44_PUBLIC_KEY_SIZE, "invalid_public_key", "ML-DSA-44 public key");
      return ml_dsa44.internal.verify(signature, message, publicKey);
    },
  };
}

export async function benchmarkMlDsa44Backend(iterations = 3): Promise<MlDsa44BenchmarkResult> {
  const backend = createExperimentalMlDsa44Backend({ enabled: true });
  const seed = new Uint8Array(ML_DSA_44_SEED_SIZE);
  const message = new Uint8Array(ML_DSA_44_SEED_SIZE);
  const initStart = performance.now();
  await backend.initialize();
  const initMs = performance.now() - initStart;

  const keygenStart = performance.now();
  let keyPair: MlDsa44KeyPair | null = null;
  for (let index = 0; index < iterations; index += 1) {
    keyPair = await backend.generateKeyPair(seed);
  }
  const keygenMs = (performance.now() - keygenStart) / iterations;
  if (!keyPair) {
    throw new MlDsa44BackendError("backend_unavailable", "ML-DSA-44 benchmark did not produce a keypair.");
  }

  const signStart = performance.now();
  let signature: Uint8Array | null = null;
  for (let index = 0; index < iterations; index += 1) {
    signature = await backend.sign(message, keyPair.privateKey);
  }
  const signMs = (performance.now() - signStart) / iterations;
  if (!signature) {
    throw new MlDsa44BackendError("backend_unavailable", "ML-DSA-44 benchmark did not produce a signature.");
  }

  const verifyStart = performance.now();
  for (let index = 0; index < iterations; index += 1) {
    await backend.verify(message, signature, keyPair.publicKey);
  }
  const verifyMs = (performance.now() - verifyStart) / iterations;

  zeroBytes(seed, message, keyPair.privateKey);
  return { initMs, keygenMs, signMs, verifyMs };
}

function expectBytes(
  value: Uint8Array,
  expectedLength: number,
  code: MlDsa44ErrorCode,
  label: string,
): void {
  if (!(value instanceof Uint8Array)) {
    throw new MlDsa44BackendError(code, `${label} must be a Uint8Array.`);
  }
  if (value.length !== expectedLength) {
    throw new MlDsa44BackendError(code, `${label} must be exactly ${expectedLength} bytes.`);
  }
}

function copyBytes(value: Uint8Array): Uint8Array {
  return new Uint8Array(value);
}

function zeroBytes(...values: Uint8Array[]): void {
  for (const value of values) {
    value.fill(0);
  }
}
