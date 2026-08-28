import { LANGUAGES, useLang } from "../../i18n/LanguageContext";

/**
 * The language switch, in one place.
 *
 * Used by the user menu and by the login screen — a first-time user needs to
 * change language *before* signing in, so it cannot live only behind an
 * authenticated menu.
 *
 * The switch changes the font stack and the leading together (Ge'ez leads at
 * 1.75, Latin at 1.5) and sets `lang` on the document element; all of that is
 * `LanguageProvider`'s job and none of it changes here. The `yep.lang` storage
 * key is unchanged.
 */
export default function LanguageSwitch({
  tone = "light",
  size = "compact",
}: {
  tone?: "light" | "dark";
  /**
   * `comfortable` raises the buttons to the 44px minimum target.
   *
   * The default stays 36 because inside the account menu these sit in a list
   * of menu rows and 44 would break that rhythm; the public landing page has
   * no such constraint and is the screen most likely to be met on a phone by
   * somebody who has never used it.
   */
  size?: "compact" | "comfortable";
}) {
  const { lang, setLang, t } = useLang();
  const onDark = tone === "dark";

  return (
    <div role="group" aria-label={t("shell.language")} style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {LANGUAGES.map((entry) => {
        const selected = lang === entry.code;
        return (
          <button
            key={entry.code}
            type="button"
            onClick={() => setLang(entry.code)}
            aria-pressed={selected}
            // `lang` on the button itself, so a screen reader pronounces
            // "አማርኛ" with Amharic phonetics rather than the page language's.
            lang={entry.code}
            style={{
              minHeight: size === "comfortable" ? 44 : 36,
              padding: size === "comfortable" ? "0 16px" : "0 12px",
              borderRadius: "var(--r-button)",
              border: `1px solid ${selected ? "var(--green-700)" : onDark ? "rgba(255,255,255,.25)" : "var(--line)"}`,
              background: selected ? "var(--green-700)" : "transparent",
              color: selected ? "var(--on-dark)" : onDark ? "var(--on-dark-2)" : "var(--ink-900)",
              fontWeight: 600,
              fontSize: 13,
              fontFamily: "var(--font-body)",
              cursor: "pointer",
            }}
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}
