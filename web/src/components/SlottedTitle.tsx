import type { ReactNode } from "react";

/**
 * A right-aligned figure column's header. When the column's rows reserve a
 * `.delta-slot` after their figures, the header reserves the same empty slot,
 * so the label ends over the figures rather than over the chips.
 */
export function SlottedTitle({ children, slot }: { children: ReactNode; slot: boolean }) {
  return (
    <>
      {children}
      {slot && <span className="delta-slot" aria-hidden="true" />}
    </>
  );
}
