import type { TxLookup } from "../../api/types";
import { classifySignatureScheme, classifyTransactionSchemes, transactionVersionLabel } from "../../shared/address_scheme";
import { SchemeBadge } from "./SchemeBadge";

export function TransactionSchemeBadge({ transaction }: { transaction: TxLookup["transaction"] }): JSX.Element {
  return (
    <span className="transaction-scheme">
      <span className="scheme-version" title="Transaction version">{transactionVersionLabel(transaction.version)}</span>
      <SchemeBadge scheme={classifyTransactionSchemes(transaction)} />
    </span>
  );
}

export function InputSchemeBadge({ input }: { input: TxLookup["transaction"]["inputs"][number] }): JSX.Element {
  return <SchemeBadge scheme={classifySignatureScheme(input)} />;
}
