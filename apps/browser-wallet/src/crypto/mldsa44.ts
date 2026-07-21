import { ml_dsa44 as nobleMlDsa44 } from "@noble/post-quantum/ml-dsa.js";

import { ENABLE_EXPERIMENTAL_BROWSER_MLDSA } from "../shared/constants";

export const ML_DSA_44_SCHEME_ID = 10;
export const ML_DSA_44_SCHEME_NAME = "mldsa44";
export const MLDSA44_SEED_BYTES = 32;
export const CHIPCOIN_V2_DIGEST_BYTES = 32;
export const MLDSA44_PUBLIC_KEY_BYTES = 1312;
export const MLDSA44_PRIVATE_KEY_BYTES = 2560;
export const MLDSA44_SIGNATURE_BYTES = 2420;
export const NOBLE_POST_QUANTUM_VERSION = "0.6.1";
export const NOBLE_POST_QUANTUM_IMPORT_PATH = "@noble/post-quantum/ml-dsa.js";

export const ML_DSA_44_SEED_SIZE = MLDSA44_SEED_BYTES;
export const ML_DSA_44_PUBLIC_KEY_SIZE = MLDSA44_PUBLIC_KEY_BYTES;
export const ML_DSA_44_PRIVATE_KEY_SIZE = MLDSA44_PRIVATE_KEY_BYTES;
export const ML_DSA_44_SIGNATURE_SIZE = MLDSA44_SIGNATURE_BYTES;

export type MlDsa44ErrorCode =
  | "backend_unavailable"
  | "feature_disabled"
  | "invalid_digest"
  | "invalid_private_key"
  | "invalid_public_key"
  | "invalid_seed"
  | "invalid_signature"
  | "not_initialized"
  | "unsupported_version";

