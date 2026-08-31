import { Component, type ErrorInfo, type ReactNode } from "react";
import { EmptyState } from "./DataState";

interface State {
  error: Error | null;
}

export class DataErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) console.error(error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <EmptyState title="This view could not be rendered">
          The data was left unchanged. Refresh the page or adjust the current
          URL filters.
        </EmptyState>
      );
    }
    return this.props.children;
  }
}
