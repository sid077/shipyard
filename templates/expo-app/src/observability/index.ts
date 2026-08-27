/**
 * Error reporting behind one seam.
 *
 * The template ships with a console reporter so a fresh clone builds and tests
 * green with no account anywhere. Wiring a crash reporter is a one-line swap in
 * `initObservability`, and the release runbook says to do it before shipping.
 */

export type ErrorReporter = {
  captureException(error: unknown, context?: Record<string, unknown>): void;
  captureMessage(message: string, context?: Record<string, unknown>): void;
};

export class ConsoleReporter implements ErrorReporter {
  captureException(error: unknown, context?: Record<string, unknown>): void {
    console.error('[error]', error, context ?? {});
  }
  captureMessage(message: string, context?: Record<string, unknown>): void {
    console.warn('[message]', message, context ?? {});
  }
}

export class MemoryReporter implements ErrorReporter {
  readonly errors: unknown[] = [];
  readonly messages: string[] = [];
  captureException(error: unknown): void {
    this.errors.push(error);
  }
  captureMessage(message: string): void {
    this.messages.push(message);
  }
}

let reporter: ErrorReporter = new ConsoleReporter();

export function setErrorReporter(next: ErrorReporter): void {
  reporter = next;
}

export function reportError(error: unknown, context?: Record<string, unknown>): void {
  reporter.captureException(error, context);
}

export function reportMessage(message: string, context?: Record<string, unknown>): void {
  reporter.captureMessage(message, context);
}

export function initObservability(): void {
  // Swap in a crash reporter here once EXPO_PUBLIC_SENTRY_DSN is provisioned.
  setErrorReporter(new ConsoleReporter());
}
