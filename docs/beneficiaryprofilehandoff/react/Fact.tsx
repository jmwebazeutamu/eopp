import type { ReactNode } from "react";

interface FactProps {
  label: string;
  /** null renders the Add control instead of a value */
  value: ReactNode | null;
  qualifier?: string | null;
  /** true when the value is numeric — turns on tabular figures */
  numeric?: boolean;
  /** what the Add control says, e.g. "Add phone". Screen-reader text. */
  addLabel?: string;
  onAdd?: () => void;
  canEdit?: boolean;
}

/**
 * One label/value pair in the identity fact grid.
 *
 * Rule: a missing value is never blank and never "N/A". When the record
 * holds nothing and the user may edit, render a gold "Add" button that
 * opens the edit form focused on that field. When the user may not edit,
 * render an em dash.
 */
export function Fact({
  label,
  value,
  qualifier,
  numeric = false,
  addLabel,
  onAdd,
  canEdit = false,
}: FactProps) {
  return (
    <div className="fact">
      <div className="t-caps">{label}</div>
      {value !== null && value !== undefined ? (
        <div className={numeric ? "fact__value fact__value--num" : "fact__value"}>
          {value}
          {qualifier ? <span className="fact__qualifier"> {qualifier}</span> : null}
        </div>
      ) : canEdit && onAdd ? (
        <button type="button" className="fact__add" onClick={onAdd}>
          Add
          <span className="sr-only"> {addLabel ?? label.toLowerCase()}</span>
        </button>
      ) : (
        <div className="fact__value fact__qualifier" aria-label="not recorded">
          &mdash;
        </div>
      )}
    </div>
  );
}
