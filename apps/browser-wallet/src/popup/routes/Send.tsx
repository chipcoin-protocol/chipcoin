import { useState } from "react";

import type { AppState } from "../../state/app_state";
import { validateBrowserSendRecipient } from "../../shared/address_scheme";
import { getSupportedNetwork } from "../../shared/constants";
import { parseChcToChipbits } from "../../shared/formatting";
import { sendWalletMessage } from "../../shared/messages";
import { AddressWithBadge } from "../components/AddressWithBadge";

export interface SendFormState {
  parsedAmountChipbits: number;
  parsedFeeChipbits: number;
  formError: string | null;
  isSubmitDisabled: boolean;
  recipientValidation: ReturnType<typeof validateBrowserSendRecipient>;
}

export function computeSendFormState(args: {
  connectedNetwork: string | null;
  expectedNetwork: string;
  recipient: string;
  amountChc: string;
  feeChc: string;
  isSubmitting: boolean;
}): SendFormState {
  let parsedAmountChipbits = 0;
  let parsedFeeChipbits = 0;
  let formError: string | null = null;
  const hasNetworkMismatch = args.connectedNetwork !== null && args.connectedNetwork !== args.expectedNetwork;
  const recipientValidation = validateBrowserSendRecipient(args.recipient.trim());

  if (args.connectedNetwork === null) {
    formError = "Node endpoint is unavailable or has not passed network validation.";
  } else if (hasNetworkMismatch) {
    formError = `Wrong network. Expected ${args.expectedNetwork}, got ${args.connectedNetwork}.`;
  } else if (recipientValidation.status !== "sendable") {
    formError = recipientValidation.error;
  } else {
    try {
      parsedAmountChipbits = parseChcToChipbits(args.amountChc);
    } catch (error) {
      formError = error instanceof Error ? error.message : "Amount must be a valid CHC value.";
    }
  }

  if (!formError) {
    try {
      parsedFeeChipbits = parseChcToChipbits(args.feeChc);
    } catch (error) {
      formError = error instanceof Error ? error.message.replace("Amount", "Fee") : "Fee must be a valid CHC value.";
    }
  }

  return {
    parsedAmountChipbits,
    parsedFeeChipbits,
    formError,
    isSubmitDisabled: Boolean(formError) || args.isSubmitting,
    recipientValidation,
  };
}

export function Send({ state, onRefresh }: { state: AppState; onRefresh(): Promise<void> }): JSX.Element {
  const [recipient, setRecipient] = useState("");
  const [amountChc, setAmountChc] = useState("");
  const [feeChc, setFeeChc] = useState("0.00001");
  const [result, setResult] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const activeNetwork = getSupportedNetwork(state.expectedNetwork);
  const connectedNetwork = state.nodeStatus?.network ?? null;
  const hasNetworkMismatch = connectedNetwork !== null && connectedNetwork !== state.expectedNetwork;
  const hasEndpointValidationFailure = connectedNetwork === null || hasNetworkMismatch;
  const trimmedRecipient = recipient.trim();
  const { parsedAmountChipbits, parsedFeeChipbits, formError, isSubmitDisabled, recipientValidation } = computeSendFormState({
    connectedNetwork,
    expectedNetwork: state.expectedNetwork,
    recipient,
    amountChc,
    feeChc,
    isSubmitting,
  });

  async function handleSubmit(): Promise<void> {
    if (formError || isSubmitting) {
      return;
    }
    const submitRecipientValidation = validateBrowserSendRecipient(trimmedRecipient);
    if (submitRecipientValidation.status !== "sendable") {
      setResult(submitRecipientValidation.error ?? "Recipient is not sendable.");
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await sendWalletMessage<{ status: string; txid?: string }>({
        type: "wallet:submit",
        recipient: trimmedRecipient,
        amountChipbits: parsedAmountChipbits,
        feeChipbits: parsedFeeChipbits,
      });
      const label = ({
        submitted: "Submitted",
        rejected: "Rejected",
        failed_to_submit: "Failed to submit",
      } as const)[response.status as "submitted" | "rejected" | "failed_to_submit"] ?? response.status;
      setResult(response.txid ? `${label}: ${response.txid}` : label);
      await onRefresh();
      if (response.status === "submitted") {
        setRecipient("");
        setAmountChc("");
      }
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Unable to submit transaction.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <h2>Send</h2>
      <p className="message">Spending stays client-side. The wallet builds, signs, and serializes transactions locally before submitting raw hex to the node.</p>
      <p><strong>Network:</strong> <span className="pill">{activeNetwork.label}</span></p>
      <p><strong>Node API:</strong> <span className="mono">{state.nodeApiBaseUrl}</span></p>
      {hasEndpointValidationFailure ? <p className="message error">Endpoint validation failed. Switch to a reachable {state.expectedNetwork} node before submitting transactions.</p> : null}
      <p><strong>From wallet:</strong> {state.address ? <AddressWithBadge address={state.address} /> : "Unavailable"}</p>
      <div className="stack">
        <label className="stack">
          <span>Recipient address</span>
          <input value={recipient} onChange={(event) => { setRecipient(event.target.value); setResult(null); }} placeholder="CHC or CHCQ recipient address" />
        </label>
        {trimmedRecipient && recipientValidation.scheme ? (
          <p className="message recipient-status">
            Recipient: <AddressWithBadge address={trimmedRecipient} />
          </p>
        ) : null}
        <label className="stack">
          <span>Amount (CHC)</span>
          <input value={amountChc} onChange={(event) => { setAmountChc(event.target.value); setResult(null); }} placeholder="e.g. 50 or 0.25" />
        </label>
        <label className="stack">
          <span>Fee (CHC)</span>
          <input value={feeChc} onChange={(event) => { setFeeChc(event.target.value); setResult(null); }} placeholder="e.g. 0.00001" />
        </label>
        <button className="primary-button" disabled={isSubmitDisabled} onClick={() => void handleSubmit()}>
          {isSubmitting ? "Submitting..." : "Submit transaction"}
        </button>
      </div>
      {formError ? <p className="message error">{formError}</p> : null}
      {result ? <p className="message">{result}</p> : null}
    </section>
  );
}
