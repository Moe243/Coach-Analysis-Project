import { AlertTriangle, Database, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

export function LoadingState({
  label = "Loading published data",
}: {
  label?: string;
}) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <div>
        <strong>{label}</strong>
        <p>Querying the current checkpoint-seven publication.</p>
      </div>
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  return (
    <div className="state-panel state-error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <strong>Published data could not be loaded</strong>
        <p>{error.message}</p>
        <button
          className="button button-secondary"
          type="button"
          onClick={retry}
        >
          <RotateCcw size={15} aria-hidden="true" /> Retry
        </button>
      </div>
    </div>
  );
}

export function EmptyState({
  title = "No records match",
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className="state-panel">
      <Database aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}
