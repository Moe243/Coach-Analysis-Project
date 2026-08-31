import {
  integer,
  number,
  payloadNumber,
  percent,
  roleLabel,
  signed,
} from "./format";

describe("formatters", () => {
  it("formats finite metrics and signed effects", () => {
    expect(number(0.1234, 3)).toBe("0.123");
    expect(signed(0.1234)).toBe("+0.123");
    expect(signed(-0.1)).toBe("-0.100");
  });

  it("preserves missing values instead of displaying zero", () => {
    expect(number(null)).toBe("—");
    expect(percent(undefined)).toBe("—");
    expect(payloadNumber({}, "missing")).toBeNull();
  });

  it("formats rates, counts, and role labels", () => {
    expect(percent(0.456)).toBe("45.6%");
    expect(integer(1234)).toBe("1,234");
    expect(roleLabel("quarterbacks_coach")).toBe("QB coach");
  });
});
