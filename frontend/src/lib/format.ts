import type { CoachRole } from "../api/contracts";

export function number(value: unknown, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(value)
    : "—";
}

export function signed(value: unknown, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${number(value, digits)}`;
}

export function integer(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)
    : "—";
}

export function percent(value: unknown, digits = 1): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${number(value * 100, digits)}%`
    : "—";
}

export function roleLabel(role: CoachRole | string): string {
  const values: Record<string, string> = {
    head_coach: "Head coach",
    offensive_coordinator: "Offensive coordinator",
    play_caller: "Play-caller",
    quarterbacks_coach: "QB coach",
  };
  return values[role] ?? role.replaceAll("_", " ");
}

export function payloadNumber(
  payload: Record<string, unknown>,
  key: string,
): number | null {
  const value = payload[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
