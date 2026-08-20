import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LanguageProvider } from "../../i18n/LanguageContext";
import { testUser } from "../../test/authHarness";
import Sidebar from "./Sidebar";
import { buildNav } from "./navModel";

vi.mock("./GlobalSearch", () => ({
  default: () => <div>Search</div>,
}));

vi.mock("./ScopeSelector", () => ({
  default: () => <div>Scope</div>,
}));

function renderSidebar(pathname = "/cases") {
  const user = testUser("SYSTEM_ADMIN", {
    access: {
      case_scope: "ALL",
      case_write: true,
      referral_scope: "ALL",
      referral_write: true,
      group_scope: "ALL",
      group_write: true,
      delivery_write: true,
    },
  });

  render(
    <MemoryRouter>
      <LanguageProvider>
        <div style={{ height: 600 }}>
          <Sidebar
            user={user}
            sections={buildNav(user, { openAlerts: 12 })}
            pathname={pathname}
            collapsed={false}
            onToggleCollapse={vi.fn()}
            footer={<div>Footer</div>}
          />
        </div>
      </LanguageProvider>
    </MemoryRouter>,
  );
}

describe("Sidebar", () => {
  it("lets a section collapse to reduce a long nav", async () => {
    const user = userEvent.setup();
    renderSidebar();

    expect(screen.getByRole("button", { name: "Cases" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Work" }));

    expect(screen.queryByRole("button", { name: "Cases" })).toBeNull();
    expect(screen.getByRole("button", { name: "Directory" })).toBeInTheDocument();
  });

  it("reopens the active section when navigation moves into it", () => {
    const { rerender } = render(
      <MemoryRouter>
        <LanguageProvider>
          <div style={{ height: 600 }}>
            <Sidebar
              user={testUser("SYSTEM_ADMIN", {
                access: {
                  case_scope: "ALL",
                  case_write: true,
                  referral_scope: "ALL",
                  referral_write: true,
                  group_scope: "ALL",
                  group_write: true,
                  delivery_write: true,
                },
              })}
              sections={buildNav(
                testUser("SYSTEM_ADMIN", {
                  access: {
                    case_scope: "ALL",
                    case_write: true,
                    referral_scope: "ALL",
                    referral_write: true,
                    group_scope: "ALL",
                    group_write: true,
                    delivery_write: true,
                  },
                }),
                { openAlerts: 0 },
              )}
              pathname="/cases"
              collapsed={false}
              onToggleCollapse={vi.fn()}
              footer={<div>Footer</div>}
            />
          </div>
        </LanguageProvider>
      </MemoryRouter>,
    );

    return userEvent.setup().click(screen.getByRole("button", { name: "Directory" })).then(() => {
      expect(screen.queryByRole("button", { name: "Partners" })).toBeNull();

      rerender(
        <MemoryRouter>
          <LanguageProvider>
            <div style={{ height: 600 }}>
              <Sidebar
                user={testUser("SYSTEM_ADMIN", {
                  access: {
                    case_scope: "ALL",
                    case_write: true,
                    referral_scope: "ALL",
                    referral_write: true,
                    group_scope: "ALL",
                    group_write: true,
                    delivery_write: true,
                  },
                })}
                sections={buildNav(
                  testUser("SYSTEM_ADMIN", {
                    access: {
                      case_scope: "ALL",
                      case_write: true,
                      referral_scope: "ALL",
                      referral_write: true,
                      group_scope: "ALL",
                      group_write: true,
                      delivery_write: true,
                    },
                  }),
                  { openAlerts: 0 },
                )}
                pathname="/partners"
                collapsed={false}
                onToggleCollapse={vi.fn()}
                footer={<div>Footer</div>}
              />
            </div>
          </LanguageProvider>
        </MemoryRouter>,
      );

      expect(screen.getByRole("button", { name: "Partners" })).toBeInTheDocument();
    });
  });
});