export class MlDsa44BackendError extends Error {
  constructor(readonly code: MlDsa44ErrorCode, message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class MlDsaBackendUnavailableError extends MlDsa44BackendError {
  constructor(message = "ML-DSA-44 backend is not available.") {
    super("backend_unavailable", message);
  }
}

export class MlDsaFeatureDisabledError extends MlDsa44BackendError {
  constructor() {
    super("feature_disabled", "Experimental browser ML-DSA-44 is disabled.");
  }
}

export class MlDsaNotInitializedError extends MlDsa44BackendError {
  constructor() {
    super("not_initialized", "Initialize ML-DSA-44 before using it.");
  }
}

export class MlDsaInvalidDigestError extends MlDsa44BackendError {
  constructor(message = `Chipcoin v2 signing digest must be exactly ${CHIPCOIN_V2_DIGEST_BYTES} bytes.`) {
    super("invalid_digest", message);
  }
}

export class MlDsaInvalidPublicKeyError extends MlDsa44BackendError {
  constructor(message = `ML-DSA-44 public key must be exactly ${MLDSA44_PUBLIC_KEY_BYTES} bytes.`) {
    super("invalid_public_key", message);
  }
}

export class MlDsaInvalidPrivateKeyError extends MlDsa44BackendError {
  constructor(message = `ML-DSA-44 private key must be exactly ${MLDSA44_PRIVATE_KEY_BYTES} bytes.`) {
    super("invalid_private_key", message);
  }
}

export class MlDsaInvalidSignatureError extends MlDsa44BackendError {
  constructor(message = `ML-DSA-44 signature must be exactly ${MLDSA44_SIGNATURE_BYTES} bytes.`) {
    super("invalid_signature", message);
  }
}

export class MlDsaInvalidSeedError extends MlDsa44BackendError {
  constructor(message = `ML-DSA-44 seed must be exactly ${MLDSA44_SEED_BYTES} bytes.`) {
    super("invalid_seed", message);
  }
}

export class MlDsaUnsupportedVersionError extends MlDsa44BackendError {
  constructor(message: string) {
    super("unsupported_version", message);
  }
}

export interface MlDsa44KeyPair {
  publicKey: Uint8Array;
  privateKey: Uint8Array;
}

export interface MlDsa44Backend {
  initialize(): Promise<void>;
  generateKeyPair(seed?: Uint8Array): Promise<MlDsa44KeyPair>;
  signDigest(digest: Uint8Array, privateKey: Uint8Array): Promise<Uint8Array>;
  verifyDigest(digest: Uint8Array, signature: Uint8Array, publicKey: Uint8Array): Promise<boolean>;
}

export interface MlDsa44BenchmarkResult {
  initMs: number;
  keygenMs: number;
  signDigestMs: number;
  verifyDigestMs: number;
  sign10Ms: number;
  verify10Ms: number;
}

interface NobleMlDsa44Implementation {
  lengths?: {
    seed?: number;
    publicKey?: number;
    secretKey?: number;
    signature?: number;
    signRand?: number;
  };
  keygen?: (seed?: Uint8Array) => { publicKey: Uint8Array; secretKey: Uint8Array };
  internal?: {
    sign?: (message: Uint8Array, secretKey: Uint8Array, options: { extraEntropy: false }) => Uint8Array;
    verify?: (signature: Uint8Array, message: Uint8Array, publicKey: Uint8Array) => boolean;
  };
}

interface BackendOptions {
  enabled?: boolean;
  implementation?: NobleMlDsa44Implementation | null;
}

export function createExperimentalMlDsa44Backend(options: BackendOptions = {}): MlDsa44Backend {
  let initialized = false;
  let initializing: Promise<void> | null = null;
  const enabled = options.enabled ?? ENABLE_EXPERIMENTAL_BROWSER_MLDSA;
  const implementation = Object.prototype.hasOwnProperty.call(options, "implementation")
    ? options.implementation ?? null
    : nobleMlDsa44;

  async function initialize(): Promise<void> {
    if (!enabled) {
      throw new MlDsaFeatureDisabledError();
    }
    if (initialized) {
      return;
    }
    if (!initializing) {
      initializing = Promise.resolve().then(() => {
        assertNobleMldsa44Compatibility(implementation);
        initialized = true;
      }).finally(() => {
        initializing = null;
      });
    }
    await initializing;
  }

  function ensureInitialized(): void {
    if (!initialized) {
      throw new MlDsaNotInitializedError();
    }
  }

  return {
    initialize,
    async generateKeyPair(seed?: Uint8Array): Promise<MlDsa44KeyPair> {
      ensureInitialized();
      if (seed !== undefined) {
        assertSeed(seed);
      }
      const keyPair = implementation?.keygen?.(seed);
      if (!keyPair) {
        throw new MlDsaBackendUnavailableError("ML-DSA-44 key generation function is not available.");
      }
      assertPublicKey(keyPair.publicKey);
      assertPrivateKey(keyPair.secretKey);
      return {
        publicKey: copyBytes(keyPair.publicKey),
        privateKey: copyBytes(keyPair.secretKey),
      };
    },
    async signDigest(digest: Uint8Array, privateKey: Uint8Array): Promise<Uint8Array> {
      ensureInitialized();
      assertDigest(digest);
      assertPrivateKey(privateKey);
      /*
       * Chipcoin consensus signs the already-computed v2 transaction digest.
       * The digest is exactly 32 bytes and already includes the network domain
       * separator in the signing payload. Do not use noble's public
       * message-signing wrapper here: it applies FIPS message formatting and
       * produces bytes that are not compatible with the Python mldsa-native
       * backend used by node validation.
       */
      const signature = implementation?.internal?.sign?.(digest, privateKey, { extraEntropy: false });
      if (!signature) {
        throw new MlDsaBackendUnavailableError("ML-DSA-44 raw digest signing function is not available.");
      }
      assertSignature(signature);
      return copyBytes(signature);
    },
    async verifyDigest(digest: Uint8Array, signature: Uint8Array, publicKey: Uint8Array): Promise<boolean> {
      ensureInitialized();
      assertDigest(digest);
      assertSignature(signature);
      assertPublicKey(publicKey);
      /*
       * Keep verification in the same raw-digest mode as signDigest(). The
       * argument order and internal API shape are pinned by vector tests so a
       * Noble upgrade cannot silently switch to public message verification.
       */
      const verifier = implementation?.internal?.verify;
      if (!verifier) {
        throw new MlDsaBackendUnavailableError("ML-DSA-44 raw digest verification function is not available.");
      }
      return verifier(signature, digest, publicKey);
    },
  };
}

export function assertNobleMldsa44Compatibility(implementation: NobleMlDsa44Implementation | null): void {
  if (!implementation) {
    throw new MlDsaBackendUnavailableError();
  }
  if (typeof implementation.keygen !== "function") {
    throw new MlDsaBackendUnavailableError("ML-DSA-44 key generation function is not available.");
  }
  if (!implementation.internal
    || typeof implementation.internal.sign !== "function"
    || typeof implementation.internal.verify !== "function") {
    throw new MlDsaUnsupportedVersionError("Noble ML-DSA-44 internal raw digest API is not available.");
  }
  const lengths = implementation.lengths;
  if (!lengths
    || lengths.seed !== MLDSA44_SEED_BYTES
    || lengths.publicKey !== MLDSA44_PUBLIC_KEY_BYTES
    || lengths.secretKey !== MLDSA44_PRIVATE_KEY_BYTES
    || lengths.signature !== MLDSA44_SIGNATURE_BYTES
    || lengths.signRand !== MLDSA44_SEED_BYTES) {
    throw new MlDsaUnsupportedVersionError("Noble ML-DSA-44 constants do not match Chipcoin.");
  }
}

export async function benchmarkMlDsa44Backend(iterations = 10): Promise<MlDsa44BenchmarkResult> {
  const backend = createExperimentalMlDsa44Backend({ enabled: true });
  const seed = new Uint8Array(MLDSA44_SEED_BYTES);
  const digest = new Uint8Array(CHIPCOIN_V2_DIGEST_BYTES);
  const initStart = performance.now();
  await backend.initialize();
  const initMs = performance.now() - initStart;

  const keygenStart = performance.now();
  let keyPair: MlDsa44KeyPair | null = null;
  for (let index = 0; index < iterations; index += 1) {
    keyPair = await backend.generateKeyPair(seed);
  }
  const keygenMs = elapsedAverage(keygenStart, iterations);
  if (!keyPair) {
    throw new MlDsaBackendUnavailableError("ML-DSA-44 benchmark did not produce a keypair.");
  }

  const signStart = performance.now();
  let signature: Uint8Array | null = null;
  for (let index = 0; index < iterations; index += 1) {
    signature = await backend.signDigest(digest, keyPair.privateKey);
  }
  const signDigestMs = elapsedAverage(signStart, iterations);
  if (!signature) {
    throw new MlDsaBackendUnavailableError("ML-DSA-44 benchmark did not produce a signature.");
  }

  const verifyStart = performance.now();
  for (let index = 0; index < iterations; index += 1) {
    await backend.verifyDigest(digest, signature, keyPair.publicKey);
  }
  const verifyDigestMs = elapsedAverage(verifyStart, iterations);

  const sign10Start = performance.now();
  for (let index = 0; index < 10; index += 1) {
    signature = await backend.signDigest(digest, keyPair.privateKey);
  }
  const sign10Ms = performance.now() - sign10Start;

  const verify10Start = performance.now();
  for (let index = 0; index < 10; index += 1) {
    await backend.verifyDigest(digest, signature, keyPair.publicKey);
  }
  const verify10Ms = performance.now() - verify10Start;

  zeroBytes(seed, digest, keyPair.privateKey);
  return { initMs, keygenMs, signDigestMs, verifyDigestMs, sign10Ms, verify10Ms };
}

function elapsedAverage(startMs: number, iterations: number): number {
  return (performance.now() - startMs) / iterations;
}

function assertSeed(value: Uint8Array): void {
  expectBytes(value, MLDSA44_SEED_BYTES, () => new MlDsaInvalidSeedError());
}

function assertDigest(value: Uint8Array): void {
  expectBytes(value, CHIPCOIN_V2_DIGEST_BYTES, () => new MlDsaInvalidDigestError());
}

function assertPublicKey(value: Uint8Array): void {
  expectBytes(value, MLDSA44_PUBLIC_KEY_BYTES, () => new MlDsaInvalidPublicKeyError());
}

function assertPrivateKey(value: Uint8Array): void {
  expectBytes(value, MLDSA44_PRIVATE_KEY_BYTES, () => new MlDsaInvalidPrivateKeyError());
}

function assertSignature(value: Uint8Array): void {
  expectBytes(value, MLDSA44_SIGNATURE_BYTES, () => new MlDsaInvalidSignatureError());
}

function expectBytes(value: Uint8Array, expectedLength: number, errorFactory: () => MlDsa44BackendError): void {
  if (!(value instanceof Uint8Array) || value.length !== expectedLength) {
    throw errorFactory();
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
