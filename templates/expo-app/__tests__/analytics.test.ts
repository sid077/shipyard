import { MemorySink, initAnalytics, setAnalyticsSink, track } from '@/analytics';

describe('analytics', () => {
  it('records events against the taxonomy', () => {
    const sink = new MemorySink();
    setAnalyticsSink(sink);

    track({ name: 'app_open' });
    track({ name: 'purchase', properties: { sku: 'pro_lifetime', price_usd: 4.99 } });

    expect(sink.events).toEqual([
      { name: 'app_open', properties: undefined },
      { name: 'purchase', properties: { sku: 'pro_lifetime', price_usd: 4.99 } },
    ]);
  });

  it('stays in no-op mode when PostHog is not configured', async () => {
    delete process.env.EXPO_PUBLIC_POSTHOG_KEY;
    await expect(initAnalytics()).resolves.toBe(false);
    // Tracking after a failed init must not throw.
    expect(() => track({ name: 'app_open' })).not.toThrow();
  });
});
