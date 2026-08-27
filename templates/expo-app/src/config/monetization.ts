import raw from '../../monetization.json';

/**
 * The monetization plan is product configuration, not code. It is written by
 * the pipeline's monetization role and validated here at import time, so a
 * malformed plan fails the test run rather than shipping a broken paywall.
 */

export type BillingPeriod = 'month' | 'year' | 'lifetime' | 'consumable';
export type MonetizationModel = 'subscription' | 'one_time' | 'freemium_credits' | 'ad_supported';

export type PricePoint = {
  sku: string;
  display_name: string;
  price_usd: number;
  period: BillingPeriod;
};

export type MonetizationConfig = {
  model: MonetizationModel;
  rationale: string;
  price_points: PricePoint[];
  trial_days: number;
  /** entitlement id -> the feature keys it unlocks */
  entitlements: Record<string, string[]>;
  /** feature key -> free allowance before the paywall appears */
  free_tier_limits: Record<string, number>;
  paywall_trigger: string;
  paywall_placement: string[];
  projected_arpu_usd: number | null;
};

const MODELS: MonetizationModel[] = [
  'subscription',
  'one_time',
  'freemium_credits',
  'ad_supported',
];
const PERIODS: BillingPeriod[] = ['month', 'year', 'lifetime', 'consumable'];

class MonetizationConfigError extends Error {
  constructor(message: string) {
    super(`monetization.json is invalid: ${message}`);
    this.name = 'MonetizationConfigError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseMonetization(value: unknown): MonetizationConfig {
  if (!isRecord(value)) throw new MonetizationConfigError('expected an object');

  if (typeof value.model !== 'string' || !MODELS.includes(value.model as MonetizationModel)) {
    throw new MonetizationConfigError(`model must be one of ${MODELS.join(', ')}`);
  }
  const model = value.model as MonetizationModel;

  if (!Array.isArray(value.price_points) || value.price_points.length === 0) {
    throw new MonetizationConfigError('price_points must be a non-empty array');
  }
  const pricePoints = value.price_points.map((point, index): PricePoint => {
    if (!isRecord(point))
      throw new MonetizationConfigError(`price_points[${index}] is not an object`);
    const { sku, display_name, price_usd, period } = point;
    if (typeof sku !== 'string' || !sku) {
      throw new MonetizationConfigError(`price_points[${index}].sku must be a non-empty string`);
    }
    if (typeof display_name !== 'string' || !display_name) {
      throw new MonetizationConfigError(`price_points[${index}].display_name is required`);
    }
    if (typeof price_usd !== 'number' || Number.isNaN(price_usd) || price_usd < 0) {
      throw new MonetizationConfigError(`price_points[${index}].price_usd must be a number >= 0`);
    }
    if (typeof period !== 'string' || !PERIODS.includes(period as BillingPeriod)) {
      throw new MonetizationConfigError(
        `price_points[${index}].period must be one of ${PERIODS.join(', ')}`
      );
    }
    return { sku, display_name, price_usd, period: period as BillingPeriod };
  });

  if (!isRecord(value.entitlements) || Object.keys(value.entitlements).length === 0) {
    throw new MonetizationConfigError('entitlements must map at least one id to feature keys');
  }
  const entitlements: Record<string, string[]> = {};
  for (const [id, features] of Object.entries(value.entitlements)) {
    if (!Array.isArray(features) || features.some((f) => typeof f !== 'string')) {
      throw new MonetizationConfigError(`entitlements.${id} must be an array of feature keys`);
    }
    entitlements[id] = features as string[];
  }

  const known = new Set(Object.values(entitlements).flat());
  const freeTierLimits: Record<string, number> = {};
  if (value.free_tier_limits !== undefined) {
    if (!isRecord(value.free_tier_limits)) {
      throw new MonetizationConfigError('free_tier_limits must be an object');
    }
    for (const [feature, limit] of Object.entries(value.free_tier_limits)) {
      if (!known.has(feature)) {
        throw new MonetizationConfigError(
          `free_tier_limits.${feature} is not a feature key declared in entitlements`
        );
      }
      if (typeof limit !== 'number' || !Number.isInteger(limit) || limit < 0) {
        throw new MonetizationConfigError(
          `free_tier_limits.${feature} must be a non-negative integer`
        );
      }
      freeTierLimits[feature] = limit;
    }
  }

  const trialDays = value.trial_days ?? 0;
  if (typeof trialDays !== 'number' || !Number.isInteger(trialDays) || trialDays < 0) {
    throw new MonetizationConfigError('trial_days must be a non-negative integer');
  }

  if (typeof value.paywall_trigger !== 'string' || !value.paywall_trigger) {
    throw new MonetizationConfigError('paywall_trigger is required');
  }
  if (!Array.isArray(value.paywall_placement) || value.paywall_placement.length === 0) {
    throw new MonetizationConfigError('paywall_placement must list at least one screen');
  }

  return {
    model,
    rationale: typeof value.rationale === 'string' ? value.rationale : '',
    price_points: pricePoints,
    trial_days: trialDays,
    entitlements,
    free_tier_limits: freeTierLimits,
    paywall_trigger: value.paywall_trigger,
    paywall_placement: value.paywall_placement as string[],
    projected_arpu_usd:
      typeof value.projected_arpu_usd === 'number' ? value.projected_arpu_usd : null,
  };
}

export const monetization: MonetizationConfig = parseMonetization(raw);

/** Every feature key the app may gate on. */
export const FEATURE_KEYS: readonly string[] = Object.values(monetization.entitlements).flat();

/** The entitlement that unlocks a feature, or null if no entitlement grants it. */
export function entitlementFor(feature: string): string | null {
  for (const [id, features] of Object.entries(monetization.entitlements)) {
    if (features.includes(feature)) return id;
  }
  return null;
}

/** The free allowance for a feature, or null when it has none. */
export function freeLimitFor(feature: string): number | null {
  return Object.prototype.hasOwnProperty.call(monetization.free_tier_limits, feature)
    ? monetization.free_tier_limits[feature]
    : null;
}

/**
 * The first feature that has a free allowance, i.e. one that meters usage and
 * eventually shows the paywall. Null when nothing is metered.
 */
export function firstMeteredFeature(): string | null {
  return FEATURE_KEYS.find((key) => freeLimitFor(key) !== null) ?? null;
}

/** The first feature with no free allowance, i.e. locked until purchase. */
export function firstLockedFeature(): string | null {
  return FEATURE_KEYS.find((key) => freeLimitFor(key) === null) ?? null;
}

/** The price point to lead the paywall with: the best annual or lifetime value. */
export function headlinePrice(): PricePoint {
  const byPreference: BillingPeriod[] = ['lifetime', 'year', 'month', 'consumable'];
  for (const period of byPreference) {
    const match = monetization.price_points.find((p) => p.period === period);
    if (match) return match;
  }
  return monetization.price_points[0];
}
