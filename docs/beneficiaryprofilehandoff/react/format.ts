/** Shared formatters. Amharic locale is the app default (html lang="am"). */

const DATE_FMT = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** 2025-07-16 -> "16 Jul 2025". Null-safe. */
export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  return DATE_FMT.format(new Date(iso));
}

/** "12 Aug 2026 · 12 days ago" */
export function formatDateWithAgo(iso: string | null, today = new Date()): string | null {
  const base = formatDate(iso);
  if (!base) return null;
  const days = Math.round((today.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return `${base} · today`;
  if (days === 1) return `${base} · yesterday`;
  if (days < 30) return `${base} · ${days} days ago`;
  const months = Math.round(days / 30);
  return `${base} · ${months} month${months === 1 ? "" : "s"} ago`;
}

/**
 * "1040.00" -> "1,040.00". Input is a decimal STRING from the API.
 * Never parse money to a float for display.
 */
export function formatMoney(value: string): string {
  const [whole, fraction = "00"] = value.split(".");
  const sign = whole.startsWith("-") ? "-" : "";
  const digits = whole.replace("-", "");
  return `${sign}${digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}

/** +251912345678 -> "+251 91 234 5678" */
export function formatPhone(e164: string | null): string | null {
  if (!e164) return null;
  const m = /^\+251(\d{2})(\d{3})(\d{4})$/.exec(e164);
  return m ? `+251 ${m[1]} ${m[2]} ${m[3]}` : e164;
}

/** "Aster Abebe" -> "AA". Falls back to one letter. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
