# Referral Stack Timeline: Rendering Fix Prompt

For Claude Code. Follow-up to `REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`. The component exists and the data model behind it is right; the rendering doesn't look like a timeline yet. This file describes the gap and what to change.

## Paste This to Claude Code

```
The ReferralStackTimeline component (docs/REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md) is
rendering referrals as small fixed-size tokens with a text list underneath, not as a
time-scaled bar chart. Read docs/REFERRAL_TIMELINE_RENDERING_FIX_PROMPT.md fully, then fix
the rendering to match it: real date axis, each referral as a horizontal bar positioned and
sized by its actual date range, labels on the bars themselves. Keep the slot/exempt lane
model and the six-status color legend as they are, both are correct. Re-run the acceptance
criteria at the end of REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md when done.
```

## What's Right, Keep It

Looking at the current build:

- The **Slot 1 / Slot 2 / Exempt** lane structure is a good concrete implementation of the two-referral parallel cap plus the Complementary Service exemption from `YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md` Section 6.3. Don't change this data model.
- The **six-status color legend** (Pending confirmation, Active, Completed, Failed, Replaced, Cancelled) matches the status-only coloring called for in `REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`, and is a cleaner set than the original concept note mockup. Keep it, including the icon-per-status convention (clock, dot, checkmark, X, undo arrow, no-entry sign).

## What's Wrong

The current render shows each referral as a small fixed-size square pill floating near a single "AUG" column header, with the actual referral details (category, partner, dates) listed as plain text underneath the row instead of on the timeline. There's no visible date axis beyond one month label, so there's no way to see when anything happened relative to anything else, and every referral looks the same size regardless of whether it ran for one day or is still ongoing.

Specifically:

1. **No real date axis.** Only a single "AUG" label appears. There should be a full axis with tick marks (days or weeks, depending on the zoom level) so bar position is readable at a glance.
2. **Referrals render as fixed-size tokens, not bars sized by duration.** A referral active for a single day and a referral that's been ongoing for three weeks currently look identical. Bar width must be computed from `initiatedDate` to `outcomeDate` (or to today, for Active/Pending referrals with no `outcomeDate` yet).
3. **Ongoing referrals don't show as open-ended.** `Employment / Placement · 15 Aug 2026 – ongoing` should render as a bar starting at 15 Aug and extending to today, with a visual marker (arrow, fade, or dashed right edge) indicating it isn't closed yet, not a static token.
4. **Labels live in a separate text block instead of on the bar.** Move `referralCategory` + partner name onto or directly beside each bar, the way the original mockup and `REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md` specify, so a lane with several referrals reads left to right as a timeline, not as a pill row followed by an unrelated text dump.
5. **Very short referrals need a minimum visible width.** A same-day referral (`16 Aug 2026 – 16 Aug 2026`) will compute to near-zero pixel width on a real time scale. Give bars a minimum rendered width (for example 8-12px) so they stay visible and clickable, with the true duration available in the tooltip.
6. **No dependency arrows yet.** Once there's an onward or replacement referral in the data, confirm the connector line and "onward"/"replacement" label from `REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md` actually render between the two bars. Test this with a Failed referral followed by its Replacement, since the current screenshot's data doesn't include one.

## Concrete Fix

- Compute a `d3.scaleTime()` (or equivalent) domain from the earliest `initiatedDate` across all referrals in the case to `max(today, latest outcomeDate)`. Render axis ticks against this scale, not a single hardcoded month label.
- For each referral, render a `<rect>` (or styled div, if not using SVG) whose `x` and `width` come from the scale applied to `initiatedDate` and `outcomeDate ?? today`. Apply the minimum-width floor from point 5 above.
- Render the label inside or immediately to the right of the bar, truncating with an ellipsis and a full-text tooltip on overflow, consistent with the original spec.
- Keep one lane per slot (`Slot 1`, `Slot 2`, `Exempt`), each lane showing its own referrals as bars along the shared time axis, stacking vertically within the lane only if two bars in the same slot overlap in time (shouldn't normally happen given the parallel cap logic, but don't let it silently overlap and hide a bar if it does).
- Verify against the acceptance criteria in `REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md`: sequential chain, two parallel actives, a failed referral followed by its replacement, an onward chain of 3+, and the empty state, once there's enough test data to cover each case.
