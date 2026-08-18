/**
 * How every dashboard states its own age.
 *
 * Three pages formatted the server's `as_of` three different ways — one
 * date-only, one date and seconds, one time-only with no date at all — and all
 * three rendered in the viewer's timezone. A supervisor in another timezone
 * therefore saw a different as-of date from the one the figures were computed
 * for, and the time-only version could not be read at all after midnight.
 *
 * Pinned to Africa/Addis_Ababa, which is where the programme runs and the
 * timezone the records are stamped in. The date is never dropped.
 */
export const PROGRAMME_TIME_ZONE = "Africa/Addis_Ababa";

export function formatAsOf(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: PROGRAMME_TIME_ZONE,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(when);
}
