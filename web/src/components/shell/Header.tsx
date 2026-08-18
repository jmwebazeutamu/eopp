import { Select } from "antd";
import { useState } from "react";

import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
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
export const HEADER_HEIGHT_PHONE = 48;

export default function Header({ isPhone = false }: { isPhone?: boolean }) {
  const { t } = useLang();
  const scope = useScope();
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header
      className={isPhone ? "on-dark" : undefined}
      style={{
        height: isPhone ? HEADER_HEIGHT_PHONE : HEADER_HEIGHT,
        flexShrink: 0,
        background: isPhone ? "var(--green-900)" : "var(--paper)",
        color: isPhone ? "var(--on-dark)" : "var(--ink-900)",
        padding: isPhone ? "0 10px" : "0 24px",
        display: "flex",
        alignItems: "center",
        gap: isPhone ? 8 : 16,
        position: "relative",
        justifyContent: isPhone ? undefined : "flex-end",
        borderBottom: isPhone ? "none" : "1px solid #e9e2d3",
      }}
    >
      {isPhone && (
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>
          {t("shell.appMark")}
        </span>
      )}

      {/* At 390px a 480px search field and a scope selector cannot both sit in
          the bar; the field truncated its own placeholder to "Searc". The
          search opens over the header instead, full width, which is also where
          a phone keyboard expects it. */}
      {isPhone ? (
        searchOpen ? (
          <div style={{ position: "absolute", inset: "0 8px", display: "flex", alignItems: "center", gap: 8 }}>
            <GlobalSearch autoFocus />
            <button
              type="button"
              onClick={() => setSearchOpen(false)}
              aria-label={t("common.close")}
              style={{
                minWidth: 44,
                minHeight: 44,
                border: "none",
                background: "transparent",
                color: "var(--on-dark)",
                font: "inherit",
                fontFamily: "var(--font-body)",
                cursor: "pointer",
              }}
            >
              {"\u2715"}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            aria-label={t("search.label")}
            style={{
              marginLeft: "auto",
              minWidth: 44,
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "none",
              background: "transparent",
              color: "var(--on-dark)",
              cursor: "pointer",
            }}
          >
            <Icon path={ICON_PATHS.search} size={20} />
          </button>
        )
      ) : null}

      <div style={{ marginLeft: isPhone ? 0 : "auto", display: "flex", alignItems: "center", gap: 8 }}>
        {scope.selectable ? (
          <Select
            aria-label={t("shell.scope")}
            value={scope.woreda}
            onChange={scope.setWoreda}
            size="middle"
            style={{ minWidth: isPhone ? 120 : 160 }}
            options={[
              { value: SCOPE_ALL, label: t("shell.allWoredas") },
              ...scope.options.map((name) => ({ value: name, label: name })),
            ]}
          />
        ) : (
          <span style={{ color: isPhone ? "var(--on-dark-2)" : "var(--ink-600)", fontSize: 13, whiteSpace: "nowrap" }}>{scope.label}</span>
        )}
      </div>
    </header>
  );
}
