const PBKDF2_ITERATIONS = 250_000;

export interface EncryptionResult {
  encryptedWalletBlob: string;
  saltBase64: string;
  ivBase64: string;
  iterations: number;
}

export interface EncryptedWalletSecretPayload {
  walletType: "private_key" | "seed_phrase";
  privateKeyHex?: string;
  recoveryPhrase?: string;
  accountIndex?: number;
}

export async function encryptWalletSecret(
  payload: EncryptedWalletSecretPayload,
  password: string,
): Promise<EncryptionResult> {
  validateSecretPayload(payload);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveEncryptionKey(password, salt, PBKDF2_ITERATIONS);
  const cipherBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  return {
    encryptedWalletBlob: bytesToBase64(new Uint8Array(cipherBuffer)),
    saltBase64: bytesToBase64(salt),
    ivBase64: bytesToBase64(iv),
    iterations: PBKDF2_ITERATIONS,
  };
}

export async function encryptPrivateKeyHex(privateKeyHex: string, password: string): Promise<EncryptionResult> {
  return encryptWalletSecret({ walletType: "private_key", privateKeyHex }, password);
}

export async function decryptWalletSecret(
  encryptedWalletBlob: string,
  password: string,
  saltBase64: string,
  ivBase64: string,
  iterations: number,
): Promise<EncryptedWalletSecretPayload> {
  const salt = base64ToBytes(saltBase64);
  const iv = base64ToBytes(ivBase64);
  const key = await deriveEncryptionKey(password, salt, iterations);
  try {
    const plainBuffer = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      base64ToBytes(encryptedWalletBlob),
    );
    const decoded = JSON.parse(new TextDecoder().decode(plainBuffer)) as EncryptedWalletSecretPayload;
    validateSecretPayload(decoded);
    return decoded;
  } catch {
    throw new Error("Unable to unlock wallet. Check your password.");
  }
}

export async function decryptPrivateKeyHex(
  encryptedWalletBlob: string,
  password: string,
  saltBase64: string,
  ivBase64: string,
  iterations: number,
): Promise<string> {
  const payload = await decryptWalletSecret(encryptedWalletBlob, password, saltBase64, ivBase64, iterations);
  if (!payload.privateKeyHex) {
    throw new Error("Wallet payload does not include a private key.");
  }
  return payload.privateKeyHex;
}

async function deriveEncryptionKey(password: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> {
  const passwordKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt,
      iterations,
      hash: "SHA-256",
    },
    passwordKey,
    {
      name: "AES-GCM",
      length: 256,
    },
    false,
    ["encrypt", "decrypt"],
  );
}

function bytesToBase64(value: Uint8Array): string {
  return btoa(String.fromCharCode(...value));
}

function base64ToBytes(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (item) => item.charCodeAt(0));
}

function validateSecretPayload(payload: EncryptedWalletSecretPayload): void {
  if (payload.walletType === "private_key" && payload.privateKeyHex) {
    return;
  }
  if (payload.walletType === "seed_phrase" && payload.recoveryPhrase) {
    return;
  }
  throw new Error("Wallet payload is incomplete.");
}
