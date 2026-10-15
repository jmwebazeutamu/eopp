import { describe, expect, it } from "vitest";

import { splitOverflow } from "./navOverflow";

describe("splitOverflow", () => {
  it("shows everything when it fits, and reserves no space for More", () => {
    expect(splitOverflow([100, 100, 100], 320, 60, 10, null)).toEqual({ visible: [0, 1, 2], overflow: [] });
  });

  it("moves the tail behind More when it does not", () => {
    // room = 300 - 60 - 10 = 230: 100 + 10 + 100 fits, the third does not.
    expect(splitOverflow([100, 100, 100], 300, 60, 10, null)).toEqual({ visible: [0, 1], overflow: [2] });
  });

  it("keeps the current page on the row even when it is last", () => {
    const split = splitOverflow([100, 100, 100], 300, 60, 10, 2);
    expect(split.visible).toContain(2);
    expect(split.overflow).toEqual([1]);
  });

  it("never loses an item", () => {
    const split = splitOverflow([90, 120, 80, 150, 70], 260, 60, 8, 3);
    expect([...split.visible, ...split.overflow].sort()).toEqual([0, 1, 2, 3, 4]);
  });

  it("sends everything but the pinned item behind More when the row is tiny", () => {
    const split = splitOverflow([100, 100], 50, 60, 10, 1);
    expect(split.visible).toEqual([1]);
    expect(split.overflow).toEqual([0]);
  });
});
