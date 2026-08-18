import { Outlet } from "react-router-dom";

/**
 * The wrapper the four tiers render inside.
 *
 * It used to own the tab strip and the tier table as well. The tabs moved into
 * `TierPage`, so they can sit *beneath* each tier's title rather than above it,
 * and the table moved into `tierAccess.ts`, where `App.tsx` and the sidebar can
 * read it without importing a component.
 *
 * What is left is the page frame, and it stays a component of its own because
 * the four tiers must not each rebuild it.
 */
export default function DashboardLayout() {
  return (
    <div className="page stack">
      <Outlet />
    </div>
  );
}
