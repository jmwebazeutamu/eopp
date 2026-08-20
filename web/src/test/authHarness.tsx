import type { ReactNode } from "react";

import { AuthContext } from "../auth/AuthContext";
import type { CurrentUser, Role } from "../api/types";

/**
 * A signed-in user for tests, without the real provider's `/users/me/` fetch.
 *
 * The dashboard tiers read the role to decide whether to draw a tab row, so a
 * tier page mounted with no auth context throws. That is the provider guard
 * doing its job; the fix belongs in the harness, not in the component.
 */
export function testUser(role: Role = "SYSTEM_ADMIN", overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: "test-user",
    username: role.toLowerCase(),
    work_email: "",
    personal_email: "",
    work_phone: "",
    personal_phone: "",
    full_name: "Test User",
    role,
    role_display: role,
    woreda_assignment: [],
    partner: null,
    partner_name: null,
    account_status: "ACTIVE",
    scopable_woredas: [],
    access: {
      case_scope: "ALL",
      case_write: true,
      referral_scope: "ALL",
      referral_write: true,
      group_scope: "NONE",
      group_write: false,
      delivery_write: false,
    },
    ...overrides,
  };
}

export function TestAuth({ user, children }: { user?: CurrentUser | null; children: ReactNode }) {
  return (
    <AuthContext.Provider
      value={{ user: user === undefined ? testUser() : user, loading: false, login: async () => {}, logout: () => {}, setUser: () => {} }}
    >
      {children}
    </AuthContext.Provider>
  );
}
