import type { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "positive" | "negative" | "neutral";
}) {
  return (
    <article className={`metric-card ${tone ? `metric-card-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </article>
  );
}
