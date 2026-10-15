import { Select } from "antd";

import { useLang } from "../../i18n/LanguageContext";
import { SCOPE_ALL, useScope } from "./ScopeContext";

/**
 * The woreda scope control.
 *
 * Lives in the header, beside global search: those two are the only
 * shell-global controls, both answering "what am I looking at" before any page
 * decides anything. It is deliberately not in a page header — the scope frames
 * every screen, and a per-page control reads as a page-local filter, which is
 * the confusion the scope was introduced to remove.
 *
 * It went missing once when the top bar was removed in a redesign. Every screen
 * still *read* the scope — subtitles kept saying "All woredas" — but nothing
 * could change it, so a supervisor covering three woredas could not narrow to
 * one. That was REG-01.
 *
 * One component, used by the header and by the phone drawer.
 */
export default function ScopeSelector({ variant = "header" }: { variant?: "header" | "sheet" }) {
  const { t } = useLang();
  const scope = useScope();

  // A single-woreda account has no choice to make, but still needs to know
  // which woreda it is reading.
  if (!scope.selectable) {
    return (
      <div
        className="t-meta"
        style={{ color: variant === "header" ? "var(--on-dark-2)" : undefined, padding: "2px 2px 0" }}
      >
        {scope.label}
      </div>
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
