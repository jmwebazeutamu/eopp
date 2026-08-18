import { Select } from "antd";

import { useLang } from "../../i18n/LanguageContext";
import GlobalSearch from "./GlobalSearch";
import { SCOPE_ALL, useScope } from "./ScopeContext";

/**
 * The header, doing three jobs in 56px.
 *
 * It used to be an 80px bar carrying the full product name a second time (the
 * rail said it too), a "Woreda: —" label that was empty for exactly the
 * accounts that can see every woreda, and the language switch. The name belongs
 * on the login screen, the language switch moved into the account menu, and the
 * woreda label became the control it was reaching for.
 */
export const HEADER_HEIGHT = 56;

export default function Header() {
  const { t } = useLang();
  const scope = useScope();

  return (
    <header
      style={{
        height: HEADER_HEIGHT,
        flexShrink: 0,
        background: "var(--green-900)",
        color: "var(--on-dark)",
        padding: "0 16px",
        display: "flex",
        alignItems: "center",
        gap: 16,
      }}
    >
      <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>
        {t("shell.appMark")}
      </span>

      <GlobalSearch />

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
        {scope.selectable ? (
          <Select
            aria-label={t("shell.scope")}
            value={scope.woreda}
            onChange={scope.setWoreda}
            size="middle"
            style={{ minWidth: 160 }}
            options={[
              { value: SCOPE_ALL, label: t("shell.allWoredas") },
              ...scope.options.map((name) => ({ value: name, label: name })),
            ]}
          />
        ) : (
          // A single-woreda account has no choice to make, but still needs to
          // know which woreda it is reading. Stating it beats an inert control.
          <span style={{ color: "var(--on-dark-2)", fontSize: 13, whiteSpace: "nowrap" }}>{scope.label}</span>
        )}
      </div>
    </header>
  );
}
