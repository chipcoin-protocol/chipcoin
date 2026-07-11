import type { TxLookup } from "../../api/types";
import { formatChc, shortHash } from "../../shared/formatting";
import { AddressWithBadge } from "./AddressWithBadge";
import { InputSchemeBadge, TransactionSchemeBadge } from "./TransactionSchemeBadge";

export function TransactionDetails({ lookup }: { lookup: TxLookup }): JSX.Element {
  const transaction = lookup.transaction;
  return (
    <div className="transaction-detail">
      <p className="detail-row">
        <strong>Transaction:</strong> <TransactionSchemeBadge transaction={transaction} />
      </p>
      {transaction.inputs.length > 0 ? (
        <div className="detail-block">
          <strong>Inputs</strong>
          <ul className="compact-list">
            {transaction.inputs.map((input) => (
              <li key={`${input.txid}:${input.index}`}>
                <span className="mono">{shortHash(input.txid, 6)}:{input.index}</span> <InputSchemeBadge input={input} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {transaction.outputs.length > 0 ? (
        <div className="detail-block">
          <strong>Outputs</strong>
          <ul className="compact-list">
            {transaction.outputs.map((output, index) => (
              <li key={`${output.recipient}:${index}`}>
                {formatChc(output.value)} to{" "}
                <AddressWithBadge
                  address={output.recipient}
                  metadata={{
                    address_kind: output.address_kind,
                    address_scheme_id: output.address_scheme_id,
                  }}
                  short
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
