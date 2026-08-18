import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

import type { CaseStatus, ReferralStatusCode } from "../../api/types";
import {
  CASE_TONE,
  IMPORT_TONE,
  REFERRAL_TONE,
  WAIT_TONE,
  type ImportOutcome,
  type StatusTone,
  type WaitLevel,
} from "../../design/status";

/**
 * The handoff's primitives.
 *
 * Ant Design still owns the behaviour-heavy pieces — Modal, Select, DatePicker,
 * Form, message — themed to these tokens in App.tsx. What lives here is the
 * visual layer the handoff specifies to the pixel, where antd's internals would
 * fight the padding, radii and chip marks.
 */

// ---------------------------------------------------------------------------
// Chips
// ---------------------------------------------------------------------------

function Chip({ tone, children }: { tone: StatusTone; children: ReactNode }) {
  return (
    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
      <span className="chip__mark" aria-hidden>
        {tone.mark}
      </span>
      {children}
    </span>
  );
}

export function CaseStatusChip({ status, label }: { status: CaseStatus; label: string }) {
  return <Chip tone={CASE_TONE[status]}>{label}</Chip>;
}

export function ReferralStatusChip({ status, label }: { status: ReferralStatusCode; label: string }) {
  return <Chip tone={REFERRAL_TONE[status]}>{label}</Chip>;
}

export function ImportOutcomeChip({ outcome, label }: { outcome: ImportOutcome; label: string }) {
  return <Chip tone={IMPORT_TONE[outcome]}>{label}</Chip>;
}

/** A neutral chip for counts, slots and coverage. */
export function MutedChip({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <span
      className="chip"
      style={{ color: "var(--ink-600)", background: "var(--fill-muted)", borderColor: "transparent", ...style }}
    >
      {children}
    </span>
  );
}

export function WaitBadge({ level, children }: { level: WaitLevel; children: ReactNode }) {
  const tone = WAIT_TONE[level];
  return (
    <span
      className="chip"
      style={{ color: tone.fg, background: tone.bg, borderColor: "transparent", fontSize: 12 }}
    >
      {children}
    </span>
  );
}

export function CountBadge({ children }: { children: ReactNode }) {
  return <span className="count-badge">{children}</span>;
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "destructive" | "destructive-soft";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  /** Visibly present but refusing — the parallel-limit case, which must explain itself. */
  blocked?: boolean;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "btn--primary",
  secondary: "",
  destructive: "btn--destructive",
  "destructive-soft": "btn--destructive-soft",
};

export function Button({ variant = "secondary", size = "md", blocked, className, ...props }: ButtonProps) {
  const classes = ["btn", VARIANT_CLASS[variant], size === "sm" ? "btn--sm" : "", blocked ? "btn--blocked" : ""];
  return <button type="button" className={[...classes, className].filter(Boolean).join(" ")} {...props} />;
}

// ---------------------------------------------------------------------------
// Layout atoms
// ---------------------------------------------------------------------------

export function Card({
  children,
  muted,
  onClick,
  style,
  className,
}: {
  children: ReactNode;
  muted?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
  className?: string;
}) {
  const classes = ["card", muted ? "card--muted" : "", onClick ? "card--interactive" : "", className];
  return (
    <div
      className={classes.filter(Boolean).join(" ")}
      style={style}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}

export function CapsLabel({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div className="t-caps" style={style}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start", justifyContent: "space-between" }}>
      <div>
        <h1 className="t-title">{title}</h1>
        {subtitle && (
          <div className="t-meta" style={{ marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
      {action}
    </div>
  );
}

/** A label/value pair, the unit the identity and profiling cards are built from. */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <CapsLabel>{label}</CapsLabel>
      <div style={{ marginTop: 2 }}>{children}</div>
    </div>
  );
}

export function ProgressTrack({
  value,
  height = 6,
  fill = "var(--green-500)",
  track = "var(--fill-muted)",
}: {
  /** 0–1. */
  value: number;
  height?: number;
  fill?: string;
  track?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="track" style={{ height, background: track }}>
      <div className="track__fill" style={{ width: `${pct}%`, height, background: fill }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons — inline SVG stroke paths, 24×24, stroke-width 1.7.
// No icon font: the brief's users are on 3G or worse.
// ---------------------------------------------------------------------------

export const ICON_PATHS = {
  dashboard: "M4 4h6v6H4V4zm10 0h6v6h-6V4zM4 14h6v6H4v-6zm10 0h6v6h-6v-6z",
  cases: "M4 4h10l2 3h4v13H4V4z",
  case: "M6 3h9l4 4v14H6V3z",
  queue: "M4 6h11l3 3-3 3H4V6zm0 8h8l3 3-3 3H4v-6z",
  alerts: "M12 3a6 6 0 016 6v4l2 3H4l2-3V9a6 6 0 016-6z",
  registry: "M5 3h11l3 3v15H5V3zM8 8h8M8 12h8M8 16h5",
  partners: "M3 20V9l5-4 5 4v11M13 20V12h8v8",
  users: "M8 11a3 3 0 100-6 3 3 0 000 6zm8 0a3 3 0 100-6 3 3 0 000 6zM2 20c0-3 3-5 6-5s6 2 6 5m2-5c3 0 6 2 6 5",
  search: "M11 4a7 7 0 105.2 11.7L21 20M11 4a7 7 0 010 14",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  // Dashboard tiers. Distinct silhouettes, because at 64px the label is gone
  // and the icon is the only thing telling four dashboards apart.
  woreda: "M3 20h18M6 20V10M12 20V4M18 20v-7",
  programme: "M4 19h16M7 16l3.5-4.5 3 2.5L18 8",
  results: "M12 3l2.6 5.6 6.1.8-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6L3.3 9.4l6.1-.8z",
  // Rail collapse chevrons. Two paths rather than one rotated, so the icon
  // reads correctly in a right-to-left layout if one is ever added.
  railCollapse: "M15 6l-6 6 6 6",
  railExpand: "M9 6l6 6-6 6",
  check: "M4 13l5 5L20 7",
} as const;

export function Icon({ path, size = 18 }: { path: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={path} />
    </svg>
  );
}

/** The placeholder programme mark — a gold square with a green mountain path. */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden>
      <rect width="30" height="30" rx="7" fill="var(--gold-300)" />
      <path d="M8 20l4-10 3 7 2-4 5 7z" fill="var(--green-900)" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Privacy
// ---------------------------------------------------------------------------

/**
 * Mask a phone number for a shared office.
 *
 * The handoff's shape is `+251 9•• •• 22 07`: country code and the leading 9
 * stay, the middle is dotted, and the last four digits stay so a case manager
 * can confirm they are looking at the right person without exposing the number
 * to whoever is standing behind them.
 */
export function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 6) return "•• •• •• ••";
  const tail = digits.slice(-4);
  const head = digits.startsWith("251") ? "+251 9" : `${digits.slice(0, 1)}••`;
  return `${head}•• •• ${tail.slice(0, 2)} ${tail.slice(2)}`;
}
