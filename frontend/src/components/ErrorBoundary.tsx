import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** When this value changes, a caught error is cleared automatically — pass the
   *  route pathname so navigating away recovers without a full page reload. */
  resetKey?: unknown;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  componentDidUpdate(prev: Props) {
    // Route changed (or any reset key) → clear the trapped error so a render
    // failure on one page doesn't strand the whole app until a full reload.
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-8 text-center">
          <h2 className="text-lg font-medium text-rose-700 dark:text-rose-300">Something went wrong.</h2>
          <p className="mt-2 text-sm text-slate-400">{this.state.error.message}</p>
          <div className="mt-4 flex justify-center gap-2">
            <button
              className="px-3 py-1 bg-slate-700 rounded text-slate-100"
              onClick={() => this.setState({ error: null })}
            >
              Try again
            </button>
            <button
              className="px-3 py-1 border border-rule rounded text-slate-300"
              onClick={() => location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
