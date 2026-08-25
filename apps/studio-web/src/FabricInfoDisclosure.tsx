import type { ReactNode } from "react";

export function FabricInfoDisclosure({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details
      className={`fabric-info-disclosure ${className}`.trim()}
      onClick={(event) => event.stopPropagation()}
    >
      <summary title={label}>
        <span aria-hidden="true">ⓘ</span>
        <span className="fabric-visually-hidden">{label}</span>
      </summary>
      <div className="fabric-info-content">{children}</div>
    </details>
  );
}
