import type { SchemeUiInfo } from "../../shared/address_scheme";

export function SchemeBadge({ scheme }: { scheme: SchemeUiInfo }): JSX.Element {
  return (
    <span
      className={`scheme-badge scheme-badge-${scheme.kind}`}
      title={scheme.title}
      aria-label={`${scheme.label}: ${scheme.title}`}
    >
      {scheme.label}
    </span>
  );
}
