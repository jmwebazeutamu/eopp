import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, tokens } from "../api/client";
import type { CurrentUser } from "../api/types";

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

// Exported so tests can supply a signed-in user without standing up the real
// provider, which would fetch /users/me/. `useAuth` still throws outside a
// provider — that guard catches a component mounted in the wrong place, and
// weakening it to make a test pass would remove the only thing that does.
export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore the session on reload: a stored token is not proof of a valid one,
  // so /me/ is the authority. A failure here clears rather than stalls.
  useEffect(() => {
    if (!tokens.access) {
      setLoading(false);
      return;
    }
    api
      .get<CurrentUser>("/users/me/")
      .then((response) => setUser(response.data))
      .catch(() => tokens.clear())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const response = await api.post<{ access: string; refresh: string; user: CurrentUser }>("/users/token/", {
      username,
      password,
    });
    tokens.set(response.data.access, response.data.refresh);
    setUser(response.data.user);
  }, []);

  const logout = useCallback(() => {
    tokens.clear();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside an AuthProvider");
  return context;
}
