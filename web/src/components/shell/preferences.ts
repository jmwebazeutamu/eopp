import { useCallback, useEffect, useState } from "react";

/**
 * Per-user interface preferences.
 *
 * Same storage strategy as `yep.lang`: localStorage, so a preference survives a
 * reload without a round trip and without a schema change. Keyed by user id,
 * because these are shared office machines — a supervisor collapsing the rail
 * must not collapse it for the case manager who signs in after them.
 *
 * Deliberately not on the User model. These are display choices with no audit
 * value, and §9's trail is for case data; putting them on the server would also
 * make every one of them a migration.
 */

const PREFIX = "yep.pref";

function storageKey(name: string, userId: string | undefined) {
  return `${PREFIX}.${userId ?? "anon"}.${name}`;
}

export function usePreference<T>(name: string, userId: string | undefined, fallback: T) {
  const [value, setValue] = useState<T>(() => read(name, userId, fallback));

  // Re-read when the signed-in user changes, so a second user on the same
  // machine gets their own preference rather than inheriting the first's.
  useEffect(() => {
    setValue(read(name, userId, fallback));
    // `fallback` is intentionally absent: a caller passing an object literal
    // would otherwise reset the preference on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, userId]);

  const store = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(storageKey(name, userId), JSON.stringify(next));
      } catch {
        // Private browsing, or a full quota. A preference is not worth an error.
      }
    },
    [name, userId],
  );

  return [value, store] as const;
}

function read<T>(name: string, userId: string | undefined, fallback: T): T {
  try {
    const raw = localStorage.getItem(storageKey(name, userId));
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}
