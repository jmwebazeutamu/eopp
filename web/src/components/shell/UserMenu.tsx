import { useEffect, useRef, useState } from "react";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import LanguageSwitch from "./LanguageSwitch";

/**
 * Who is signed in, and the things that belong to them rather than to a screen.
 *
 * There was no user menu anywhere before this: the name and role sat as flat
 * text at the foot of the rail, sign-out was a bare button beside them, and the
 * language switch was three buttons occupying the right half of the header on
 * every page. All of it lives here now, one click away.
 *
 * Built rather than taken from antd's Dropdown because the trigger is a piece
 * of page furniture with its own layout in two rail widths, and because the
 * menu holds a control group (the language switch) rather than a list of
 * commands. antd keeps the behaviour-heavy components; this is not one.
 */
export default function UserMenu({
  user,
  collapsed,
  onSignOut,
  onOpenProfile,
}: {
  user: CurrentUser;
  collapsed: boolean;
  onSignOut: () => void;
  /** Opens the profile modal; the menu closes first so focus is not trapped. */
  onOpenProfile?: () => void;
}) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      // Focus goes back to what opened the menu, or it lands on the document
      // and a keyboard user restarts from the top of the page.
      trigger.current?.focus();
    };
    const onPointer = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <div ref={container} style={{ position: "relative" }}>
      {open && (
        <div
          role="dialog"
          aria-label={t("shell.account")}
          style={{
            position: "absolute",
            bottom: "calc(100% + 8px)",
            left: 0,
            width: collapsed ? 260 : "100%",
            minWidth: 240,
            background: "var(--surface)",
            color: "var(--ink-900)",
            borderRadius: "var(--r-card)",
            border: "1px solid var(--line)",
            boxShadow: "var(--overlay)",
            padding: 14,
            zIndex: 20,
          }}
        >
          <div style={{ fontWeight: 700 }}>{user.full_name}</div>
          <div className="t-meta">{user.role_display}</div>
          <div className="t-meta" style={{ marginTop: 6 }}>
            {t("shell.woreda")}: {user.woreda_assignment?.length ? user.woreda_assignment.join(", ") : t("shell.allWoredas")}
          </div>

          <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
            <div className="t-meta" style={{ marginBottom: 6 }}>
              {t("shell.language")}
            </div>
            <LanguageSwitch />
          </div>

          {/*
           * A real link to a real file, not a route.
           *
           * The manual is a standalone page served as a static file, so it has
           * to survive the app not loading — which is one of the times somebody
           * reaches for a manual. It opens in a new tab so a half-finished form
           * behind it is not thrown away.
           */}
          <a
            href="/manual.html"
            target="_blank"
            rel="noreferrer"
            onClick={() => setOpen(false)}
            style={{
              marginTop: 12,
              minHeight: 44,
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              borderRadius: "var(--r-button)",
              border: "1px solid var(--line)",
              background: "transparent",
              color: "var(--ink-900)",
              fontFamily: "var(--font-body)",
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            {t("nav.manual")}
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="sr-only">{t("shell.opensNewTab")}</span>
          </a>

          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onOpenProfile?.();
            }}
            style={{
              marginTop: 12,
              minHeight: 44,
              width: "100%",
              borderRadius: "var(--r-button)",
              border: "1px solid var(--line)",
              background: "transparent",
              color: "var(--ink-900)",
              font: "inherit",
              fontFamily: "var(--font-body)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t("profile.open")}
          </button>

          <button
            type="button"
            onClick={onSignOut}
            style={{
              marginTop: 12,
              minHeight: 44,
              width: "100%",
              borderRadius: "var(--r-button)",
              border: "1px solid var(--line)",
              background: "transparent",
              color: "var(--ink-900)",
              font: "inherit",
              fontFamily: "var(--font-body)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t("nav.signOut")}
          </button>
        </div>
      )}

      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={collapsed ? `${t("shell.account")}: ${user.full_name}` : undefined}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          minHeight: 44,
          padding: collapsed ? 0 : "0 0 0 0",
          justifyContent: collapsed ? "center" : "flex-start",
          borderRadius: 7,
          border: "none",
          background: open ? "rgba(255,255,255,.12)" : "transparent",
          color: "var(--on-dark)",
          font: "inherit",
          fontFamily: "var(--font-body)",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <Avatar name={user.full_name} />
        {!collapsed && (
          <span style={{ minWidth: 0, lineHeight: 1.25 }}>
            <span style={{ display: "block", fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {user.full_name}
            </span>
            <span
              style={{
                display: "block",
                color: "rgba(255,255,255,0.5)",
                fontSize: 11.5,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {user.role_display}
            </span>
          </span>
        )}
      </button>
    </div>
  );
}

/**
 * Initials, not a photograph. There are no avatars in this system and there is
 * no field to hold one; two letters identify the signed-in account well enough
 * to catch the shared-machine mistake this block exists to prevent.
 */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = [...parts[0]][0] ?? "";
  const last = parts.length > 1 ? ([...parts[parts.length - 1]][0] ?? "") : "";
  return (first + last).toUpperCase();
}

function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      style={{
        flexShrink: 0,
        width: 30,
        height: 30,
        borderRadius: "50%",
        background: "var(--gold-300)",
        color: "var(--green-900)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: 12,
      }}
    >
      {initialsOf(name)}
    </span>
  );
}
