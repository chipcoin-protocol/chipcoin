import mldsaVector from "../fixtures/mldsa44-browser-vector-1.json";
import { bytesToHex, hexToBytes } from "../../src/crypto/keys";
import {
  benchmarkMlDsa44Backend,
  createExperimentalMlDsa44Backend,
} from "../../src/crypto/mldsa44";

declare global {
  interface Window {
    __CHIPCOIN_MLDSA_BROWSER_RESULT__?: unknown;
  }
}

async function runHarness() {
  const backend = createExperimentalMlDsa44Backend({ enabled: true });
  await backend.initialize();
  await Promise.all([backend.initialize(), backend.initialize()]);
  const digest = hexToBytes(mldsaVector.message_hex);
  const keyPair = await backend.generateKeyPair(hexToBytes(mldsaVector.seed_hex));
  const signature = await backend.signDigest(digest, keyPair.privateKey);
  const alteredSignature = new Uint8Array(signature);
  alteredSignature[0] ^= 0x01;
  const alteredDigest = new Uint8Array(digest);
  alteredDigest[0] ^= 0x01;
  const wrongPublicKey = (await backend.generateKeyPair(new Uint8Array(32).fill(3))).publicKey;
  const benchmark = await benchmarkMlDsa44Backend(3);

  const publicKeyMatches = bytesToHex(keyPair.publicKey) === mldsaVector.public_key_hex;
  const signatureMatches = bytesToHex(signature) === mldsaVector.signature_hex;
  const signatureVerifies = await backend.verifyDigest(digest, signature, keyPair.publicKey);
  const pythonSignatureVerifies = await backend.verifyDigest(digest, hexToBytes(mldsaVector.signature_hex), keyPair.publicKey);
  const alteredSignatureRejected = !await backend.verifyDigest(digest, alteredSignature, keyPair.publicKey);
  const alteredDigestRejected = !await backend.verifyDigest(alteredDigest, signature, keyPair.publicKey);
  const wrongPublicKeyRejected = !await backend.verifyDigest(digest, signature, wrongPublicKey);

  return {
    ok: publicKeyMatches
      && signatureMatches
      && signatureVerifies
      && pythonSignatureVerifies
      && alteredSignatureRejected
      && alteredDigestRejected
      && wrongPublicKeyRejected,
    publicKeyMatches,
    signatureMatches,
    signatureVerifies,
    pythonSignatureVerifies,
    alteredSignatureRejected,
    alteredDigestRejected,
    wrongPublicKeyRejected,
    publicKeyLength: keyPair.publicKey.length,
    privateKeyLength: keyPair.privateKey.length,
    signatureLength: signature.length,
    benchmark,
  };
}

runHarness()
  .then((result) => {
    window.__CHIPCOIN_MLDSA_BROWSER_RESULT__ = result;
    document.body.dataset.status = result.ok ? "pass" : "fail";
    document.body.textContent = JSON.stringify(result);
  })
  .catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    window.__CHIPCOIN_MLDSA_BROWSER_RESULT__ = { ok: false, error: message };
    document.body.dataset.status = "fail";
    document.body.textContent = message;
  });
