import shipped from '../monetization.json';
import {
  entitlementFor,
  freeLimitFor,
  headlinePrice,
  parseMonetization,
} from '@/config/monetization';

describe('the shipped monetization plan', () => {
  it('validates, so a malformed plan fails here rather than in the store', () => {
    expect(() => parseMonetization(shipped)).not.toThrow();
  });

  it('exposes the entitlement that unlocks each feature', () => {
    const config = parseMonetization(shipped);
    for (const [id, features] of Object.entries(config.entitlements)) {
      for (const feature of features) {
        expect(entitlementFor(feature)).toBe(id);
      }
    }
    expect(entitlementFor('a_feature_nobody_declared')).toBeNull();
  });

  it('reports a free allowance only for features that have one', () => {
    const config = parseMonetization(shipped);
    for (const [feature, limit] of Object.entries(config.free_tier_limits)) {
      expect(freeLimitFor(feature)).toBe(limit);
    }
    expect(freeLimitFor('a_feature_nobody_declared')).toBeNull();
  });

  it('leads the paywall with the best-value price point available', () => {
    const config = parseMonetization(shipped);
    const preference = ['lifetime', 'year', 'month', 'consumable'];
    const best = config.price_points
      .slice()
      .sort((a, b) => preference.indexOf(a.period) - preference.indexOf(b.period))[0];
    expect(headlinePrice().sku).toBe(best.sku);
  });
});

describe('parseMonetization rejects plans that would ship a broken paywall', () => {
  const base = () => JSON.parse(JSON.stringify(shipped));

  it('rejects an unknown model', () => {
    expect(() => parseMonetization({ ...base(), model: 'donations' })).toThrow(/model must be/);
  });

  it('rejects an empty price list', () => {
    expect(() => parseMonetization({ ...base(), price_points: [] })).toThrow(/non-empty/);
  });

  it('rejects a negative price', () => {
    const config = base();
    config.price_points[0].price_usd = -1;
    expect(() => parseMonetization(config)).toThrow(/price_usd/);
  });

  it('rejects a free limit on a feature no entitlement grants', () => {
    const config = base();
    config.free_tier_limits = { nonexistent_feature: 3 };
    expect(() => parseMonetization(config)).toThrow(/not a feature key/);
  });

  it('rejects a plan with no entitlements at all', () => {
    expect(() => parseMonetization({ ...base(), entitlements: {} })).toThrow(/entitlements/);
  });

  it('rejects a missing paywall trigger', () => {
    const config = base();
    delete config.paywall_trigger;
    expect(() => parseMonetization(config)).toThrow(/paywall_trigger/);
  });
});
