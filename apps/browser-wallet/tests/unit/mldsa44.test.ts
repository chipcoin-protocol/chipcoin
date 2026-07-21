import { describe, expect, it, vi } from "vitest";

import mldsaVector from "../fixtures/mldsa44-browser-vector-1.json";
import { parseAddress } from "../../src/crypto/addresses";
import { bytesToHex, hexToBytes } from "../../src/crypto/keys";
import {
  ENABLE_EXPERIMENTAL_BROWSER_MLDSA,
} from "../../src/shared/constants";
import {
  benchmarkMlDsa44Backend,
  createExperimentalMlDsa44Backend,
  MlDsaBackendUnavailableError,
  MlDsaInvalidDigestError,
  MlDsaInvalidPrivateKeyError,
  MlDsaInvalidPublicKeyError,
  MlDsaInvalidSignatureError,
  MlDsaInvalidSeedError,
  MlDsaUnsupportedVersionError,
  MLDSA44_PRIVATE_KEY_BYTES,
  MLDSA44_PUBLIC_KEY_BYTES,
  MLDSA44_SEED_BYTES,
  MLDSA44_SIGNATURE_BYTES,
  ML_DSA_44_PRIVATE_KEY_SIZE,
  ML_DSA_44_PUBLIC_KEY_SIZE,
  ML_DSA_44_SCHEME_ID,
  ML_DSA_44_SCHEME_NAME,
  ML_DSA_44_SEED_SIZE,
  ML_DSA_44_SIGNATURE_SIZE,
  MlDsa44BackendError,
  NOBLE_POST_QUANTUM_IMPORT_PATH,
  NOBLE_POST_QUANTUM_VERSION,
} from "../../src/crypto/mldsa44";

function expectBackendError(code: string, callable: () => Promise<unknown>) {
  return expect(callable()).rejects.toMatchObject({ code });
}

