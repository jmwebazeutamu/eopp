/**
 * The landing page's decorative icons.
 *
 * Inline SVG paths, like `components/ui`'s `Icon` — the brief forbids an icon
 * font on a 3G connection. Kept local rather than added to `ICON_PATHS`
 * because `Icon` renders one path and several of these need two or three, and
 * because none of them appears on any authenticated screen.
 *
 * Every one is `aria-hidden`. They sit beside text that already says the same
 * thing; the design system's "never colour alone" rule has the same shape.
 */

const PATHS = {
  signal: ["M5 12.5a11 11 0 0 1 14 0", "M1.4 9a16 16 0 0 1 21.2 0", "M8.5 16.1a6 6 0 0 1 7 0", "M12 20h.01"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z", "m9 12 2 2 4-4"],
  script: ["M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"],
  phone: ["M5 2h14v20H5z", "M12 18h.01"],
  ledger: ["M3 21h18", "M12 3v7", "M8 10h8l1 11H7Z", "M8 6h8"],
  gate: ["m9 11 3 3L22 4", "M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"],
  people: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8", "M22 21v-2a4 4 0 0 0-3-3.9"],
  addPerson: ["M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2", "M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8", "M19 8v6M22 11h-6"],
  calendar: ["M3 4h18v17H3z", "M16 2v4M8 2v4M3 10h18", "m9 15 2 2 4-4"],
  bars: ["M12 20V10", "M18 20V4", "M6 20v-4"],
  hierarchy: ["M12 3v6", "M6 21v-4a6 6 0 0 1 12 0v4", "M12 9a2 2 0 1 1 0 4 2 2 0 0 1 0-4", "M4 21h16"],
  link: ["M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7", "M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"],
  card: ["M2 6h20v13H2z", "M2 11h20", "M6 15h4"],
  stamp: ["M4 4h16v12H7l-3 3Z", "M9 9h6"],
  megaphone: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z", "M12 9v4M12 16h.01"],
  chart: ["M3 3v18h18", "m7 15 4-4 3 3 5-6"],
  database: ["M12 2c5 0 9 1.3 9 3s-4 3-9 3-9-1.3-9-3 4-3 9-3Z", "M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5", "M3 12c0 1.7 4 3 9 3s9-1.3 9-3"],
} as const;

export type LandingIconName = keyof typeof PATHS;

export default function LandingIcon({ name, size = 20 }: { name: LandingIconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      {PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
