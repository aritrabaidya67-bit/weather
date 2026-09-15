/**
 * Route-level error boundary.
 *
 * A page that throws used to blank the entire application, which reads as "the
 * section is broken" with no way back. The boundary keeps the header and
 * navigation alive, states what happened in plain language, and hides the stack
 * behind a disclosure so the fault stays debuggable.
 */

import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Disclosure } from "./Ui";

type Props = { children: ReactNode; title?: string };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Section crashed:", error, info.componentStack);
  }

  private readonly reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="panel p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-rose-500/10 text-rose-600 dark:text-rose-300">
            <AlertTriangle size={18} aria-hidden />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              {this.props.title ?? "This section could not be displayed"}
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
              The rest of the platform is still running: sensor ingestion, alerts and history are unaffected. Use the
              navigation to open another section, or retry this view.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={this.reset}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <RotateCcw size={13} aria-hidden />
                Retry this view
              </button>
              <Disclosure label="Technical details">
                <pre className="max-w-full overflow-x-auto rounded-xl bg-slate-900/90 p-3 text-[11px] leading-relaxed text-rose-200">
                  {error.message}
                  {error.stack ? `\n\n${error.stack.split("\n").slice(0, 6).join("\n")}` : ""}
                </pre>
              </Disclosure>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