describe("experimental ML-DSA-44 browser backend", () => {
  it("keeps the public feature flag disabled by default", async () => {
    expect(ENABLE_EXPERIMENTAL_BROWSER_MLDSA).toBe(false);
    const backend = createExperimentalMlDsa44Backend();
    await expectBackendError("feature_disabled", () => backend.initialize());
  });

  it("requires initialization before use", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await expectBackendError("not_initialized", () => backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex)));
  });

  it("initializes repeatedly without racing", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await Promise.all([backend.initialize(), backend.initialize(), backend.initialize()]);
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    expect(keyPair.publicKey).toHaveLength(ML_DSA_44_PUBLIC_KEY_SIZE);
  });

  it("imports deterministic Python vector keys and validates CHCQ address metadata", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    const addressInfo = parseAddress(mldsaVector.address);

    expect(mldsaVector.scheme_id).toBe(ML_DSA_44_SCHEME_ID);
    expect(mldsaVector.scheme_name).toBe(ML_DSA_44_SCHEME_NAME);
    expect(addressInfo.kind).toBe("pq");
    expect(addressInfo.schemeId).toBe(ML_DSA_44_SCHEME_ID);
    expect(bytesToHex(keyPair.publicKey)).toBe(mldsaVector.public_key_hex);
    expect(bytesToHex(keyPair.privateKey)).toBe(mldsaVector.private_key_hex);
    expect(keyPair.publicKey).toHaveLength(mldsaVector.public_key_len);
    expect(keyPair.privateKey).toHaveLength(mldsaVector.private_key_len);
  });

  it("signs raw Chipcoin digests with byte parity against Python mldsa-native", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    const message = hexToBytes(mldsaVector.message_hex);
    const signature = await backend.signDigest(message, keyPair.privateKey);

    expect(bytesToHex(signature)).toBe(mldsaVector.signature_hex);
    expect(await backend.verifyDigest(message, signature, keyPair.publicKey)).toBe(true);
  });

  it("verifies Python signatures and rejects altered data", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const message = hexToBytes(mldsaVector.message_hex);
    const signature = hexToBytes(mldsaVector.signature_hex);
    const publicKey = hexToBytes(mldsaVector.public_key_hex);

    expect(await backend.verifyDigest(message, signature, publicKey)).toBe(true);

    const alteredSignature = new Uint8Array(signature);
    alteredSignature[0] ^= 0x01;
    expect(await backend.verifyDigest(message, alteredSignature, publicKey)).toBe(false);

    const alteredMessage = new Uint8Array(message);
    alteredMessage[0] ^= 0x01;
    expect(await backend.verifyDigest(alteredMessage, signature, publicKey)).toBe(false);

    const wrongPublicKey = (await backend.generateKeyPair(new Uint8Array(ML_DSA_44_SEED_SIZE).fill(9))).publicKey;
    expect(await backend.verifyDigest(message, signature, wrongPublicKey)).toBe(false);
  });

  it("throws typed errors for structurally invalid inputs", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    const message = hexToBytes(mldsaVector.message_hex);
    const signature = hexToBytes(mldsaVector.signature_hex);

    await expectBackendError("invalid_seed", () => backend.generateKeyPair(new Uint8Array(31)));
    await expectBackendError("invalid_seed", () => backend.generateKeyPair(new Uint8Array(0)));
    await expectBackendError("invalid_digest", () => backend.signDigest(new Uint8Array(31), keyPair.privateKey));
    await expectBackendError("invalid_digest", () => backend.signDigest(new Uint8Array(33), keyPair.privateKey));
    await expectBackendError("invalid_digest", () => backend.signDigest(new Uint8Array(0), keyPair.privateKey));
    await expectBackendError("invalid_private_key", () => backend.signDigest(message, new Uint8Array(ML_DSA_44_PRIVATE_KEY_SIZE - 1)));
    await expectBackendError("invalid_private_key", () => backend.signDigest(message, new Uint8Array(0)));
    await expectBackendError("invalid_signature", () => backend.verifyDigest(message, signature.slice(1), keyPair.publicKey));
    await expectBackendError("invalid_signature", () => backend.verifyDigest(message, new Uint8Array(0), keyPair.publicKey));
    await expectBackendError("invalid_public_key", () => backend.verifyDigest(message, signature, keyPair.publicKey.slice(1)));
    await expectBackendError("invalid_public_key", () => backend.verifyDigest(message, signature, new Uint8Array(0)));

    await expectBackendError("invalid_digest", async () => {
      const invalidMessage = "not bytes" as unknown as Uint8Array;
      await backend.signDigest(invalidMessage, keyPair.privateKey);
    });
  });

  it("throws distinct errors for unavailable or incompatible Noble APIs", async () => {
    const absent = createExperimentalMlDsa44Backend({ enabled: true, implementation: null });
    await expect(absent.initialize()).rejects.toBeInstanceOf(MlDsaBackendUnavailableError);

    const noInternal = createExperimentalMlDsa44Backend({
      enabled: true,
      implementation: {
        lengths: {
          seed: MLDSA44_SEED_BYTES,
          publicKey: MLDSA44_PUBLIC_KEY_BYTES,
          secretKey: MLDSA44_PRIVATE_KEY_BYTES,
          signature: MLDSA44_SIGNATURE_BYTES,
          signRand: MLDSA44_SEED_BYTES,
        },
        keygen: () => ({
          publicKey: new Uint8Array(MLDSA44_PUBLIC_KEY_BYTES),
          secretKey: new Uint8Array(MLDSA44_PRIVATE_KEY_BYTES),
        }),
      },
    });
    await expect(noInternal.initialize()).rejects.toBeInstanceOf(MlDsaUnsupportedVersionError);

    const wrongLengths = createExperimentalMlDsa44Backend({
      enabled: true,
      implementation: {
        lengths: {
          seed: MLDSA44_SEED_BYTES,
          publicKey: MLDSA44_PUBLIC_KEY_BYTES - 1,
          secretKey: MLDSA44_PRIVATE_KEY_BYTES,
          signature: MLDSA44_SIGNATURE_BYTES,
          signRand: MLDSA44_SEED_BYTES,
        },
        keygen: () => ({
          publicKey: new Uint8Array(MLDSA44_PUBLIC_KEY_BYTES),
          secretKey: new Uint8Array(MLDSA44_PRIVATE_KEY_BYTES),
        }),
        internal: {
          sign: () => new Uint8Array(MLDSA44_SIGNATURE_BYTES),
          verify: () => true,
        },
      },
    });
    await expect(wrongLengths.initialize()).rejects.toBeInstanceOf(MlDsaUnsupportedVersionError);
  });

  it("rejects signatures bound to another digest or keypair", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    const otherKeyPair = await backend.generateKeyPair(new Uint8Array(MLDSA44_SEED_BYTES).fill(7));
    const digest = hexToBytes(mldsaVector.message_hex);
    const signature = await backend.signDigest(digest, otherKeyPair.privateKey);

    expect(await backend.verifyDigest(digest, signature, keyPair.publicKey)).toBe(false);
    const mutatedDigest = new Uint8Array(digest);
    mutatedDigest[31] ^= 0x01;
    expect(await backend.verifyDigest(mutatedDigest, signature, otherKeyPair.publicKey)).toBe(false);
  });

  it("supports repeated calls and does not log sensitive material", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      const backend = createExperimentalMlDsa44Backend({ enabled: true });
      await backend.initialize();
      const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
      const digest = hexToBytes(mldsaVector.message_hex);
      for (let index = 0; index < 5; index += 1) {
        const signature = await backend.signDigest(digest, keyPair.privateKey);
        expect(await backend.verifyDigest(digest, signature, keyPair.publicKey)).toBe(true);
      }
      expect(logSpy).not.toHaveBeenCalled();
      expect(warnSpy).not.toHaveBeenCalled();
      expect(errorSpy).not.toHaveBeenCalled();
    } finally {
      logSpy.mockRestore();
      warnSpy.mockRestore();
      errorSpy.mockRestore();
    }
  });

  it("reports preliminary benchmark timings without rigid thresholds", async () => {
    const result = await benchmarkMlDsa44Backend(1);
    expect(result.initMs).toBeGreaterThanOrEqual(0);
    expect(result.keygenMs).toBeGreaterThanOrEqual(0);
    expect(result.signDigestMs).toBeGreaterThanOrEqual(0);
    expect(result.verifyDigestMs).toBeGreaterThanOrEqual(0);
    expect(result.sign10Ms).toBeGreaterThanOrEqual(0);
    expect(result.verify10Ms).toBeGreaterThanOrEqual(0);
  });

  it("uses the expected fixed lengths", () => {
    expect(ML_DSA_44_SEED_SIZE).toBe(32);
    expect(ML_DSA_44_PUBLIC_KEY_SIZE).toBe(1312);
    expect(ML_DSA_44_PRIVATE_KEY_SIZE).toBe(2560);
    expect(ML_DSA_44_SIGNATURE_SIZE).toBe(2420);
    expect(NOBLE_POST_QUANTUM_VERSION).toBe("0.6.1");
    expect(NOBLE_POST_QUANTUM_IMPORT_PATH).toBe("@noble/post-quantum/ml-dsa.js");
    expect(new MlDsaInvalidDigestError().code).toBe("invalid_digest");
    expect(new MlDsaInvalidPrivateKeyError().code).toBe("invalid_private_key");
    expect(new MlDsaInvalidPublicKeyError().code).toBe("invalid_public_key");
    expect(new MlDsaInvalidSignatureError().code).toBe("invalid_signature");
    expect(new MlDsaInvalidSeedError().code).toBe("invalid_seed");
    expect(new MlDsa44BackendError("unsupported_version", "unsupported").code).toBe("unsupported_version");
  });
});
