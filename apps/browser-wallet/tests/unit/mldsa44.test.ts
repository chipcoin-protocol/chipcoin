import { describe, expect, it } from "vitest";

import mldsaVector from "../fixtures/mldsa44-browser-vector-1.json";
import { parseAddress } from "../../src/crypto/addresses";
import { bytesToHex, hexToBytes } from "../../src/crypto/keys";
import {
  ENABLE_EXPERIMENTAL_BROWSER_MLDSA,
} from "../../src/shared/constants";
import {
  benchmarkMlDsa44Backend,
  createExperimentalMlDsa44Backend,
  ML_DSA_44_PRIVATE_KEY_SIZE,
  ML_DSA_44_PUBLIC_KEY_SIZE,
  ML_DSA_44_SCHEME_ID,
  ML_DSA_44_SCHEME_NAME,
  ML_DSA_44_SEED_SIZE,
  ML_DSA_44_SIGNATURE_SIZE,
  MlDsa44BackendError,
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
    const signature = await backend.sign(message, keyPair.privateKey);

    expect(bytesToHex(signature)).toBe(mldsaVector.signature_hex);
    expect(await backend.verify(message, signature, keyPair.publicKey)).toBe(true);
  });

  it("verifies Python signatures and rejects altered data", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const message = hexToBytes(mldsaVector.message_hex);
    const signature = hexToBytes(mldsaVector.signature_hex);
    const publicKey = hexToBytes(mldsaVector.public_key_hex);

    expect(await backend.verify(message, signature, publicKey)).toBe(true);

    const alteredSignature = new Uint8Array(signature);
    alteredSignature[0] ^= 0x01;
    expect(await backend.verify(message, alteredSignature, publicKey)).toBe(false);

    const alteredMessage = new Uint8Array(message);
    alteredMessage[0] ^= 0x01;
    expect(await backend.verify(alteredMessage, signature, publicKey)).toBe(false);

    const wrongPublicKey = (await backend.generateKeyPair(new Uint8Array(ML_DSA_44_SEED_SIZE).fill(9))).publicKey;
    expect(await backend.verify(message, signature, wrongPublicKey)).toBe(false);
  });

  it("throws typed errors for structurally invalid inputs", async () => {
    const backend = createExperimentalMlDsa44Backend({ enabled: true });
    await backend.initialize();
    const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
    const message = hexToBytes(mldsaVector.message_hex);
    const signature = hexToBytes(mldsaVector.signature_hex);

    await expectBackendError("invalid_seed", () => backend.generateKeyPair(new Uint8Array(31)));
    await expectBackendError("invalid_message", () => backend.sign(new Uint8Array(31), keyPair.privateKey));
    await expectBackendError("invalid_private_key", () => backend.sign(message, new Uint8Array(ML_DSA_44_PRIVATE_KEY_SIZE - 1)));
    await expectBackendError("invalid_signature", () => backend.verify(message, signature.slice(1), keyPair.publicKey));
    await expectBackendError("invalid_public_key", () => backend.verify(message, signature, keyPair.publicKey.slice(1)));

    await expectBackendError("invalid_message", async () => {
      const invalidMessage = "not bytes" as unknown as Uint8Array;
      await backend.sign(invalidMessage, keyPair.privateKey);
    });
  });

  it("reports preliminary benchmark timings without rigid thresholds", async () => {
    const result = await benchmarkMlDsa44Backend(1);
    expect(result.initMs).toBeGreaterThanOrEqual(0);
    expect(result.keygenMs).toBeGreaterThanOrEqual(0);
    expect(result.signMs).toBeGreaterThanOrEqual(0);
    expect(result.verifyMs).toBeGreaterThanOrEqual(0);
  });

  it("uses the expected fixed lengths", () => {
    expect(ML_DSA_44_SEED_SIZE).toBe(32);
    expect(ML_DSA_44_PUBLIC_KEY_SIZE).toBe(1312);
    expect(ML_DSA_44_PRIVATE_KEY_SIZE).toBe(2560);
    expect(ML_DSA_44_SIGNATURE_SIZE).toBe(2420);
    expect(new MlDsa44BackendError("unsupported_scheme", "unsupported").code).toBe("unsupported_scheme");
  });
});
