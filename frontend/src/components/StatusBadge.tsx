import clsx from "clsx";

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  return (
    <span
      className={clsx("status-badge", {
        "status-positive": ["verified", "eligible", "high"].includes(
          normalized,
        ),
        "status-warning": ["provisional", "medium", "exploratory"].some(
          (term) => normalized.includes(term),
        ),
        "status-muted": ["ineligible", "low", "suppressed"].some((term) =>
          normalized.includes(term),
        ),
        "status-danger": normalized.includes("conflict"),
      })}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
