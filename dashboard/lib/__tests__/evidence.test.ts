import { describe, expect, it } from "vitest";
import {
  currentStateIndex,
  displayStatus,
  isVerificationFailed,
  shortHash,
  type Evidence,
} from "@/lib/evidence";

// Minimal Evidence stand-in: only `metrics.has_blocking_sort` is read by the
// functions under test, but the type requires the full shape.
function evidence(hasBlockingSort: boolean): Evidence {
  return {
    explain_plan: {},
    metrics: {
      docs_examined: 0,
      docs_returned: 0,
      has_blocking_sort: hasBlockingSort,
      millis: 0,
      stages: [],
      total_keys_examined: 0,
    },
    query: { filter: {}, limit: 0, sort: [] },
  };
}

describe("isVerificationFailed", () => {
  it("is false for diagnosed with null after", () => {
    expect(isVerificationFailed({ status: "diagnosed", after: null })).toBe(false);
  });

  it("is false for approved with null after (applying — verification pending)", () => {
    expect(isVerificationFailed({ status: "approved", after: null })).toBe(false);
  });

  it("is true for approved with after present (verification failed)", () => {
    expect(isVerificationFailed({ status: "approved", after: evidence(true) })).toBe(true);
  });

  it("does not depend on has_blocking_sort: approved + clean after is still failed", () => {
    expect(isVerificationFailed({ status: "approved", after: evidence(false) })).toBe(true);
  });

  it("is false for verified", () => {
    expect(isVerificationFailed({ status: "verified", after: evidence(false) })).toBe(false);
  });
});

describe("displayStatus", () => {
  it("diagnosed + after null -> pending-approval", () => {
    expect(displayStatus({ status: "diagnosed", after: null })).toEqual({
      key: "pending-approval",
      label: "pending approval",
    });
  });

  it("approved + after null -> approved (applying — verification pending), NOT verification-failed", () => {
    const result = displayStatus({ status: "approved", after: null });
    expect(result.key).toBe("approved");
    expect(result.key).not.toBe("verification-failed");
    expect(result.label).toBe("applying — verification pending");
  });

  it("approved + after with blocking sort -> verification-failed", () => {
    expect(displayStatus({ status: "approved", after: evidence(true) })).toEqual({
      key: "verification-failed",
      label: "verification failed",
    });
  });

  it("verified + clean after -> verified", () => {
    expect(displayStatus({ status: "verified", after: evidence(false) })).toEqual({
      key: "verified",
      label: "verified",
    });
  });

  it("rejected -> rejected", () => {
    expect(displayStatus({ status: "rejected", after: null })).toEqual({
      key: "rejected",
      label: "rejected",
    });
  });

  it("never derives a verified key from a non-verified status", () => {
    expect(displayStatus({ status: "approved", after: evidence(true) }).key).not.toBe("verified");
  });
});

describe("shortHash", () => {
  it("collapses a long hash to first8…last6", () => {
    const hash = "a20fca5ded1f8f2760a05401020813569356e8642185ba115a4ef5fc0cec640a";
    expect(shortHash(hash)).toBe("a20fca5d…ec640a");
  });

  it("passes a short hash through unchanged", () => {
    expect(shortHash("abc123")).toBe("abc123");
    expect(shortHash("0123456789abcdef")).toBe("0123456789abcdef"); // exactly 16
  });
});

describe("currentStateIndex", () => {
  it("returns null for a null pack", () => {
    expect(currentStateIndex(null)).toBeNull();
  });

  it("pending-approval (diagnosed) -> 3", () => {
    expect(currentStateIndex({ status: "diagnosed", after: null })).toBe(3);
  });

  it("approved (applying) -> 4", () => {
    expect(currentStateIndex({ status: "approved", after: null })).toBe(4);
  });

  it("verification-failed -> 5", () => {
    expect(currentStateIndex({ status: "approved", after: evidence(true) })).toBe(5);
  });

  it("verified -> 6", () => {
    expect(currentStateIndex({ status: "verified", after: evidence(false) })).toBe(6);
  });

  it("rejected -> 6", () => {
    expect(currentStateIndex({ status: "rejected", after: null })).toBe(6);
  });
});
