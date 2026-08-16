# Referral Stack Timeline: Component Development Prompt

For Claude Code. Companion to `YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`, Sprint 3 ("Referral engine core"), deliverable "Case manager UI: initiate, confirm/decline, stack timeline."

## Paste This to Claude Code

```
Build the ReferralStackTimeline React component described in docs/REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md.
Read that file fully first. Implement the component, write unit tests for the layout
logic (lane assignment, parallel grouping, dependency arrows), and wire it into the
case detail page built in Sprint 1. Follow the acceptance criteria at the end of the
file as your definition of done for this component.
```

## Context

The Concept Note (v6) includes a mockup, Figure 4, of what a youth's referral history should look like: one row per referral, laid out across time, color-coded by status, with arrows showing which referral triggered the next one. The goal is a real component that renders this from live data on the case detail screen, not a static illustration.

## What the Reference Mockup Shows

- One horizontal lane per referral (Ref 1, Ref 2, Ref 3...), stacked top to bottom.
- Each referral is a bar spanning the months it was active, color-coded: green for completed, red for failed, orange for active.
- Arrows connect a completed or failed referral to the one it produced, labeled "onward" or "replacement."
- Two referrals get a fifth and sixth legend color for "parallel."
- A row of month/stage bands runs across the top (Registration & Assessment, Life Skills Training, TVET Enrolment, and so on).

## Fix Before Building: the Mockup's Legend Conflates Two Different Things

The mockup's legend has five colors: Completed, Failed, Active, Parallel referral (simultaneous), and Additional/parallel active referral. The last two aren't a referral *status*, they're a referral *structure*: they just mark that it happens to overlap in time with another referral. This is the same status/trigger/parallel conflation flagged in the platform's referral taxonomy (`YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`, Section 5): a referral's `status` (Completed, Active, Failed, and so on) and its concurrency (`parallel_group_id`) are independent facts about it, and a real case can have a parallel Complementary Service referral that's also Failed, which the mockup's five-color scheme can't represent.

Build the real component so color encodes status only, and parallel concurrency is shown structurally, not with its own colors. See "Visual Requirements" below.

## Data Source

The component receives an already-fetched list of the case's referrals as a prop (`GET /api/cases/{case_id}/referrals/`, per the Referral entity in the dev spec, Section 4.6). It does no fetching and no server-side aggregation of its own.

```ts
interface ReferralTimelineItem {
  referralId: string;
  caseId: string;
  referralCategory: string;   // Training | Employment/Placement | Apprenticeship | Enterprise
                               // | Finance Access | Market Linkage | Complementary Service
                               // | Coaching | Other
  receivingPartnerName: string;
  status: 'pending_confirmation' | 'active' | 'completed' | 'failed' | 'replaced' | 'cancelled';
  referralTrigger: 'manual' | 'onward' | 'replacement';
  initiatedDate: string;        // ISO date
  outcomeDate?: string;         // ISO date; set when status is completed or failed
  failureReasonCode?: string;
  parentReferralId?: string;    // set for onward/replacement referrals; the referral that preceded this one
  replacementReferralId?: string; // set once this referral has been replaced
  parallelGroupId?: string;     // referrals sharing this id ran concurrently
  notes?: string;
}
```

## Visual Requirements

- One lane per referral, ordered by `initiatedDate`.
- **X-axis is real time**, not idealized month labels. Scale to the case's actual date range (first `initiatedDate` to today, or the last `outcomeDate`). Pick tick intervals (weekly, monthly) based on the span; don't hardcode "Month 1" through "Month 6."
- Each bar spans `initiatedDate` to `outcomeDate`, or to today if the referral is still Pending or Active.
- **Bar color is status only:**
  | Status | Color |
  |---|---|
  | Completed | Green |
  | Active | Amber/orange |
  | Failed | Red |
  | Pending Confirmation | Light grey/blue, dashed border |
  | Cancelled | Grey, reduced opacity |
  | Replaced | Same as Failed, plus a small "replaced" icon |
- **Parallel referrals** (same `parallelGroupId`): render their lanes adjacent with a shared bracket on the left edge and a small "parallel" badge, not a distinct color. Hovering one bar highlights both.
- **Dependency arrows:** draw a connector from a referral to the one it produced via `parentReferralId`. Label the arrow "onward" if the child's `referralTrigger` is `onward`, or "replacement" if it's `replacement`.
- Each bar's label is `referralCategory` + `receivingPartnerName`, truncated with a tooltip on hover showing the full detail: category, partner, trigger, initiated date, outcome date, outcome type or failure reason.
- Clicking a bar calls `onReferralClick(referralId)`; it does not open anything itself. Wire it to whatever referral detail drawer Sprint 3's initiate/confirm/decline flow already built. Don't build a second one.
- Legend: five status swatches, plus one legend entry for the parallel bracket. Not seven colors.
- Empty state: a case with no referrals yet shows "No referrals yet," not a blank chart.

## Non-Goals for v1

- No editing or creating referrals from this view. Read-only.
- No stage bands (Registration & Assessment / Life Skills Training / TVET Enrolment / ...) across the top. Those stages aren't a modeled entity in the platform (see the dev spec's Core Entity Model). Deriving them reliably from live data (probably from Pathway Assignment history) is a separate future task. Leave it out rather than hardcoding a stage list that won't match real cases.

## Suggested Implementation

- `ReferralStackTimeline`, a React + TypeScript component in `web/src/components/referrals/`.
- Use D3.js (`d3-scale` for the time axis, SVG for rendering) rather than a pre-built Gantt/timeline library. Off-the-shelf options like `frappe-gantt` or `vis-timeline` don't cleanly support status-only coloring plus parallel brackets plus dependency arrows together; you'd fight the library as much as you'd save. If shipping speed matters more than fidelity, `frappe-gantt` is a workable fallback since it has built-in dependency arrows, but expect to override its styling for the parallel bracket and status coloring.
- Use Ant Design (`Tooltip`, `Popover`, `Tag`) for the surrounding chrome, consistent with the rest of the web app.

```ts
interface ReferralStackTimelineProps {
  referrals: ReferralTimelineItem[];
  onReferralClick?: (referralId: string) => void;
}
```

## Acceptance Criteria

- [ ] Renders correctly for a single sequential referral chain (no parallel, no failures).
- [ ] Renders correctly for two parallel active referrals (bracket, not a distinct color).
- [ ] Renders correctly for a failed referral followed by a replacement (red bar, arrow labeled "replacement" to the new bar).
- [ ] Renders correctly for an onward chain of 3 or more hops.
- [ ] Handles a case with zero referrals (empty state, not a blank chart).
- [ ] Time axis scales to the actual data range; no hardcoded month labels.
- [ ] Meets the Definition of Done in `YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`, Section 10.1: layout logic has unit tests, code is reviewed, and the component is demonstrated in the staging environment before the sprint is marked done.
