import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { AM, OM, STRINGS, type StringKey, type Translations } from "./strings";

/**
 * Language, the font stack and the leading that goes with it.
 *
 * Ge'ez needs more room between lines than Latin, and the two font families
 * swap order per language rather than one being a permanent fallback — an
 * Amharic screen should set Ge'ez first so Latin never wins a shared glyph.
 * Both are driven off CSS custom properties, so the switch is one write to
 * documentElement rather than a prop threaded through every component.
 */

export type Language = "en" | "am" | "om";

interface LanguageDefinition {
  code: Language;
  /** Shown on the toggle in its own script. */
  label: string;
  fontStack: string;
  leading: string;
  table: Translations;
}

const LATIN = '"Archivo", "Noto Sans Ethiopic", sans-serif';
const GEEZ = '"Noto Sans Ethiopic", "Archivo", sans-serif';

export const LANGUAGES: LanguageDefinition[] = [
  { code: "en", label: "EN", fontStack: LATIN, leading: "1.5", table: STRINGS },
  { code: "am", label: "አማርኛ", fontStack: GEEZ, leading: "1.75", table: AM },
  // Afaan Oromo is written in Latin script, so it takes the Latin stack and
  // leading and differs only in its string table.
  { code: "om", label: "Afaan Oromoo", fontStack: LATIN, leading: "1.5", table: OM },
];

const STORAGE_KEY = "yep.lang";

/**
 * The translate function's signature, exported so a helper that takes `t` as a
 * parameter states it once rather than restating it.
 *
 * A helper that widened the key to `string` did not compile: parameters are
 * contravariant, so a function accepting only `StringKey` cannot be passed
 * where any `string` is allowed. Widening it is also the wrong direction — the
 * union is what stops a typo becoming a missing translation at runtime.
 */
export type Translate = (key: StringKey, vars?: Record<string, string | number>) => string;

interface LanguageValue {
  lang: Language;
  setLang: (lang: Language) => void;
  /** Translate, with `{placeholder}` interpolation. */
  t: Translate;
}

const LanguageContext = createContext<LanguageValue | null>(null);

function definitionFor(lang: Language): LanguageDefinition {
  return LANGUAGES.find((entry) => entry.code === lang) ?? LANGUAGES[0];
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.some((entry) => entry.code === stored) ? (stored as Language) : "en";
  });

  useEffect(() => {
    const definition = definitionFor(lang);
    document.documentElement.style.setProperty("--font-body", definition.fontStack);
    document.documentElement.style.setProperty("--leading", definition.leading);
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Language) => {
    localStorage.setItem(STORAGE_KEY, next);
    setLangState(next);
  }, []);

  const t = useCallback(
    (key: StringKey, vars?: Record<string, string | number>) => {
      // Fall through to English rather than showing a key: an untranslated
      // string is a gap in the translation table, and a visible English word is
      // more use to a case manager than `case.nextAction`.
      const template = definitionFor(lang).table[key] ?? STRINGS[key];
      if (!vars) return template;
      return template.replace(/\{(\w+)\}/g, (match, name: string) =>
        name in vars ? String(vars[name]) : match,
      );
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang(): LanguageValue {
  const value = useContext(LanguageContext);
  if (!value) throw new Error("useLang must be used inside LanguageProvider");
  return value;
}
