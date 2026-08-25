import { describe, expect, it } from "vitest";

import type { Grievance } from "../api/types";
import { byUrgency, clockLabel } from "./grievanceClock";

function standing(over: Partial<Grievance["standing"]> = {}): Grievance["standing"] {
  return { state: "on_time", days: 5, due_on: "2026-09-01", ...over };
}

function grievance(state: Grievance["standing"]["state"], days: number | null): Grievance {
  return { standing: standing({ state, days }) } as Grievance;
}

describe("clockLabel", () => {
  it("says how late, not how old", () => {
    // The Age column counted days since the record was created and kept
    // counting after resolution, so every live case looked equally fine.
    const label = clockLabel(standing({ state: "late", days: -3 }));
    expect(label.key).toBe("grievances.clockLate");
    expect(label.days).toBe(3);
    expect(label.tone).toBe("late");
  });

  it("says today rather than 'due in 0 days'", () => {
    expect(clockLabel(standing({ state: "due", days: 0 })).key).toBe("grievances.clockToday");
    expect(clockLabel(standing({ state: "due", days: 2 })).key).toBe("grievances.clockDue");
  });

  it("stops the clock on a concluded case", () => {
    const label = clockLabel(standing({ state: "closed", days: 11 }));
    expect(label.key).toBe("grievances.clockClosed");
    expect(label.tone).toBe("calm");
  });

  it("does not colour a case that is simply in hand", () => {
    // Terracotta is reserved for genuine failure. A complaint with a week left
    // is not one, and a queue where everything is coloured prioritises nothing.
    expect(clockLabel(standing({ state: "on_time", days: 9 })).tone).toBe("calm");
  });

  it("says nothing rather than zero when there is no deadline", () => {
    expect(clockLabel(standing({ state: "unscheduled", days: null })).key).toBe("grievances.clockNone");
  });
});

describe("byUrgency", () => {
  it("puts late before due before the rest", () => {
    const rows = [grievance("closed", 4), grievance("on_time", 9), grievance("due", 1), grievance("late", -3)];
    expect(rows.sort(byUrgency).map((row) => row.standing.state)).toEqual(["late", "due", "on_time", "closed"]);
  });

  it("puts the most overdue at the very top", () => {
    const rows = [grievance("late", -2), grievance("late", -30), grievance("late", -9)];
    expect(rows.sort(byUrgency).map((row) => row.standing.days)).toEqual([-30, -9, -2]);
  });

  it("sinks concluded cases whatever their dates", () => {
    // A queue is a list of work, and they are not work.
    const rows = [grievance("closed", 1), grievance("on_time", 20)];
    expect(rows.sort(byUrgency)[0].standing.state).toBe("on_time");
  });
});
