import { useEffect, useRef, useState } from "react";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import AccountPanel from "./AccountPanel";

/**
 * Who is signed in, and the things that belong to them rather than to a screen.
 *
 * There was no user menu anywhere before this: the name and role sat as flat
 * text at the foot of the rail, sign-out was a bare button beside them, and the
 * language switch was three buttons occupying the right half of the header on
 * every page. All of it lives here now, one click away.
 *
 * Built rather than taken from antd's Dropdown because the menu holds a control
 * group (the language switch) rather than a list of commands. The contents are
 * `AccountPanel`, shared with the phone drawer. antd keeps the behaviour-heavy
 * components; this is not one.
 */
export default function UserMenu({
  user,
  onSignOut,
  onOpenProfile,
}: {
  user: CurrentUser;
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
    <div ref={container} className="account-menu">
      <button
        ref={trigger}
        type="button"
        className="account-trigger"
        onClick={() => setOpen((was) => !was)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`${t("shell.account")}: ${user.full_name}`}
      >
        <Avatar name={user.full_name} />
        <span className="account-trigger-text">
          <span className="account-trigger-name">{user.full_name}</span>
          <span className="account-trigger-role">{user.role_display}</span>
        </span>
      </button>

      {open && (
        <div role="dialog" aria-label={t("shell.account")} className="account-popup">
          <AccountPanel
            user={user}
            onSignOut={onSignOut}
            onOpenProfile={onOpenProfile}
            onNavigate={() => setOpen(false)}
          />
        </div>
      )}
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
