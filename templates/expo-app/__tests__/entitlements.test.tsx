import { render, screen, userEvent } from '@testing-library/react-native';
import { Text } from 'react-native';

import { MemorySink, setAnalyticsSink } from '@/analytics';
import { Button } from '@/components/button';
import {
  entitlementFor,
  firstLockedFeature,
  firstMeteredFeature,
  freeLimitFor,
  headlinePrice,
  monetization,
} from '@/config/monetization';
import {
  NoopPurchaseProvider,
  StubPurchaseProvider,
  setPurchaseProvider,
} from '@/purchases/client';
import { EntitlementsProvider, useEntitlement, useEntitlements } from '@/purchases/entitlements';
import { MemoryUsageStore, setUsageStore } from '@/purchases/usage';

/**
 * These derive from whatever monetization plan is applied, so they keep
 * verifying the money path after the pipeline swaps in a real product.
 */
const METERED = firstMeteredFeature();
const LOCKED = firstLockedFeature();
const LIMIT = METERED ? (freeLimitFor(METERED) ?? 0) : 0;
const ENTITLEMENT = METERED ? entitlementFor(METERED) : null;
const ALL_ENTITLEMENTS = Object.keys(monetization.entitlements);
const PRICE = headlinePrice();

function Harness({ feature }: { feature: string }) {
  const { allowed, reason, remaining, recordUse } = useEntitlement(feature);
  const { purchase } = useEntitlements();
  return (
    <>
      <Text testID="reason">{reason}</Text>
      <Text testID="allowed">{String(allowed)}</Text>
      <Text testID="remaining">{String(remaining)}</Text>
      <Button testID="use" label="use" onPress={() => void recordUse()} />
      <Button testID="buy" label="buy" onPress={() => void purchase(PRICE.sku)} />
    </>
  );
}

async function renderHarness(feature: string) {
  return render(
    <EntitlementsProvider>
      <Harness feature={feature} />
    </EntitlementsProvider>
  );
}

let sink: MemorySink;

beforeEach(() => {
  sink = new MemorySink();
  setAnalyticsSink(sink);
  setUsageStore(new MemoryUsageStore());
  setPurchaseProvider(new NoopPurchaseProvider());
});

it('declares at least one paid feature, or the paywall has nothing to sell', () => {
  expect(ALL_ENTITLEMENTS.length).toBeGreaterThan(0);
  expect(Object.values(monetization.entitlements).flat().length).toBeGreaterThan(0);
});

// A plan with no metered feature is valid (everything is locked until purchase),
// so these run only when the applied plan actually meters something.
const describeMetered = METERED ? describe : describe.skip;

describeMetered('a free user', () => {
  it('may use the metered feature while the free allowance lasts', async () => {
    await renderHarness(METERED!);

    expect(await screen.findByTestId('reason')).toHaveTextContent('free_quota');
    expect(screen.getByTestId('allowed')).toHaveTextContent('true');
    expect(screen.getByTestId('remaining')).toHaveTextContent(String(LIMIT));
  });

  it('counts down and locks at exactly the configured limit', async () => {
    const user = userEvent.setup();
    await renderHarness(METERED!);
    await screen.findByTestId('reason');

    for (let i = 0; i < LIMIT; i += 1) {
      await user.press(screen.getByTestId('use'));
    }

    expect(screen.getByTestId('remaining')).toHaveTextContent('0');
    expect(screen.getByTestId('reason')).toHaveTextContent('quota_exhausted');
    expect(screen.getByTestId('allowed')).toHaveTextContent('false');
  });

  it('refuses a use past the limit, reports it, and does not creep the counter', async () => {
    const store = new MemoryUsageStore();
    for (let i = 0; i < LIMIT; i += 1) await store.increment(METERED!);
    setUsageStore(store);

    const user = userEvent.setup();
    await renderHarness(METERED!);
    expect(await screen.findByTestId('reason')).toHaveTextContent('quota_exhausted');

    await user.press(screen.getByTestId('use'));

    expect(sink.events.map((e) => e.name)).toContain('quota_exhausted');
    expect(await store.get(METERED!)).toBe(LIMIT);
  });
});

describeMetered('an entitled user', () => {
  beforeEach(() => setPurchaseProvider(new StubPurchaseProvider([ENTITLEMENT!])));

  it('is allowed no matter how much free allowance was already spent', async () => {
    const store = new MemoryUsageStore();
    for (let i = 0; i < LIMIT + 3; i += 1) await store.increment(METERED!);
    setUsageStore(store);

    await renderHarness(METERED!);

    expect(await screen.findByTestId('reason')).toHaveTextContent('entitled');
    expect(screen.getByTestId('allowed')).toHaveTextContent('true');
  });

  it('does not spend free-tier usage', async () => {
    const store = new MemoryUsageStore();
    setUsageStore(store);
    const user = userEvent.setup();
    await renderHarness(METERED!);
    await screen.findByTestId('reason');

    await user.press(screen.getByTestId('use'));

    expect(await store.get(METERED!)).toBe(0);
  });
});

(LOCKED ? describe : describe.skip)('a feature with no free allowance', () => {
  it('is locked outright until purchase', async () => {
    await renderHarness(LOCKED!);

    expect(await screen.findByTestId('reason')).toHaveTextContent('locked');
    expect(screen.getByTestId('allowed')).toHaveTextContent('false');
  });
});

describeMetered('purchasing', () => {
  it('unlocks the feature and reports the sale at the configured price', async () => {
    setPurchaseProvider(new StubPurchaseProvider([], ALL_ENTITLEMENTS));
    const user = userEvent.setup();
    await renderHarness(METERED!);
    expect(await screen.findByTestId('reason')).toHaveTextContent('free_quota');

    await user.press(screen.getByTestId('buy'));

    expect(screen.getByTestId('reason')).toHaveTextContent('entitled');
    expect(sink.events).toContainEqual({
      name: 'purchase',
      properties: { sku: PRICE.sku, price_usd: PRICE.price_usd },
    });
  });

  it('reports a failure instead of granting access when purchases are unavailable', async () => {
    const user = userEvent.setup();
    await renderHarness(METERED!);
    await screen.findByTestId('reason');

    await user.press(screen.getByTestId('buy'));

    expect(screen.getByTestId('reason')).toHaveTextContent('free_quota');
    expect(sink.events).toContainEqual({
      name: 'purchase_failed',
      properties: { sku: PRICE.sku, reason: 'purchases_not_configured' },
    });
  });
});

describe('the provider contract', () => {
  it('never grants an entitlement when no purchase backend is configured', async () => {
    const provider = new NoopPurchaseProvider();
    const outcome = await provider.purchase(PRICE.sku);

    expect(outcome.ok).toBe(false);
    expect(outcome.reason).toBe('purchases_not_configured');
    expect(outcome.entitlements.size).toBe(0);
    expect((await provider.activeEntitlements()).size).toBe(0);
  });

  it('fails loudly when the hook is used outside the provider', async () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    await expect(render(<Harness feature={METERED ?? 'anything'} />)).rejects.toThrow(
      /EntitlementsProvider/
    );
    spy.mockRestore();
  });
});
