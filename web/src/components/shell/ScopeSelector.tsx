import { Select, Tooltip } from "antd";

import { useLang } from "../../i18n/LanguageContext";
import { SCOPE_ALL, useScope } from "./ScopeContext";

/**
 * The woreda scope control.
 *
 * Lives in the rail, directly under global search: those two are the only
 * shell-global controls, both answering "what am I looking at" before any page
 * decides anything. It is deliberately not in a page header — the scope frames
 * every screen, and a per-page control reads as a page-local filter, which is
 * the confusion the scope was introduced to remove.
 *
 * It went missing when the top bar was removed in the redesign. Every screen
 * still *read* the scope — subtitles kept saying "All woredas" — but nothing
 * could change it, so a supervisor covering three woredas could not narrow to
 * one. That was REG-01.
 *
 * One component, used by the rail and by the phone's More sheet.
 */
export default function ScopeSelector({
  variant = "rail",
  onExpand,
}: {
  /** `rail` on dark green, `sheet` on paper, `collapsed` for the 60px rail. */
  variant?: "rail" | "sheet" | "collapsed";
  /** Collapsed only: opens the rail so the full control is reachable. */
  onExpand?: () => void;
}) {
  const { t } = useLang();
  const scope = useScope();

  // A single-woreda account has no choice to make, but still needs to know
  // which woreda it is reading.
  if (!scope.selectable) {
    if (variant === "collapsed") return null;
    return (
      <div
        className="t-meta"
        style={{ color: variant === "rail" ? "var(--on-dark-2)" : undefined, padding: "2px 2px 0" }}
      >
        {scope.label}
      </div>
    );
  }

  if (variant === "collapsed") {
    // 60px cannot hold a select. The initials keep the current scope visible —
    // which is the part that must not be lost — and one click opens the rail.
    return (
      <Tooltip title={`${t("shell.scope")}: ${scope.label}`} placement="right">
        <button
          type="button"
          onClick={onExpand}
          aria-label={`${t("shell.scope")}: ${scope.label}`}
          style={{
            width: 44,
            height: 32,
            margin: "0 auto 4px",
            display: "block",
            borderRadius: "var(--r-button)",
            border: "1px solid rgba(255,255,255,.25)",
            background: "rgba(255,255,255,.10)",
            color: "var(--on-dark)",
            font: "inherit",
            fontFamily: "var(--font-body)",
            fontSize: 11,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          {shortScope(scope.woreda, t("shell.allShort"))}
        </button>
      </Tooltip>
    );
  }

  return (
    <Select
      aria-label={t("shell.scope")}
      value={scope.woreda}
      onChange={scope.setWoreda}
      size="middle"
      style={{ width: "100%" }}
      options={[
        { value: SCOPE_ALL, label: t("shell.allWoredas") },
        ...scope.options.map((name) => ({ value: name, label: name })),
      ]}
    />
  );
}

/** Three characters at most; the tooltip and aria-label carry the full name. */
function shortScope(woreda: string, allLabel: string): string {
  if (!woreda) return allLabel;
  return woreda.slice(0, 3).toUpperCase();
}
