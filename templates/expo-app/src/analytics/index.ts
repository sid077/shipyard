/**
 * The analytics taxonomy is a closed union on purpose: an engineer cannot
 * invent an event name, because the type checker rejects it. The PRD's success
 * metrics reference these names, so the two cannot drift.
 */

export type AnalyticsEvent =
  | { name: 'app_open'; properties?: Record<string, never> }
  | { name: 'activation'; properties: { feature: string } }
  | { name: 'paywall_view'; properties: { placement: string; trigger: string } }
  | { name: 'paywall_dismissed'; properties: { placement: string } }
  | { name: 'trial_start'; properties: { sku: string } }
  | { name: 'purchase'; properties: { sku: string; price_usd: number } }
  | { name: 'purchase_failed'; properties: { sku: string; reason: string } }
  | { name: 'quota_exhausted'; properties: { feature: string; limit: number } }
  | { name: 'churn_signal'; properties: { reason: string } };

/** Analytics values must survive a JSON round trip to any sink. */
export type AnalyticsProperties = Record<string, string | number | boolean | null>;

export type AnalyticsSink = {
  capture(name: string, properties?: AnalyticsProperties): void;
  identify(distinctId: string, properties?: AnalyticsProperties): void;
};

/** Records events in memory. Used before init, on web, and in tests. */
export class MemorySink implements AnalyticsSink {
  readonly events: { name: string; properties?: AnalyticsProperties }[] = [];
  capture(name: string, properties?: AnalyticsProperties): void {
    this.events.push({ name, properties });
  }
  identify(): void {}
  reset(): void {
    this.events.length = 0;
  }
}

let sink: AnalyticsSink = new MemorySink();

export function setAnalyticsSink(next: AnalyticsSink): void {
  sink = next;
}

export function getAnalyticsSink(): AnalyticsSink {
  return sink;
}

export function track(event: AnalyticsEvent): void {
  sink.capture(event.name, event.properties);
}

export function identify(distinctId: string, properties?: AnalyticsProperties): void {
  sink.identify(distinctId, properties);
}

/**
 * Attach PostHog if a key is configured. Without one the app keeps the memory
 * sink, so a missing key degrades analytics rather than breaking the build.
 */
export async function initAnalytics(): Promise<boolean> {
  const apiKey = process.env.EXPO_PUBLIC_POSTHOG_KEY;
  if (!apiKey) return false;
  try {
    const { PostHog } = await import('posthog-react-native');
    const client = new PostHog(apiKey, {
      host: process.env.EXPO_PUBLIC_POSTHOG_HOST ?? 'https://us.i.posthog.com',
    });
    setAnalyticsSink({
      capture: (name, properties) => client.capture(name, properties),
      identify: (distinctId, properties) => client.identify(distinctId, properties),
    });
    return true;
  } catch {
    // A missing or broken native module must never take the app down.
    return false;
  }
}
