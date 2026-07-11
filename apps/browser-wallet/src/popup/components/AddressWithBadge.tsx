import { classifyAddressScheme, type AddressSchemeMetadata } from "../../shared/address_scheme";
import { shortHash } from "../../shared/formatting";
import { SchemeBadge } from "./SchemeBadge";

export function AddressWithBadge(
  { address, metadata, short = false }: { address: string; metadata?: AddressSchemeMetadata; short?: boolean },
): JSX.Element {
  const scheme = classifyAddressScheme({
    address,
    address_kind: metadata?.address_kind,
    address_scheme_id: metadata?.address_scheme_id,
  });
  return (
    <span className="address-with-badge">
      <span className="mono address-text" title={address}>{short ? shortHash(address, 10) : address}</span>
      <SchemeBadge scheme={scheme} />
    </span>
  );
}
