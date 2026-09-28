import { privateKeyHexToAddress, publicKeyHexToPqAddress } from "../crypto/addresses";
import { validateBrowserSendRecipient } from "../shared/address_scheme";
import {
  serializeSignedTransactionToRawHex,
  transactionId,
  transactionSignatureDigest,
} from "../crypto/serialization";
import { bytesToHex, hexToBytes } from "../crypto/keys";
import { createExperimentalMlDsa44Backend, ML_DSA_44_SCHEME_ID } from "../crypto/mldsa44";
import { signDigestHex, walletKeyMaterialFromPrivateKeyHex } from "../crypto/signing";
import type { AddressUtxo } from "../api/types";
import type { BuiltTransaction, SendPlan, SpendCandidate, TransactionModel } from "./models";
import { selectInputs } from "./selection";

export function filterSpendableCandidates(address: string, utxos: AddressUtxo[]): SpendCandidate[] {
  return utxos
    .filter((utxo) => utxo.status === "unspent" && utxo.mature)
    .map((utxo) => ({
      txid: utxo.txid,
      index: utxo.vout,
      amountChipbits: utxo.amount_chipbits,
      recipient: address,
    }));
}

export function buildSendPlan(args: {
  walletAddress: string;
  recipient: string;
  amountChipbits: number;
  feeChipbits: number;
  utxos: AddressUtxo[];
}): SendPlan {
  const { walletAddress, recipient, amountChipbits, feeChipbits, utxos } = args;
  if (amountChipbits <= 0) {
    throw new Error("Amount must be positive.");
  }
  if (feeChipbits < 0) {
    throw new Error("Fee cannot be negative.");
  }
  const recipientValidation = validateBrowserSendRecipient(recipient);
  if (recipientValidation.status !== "sendable") {
    throw new Error(recipientValidation.error ?? "Recipient is not sendable.");
  }
  const spendableCandidates = filterSpendableCandidates(walletAddress, utxos);
  const targetValue = amountChipbits + feeChipbits;
  const spendableValue = spendableCandidates.reduce((total, candidate) => total + candidate.amountChipbits, 0);
  const hasImmatureCoinbase = utxos.some((utxo) => utxo.status === "unspent" && utxo.coinbase && !utxo.mature);
  if (spendableValue < targetValue && hasImmatureCoinbase) {
    throw new Error("Insufficient spendable balance. Coinbase rewards are still immature.");
  }
  const selection = selectInputs(spendableCandidates, targetValue);
  return {
    recipient,
    amountChipbits,
    feeChipbits,
    changeRecipient: walletAddress,
    selectedInputs: selection.selected,
    totalInputChipbits: selection.totalInputChipbits,
    changeChipbits: selection.changeChipbits,
  };
}

export function buildSignedPaymentTransaction(args: {
  privateKeyHex: string;
  walletAddress: string;
  recipient: string;
  amountChipbits: number;
  feeChipbits: number;
  utxos: AddressUtxo[];
}): BuiltTransaction {
  const plan = buildSendPlan(args);
  const keyMaterial = walletKeyMaterialFromPrivateKeyHex(args.privateKeyHex);
  const derivedAddress = privateKeyHexToAddress(args.privateKeyHex);
  if (args.walletAddress !== derivedAddress) {
    throw new Error("Wallet address does not match the provided private key.");
  }

  const unsigned: TransactionModel = {
    version: 1,
    inputs: plan.selectedInputs.map((input) => ({
      previousOutput: {
        txid: input.txid,
        index: input.index,
      },
      signatureHex: "",
      publicKeyHex: "",
      sequence: 0xffffffff,
    })),
    outputs: [
      {
        value: plan.amountChipbits,
        recipient: plan.recipient,
      },
      ...(plan.changeChipbits > 0
        ? [{
            value: plan.changeChipbits,
            recipient: plan.changeRecipient,
          }]
        : []),
    ],
    locktime: 0,
    metadata: {},
  };

  const signedInputs = unsigned.inputs.map((input, index) => {
    const candidate = plan.selectedInputs[index];
      if (candidate.recipient !== derivedAddress) {
        throw new Error("Spend candidate recipient does not belong to this wallet key.");
      }
    const digestHex = bytesToHex(
      transactionSignatureDigest({
        transaction: unsigned,
        inputIndex: index,
        previousOutputValue: candidate.amountChipbits,
        previousOutputRecipient: candidate.recipient,
      }),
    );
    return {
      ...input,
      signatureHex: signDigestHex(args.privateKeyHex, digestHex),
      publicKeyHex: keyMaterial.publicKeyHex,
    };
  });

  const signed: TransactionModel = {
    ...unsigned,
    inputs: signedInputs,
  };

  return {
    transaction: signed,
    rawHex: serializeSignedTransactionToRawHex(signed),
    txid: transactionId(signed),
    feeChipbits: plan.feeChipbits,
    changeChipbits: plan.changeChipbits,
  };
}

export async function buildSignedPqPaymentTransaction(args: {
  pqSeedHex: string;
  walletAddress: string;
  recipient: string;
  amountChipbits: number;
  feeChipbits: number;
  utxos: AddressUtxo[];
  network: string;
}): Promise<BuiltTransaction> {
  const plan = buildSendPlan(args);
  const backend = createExperimentalMlDsa44Backend();
  await backend.initialize();
  const keyPair = await backend.generateKeyPair(hexToBytes(args.pqSeedHex));
  const publicKeyHex = bytesToHex(keyPair.publicKey);
  const derivedAddress = publicKeyHexToPqAddress(publicKeyHex, ML_DSA_44_SCHEME_ID);
  if (args.walletAddress !== derivedAddress) {
    throw new Error("Wallet address does not match the provided ML-DSA seed.");
  }

  const unsigned: TransactionModel = {
    version: 2,
    inputs: plan.selectedInputs.map((input) => ({
      previousOutput: { txid: input.txid, index: input.index },
      signatureHex: "",
      publicKeyHex: "",
      sequence: 0xffffffff,
      sigSchemeId: ML_DSA_44_SCHEME_ID,
    })),
    outputs: [
      { value: plan.amountChipbits, recipient: plan.recipient },
      ...(plan.changeChipbits > 0 ? [{ value: plan.changeChipbits, recipient: plan.changeRecipient }] : []),
    ],
    locktime: 0,
    metadata: {},
  };

  const signedInputs = [];
  for (let index = 0; index < unsigned.inputs.length; index += 1) {
    const candidate = plan.selectedInputs[index];
    if (candidate.recipient !== derivedAddress) {
      throw new Error("Spend candidate recipient does not belong to this wallet key.");
    }
    const digest = transactionSignatureDigest({
      transaction: unsigned,
      inputIndex: index,
      previousOutputValue: candidate.amountChipbits,
      previousOutputRecipient: candidate.recipient,
      network: args.network,
    });
    signedInputs.push({
      ...unsigned.inputs[index],
      signatureHex: bytesToHex(await backend.signDigest(digest, keyPair.privateKey)),
      publicKeyHex,
    });
  }

  const signed = { ...unsigned, inputs: signedInputs };
  return {
    transaction: signed,
    rawHex: serializeSignedTransactionToRawHex(signed),
    txid: transactionId(signed),
    feeChipbits: plan.feeChipbits,
    changeChipbits: plan.changeChipbits,
  };
}
