import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({
  total,
  offset,
  limit,
  onChange,
}: {
  total: number;
  offset: number;
  limit: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const first = offset + 1;
  const last = Math.min(total, offset + limit);
  return (
    <nav className="pagination" aria-label="Results pages">
      <p aria-live="polite">
        {first}–{last} of {total.toLocaleString()}
      </p>
      <div>
        <button
          className="icon-button"
          type="button"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
          aria-label="Previous page"
        >
          <ChevronLeft aria-hidden="true" />
        </button>
        <button
          className="icon-button"
          type="button"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
          aria-label="Next page"
        >
          <ChevronRight aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}
