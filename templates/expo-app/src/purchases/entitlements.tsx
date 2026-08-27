import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { track } from '@/analytics';
import { entitlementFor, freeLimitFor, monetization } from '@/config/monetization';

import { getPurchaseProvider } from './client';
import { getUsageStore } from './usage';

/**
 * The single way the app asks "may this user do this?".
 *
 * Never gate a paid feature on a boolean, a debug flag, or a local preference.
 * Gate it on `useEntitlement(<feature key from monetization.json>)`.
 */

export type EntitlementReason =
  'loading' | 'entitled' | 'free_quota' | 'quota_exhausted' | 'locked';

export type EntitlementState = {
  /** Whether the user may use the feature right now. */
  allowed: boolean;
  reason: EntitlementReason;
  /** Uses left under the free allowance, or null when the feature has none. */
  remaining: number | null;
  limit: number | null;
  /** The entitlement id that would unlock this feature, if any. */
  entitlement: string | null;
  /** Spend one unit of the free allowance. Returns whether the use was allowed. */
  recordUse: () => Promise<boolean>;
};

type EntitlementsContextValue = {
  entitlements: Set<string>;
  usage: Record<string, number>;
  ready: boolean;
  purchasesAvailable: boolean;
  refresh: () => Promise<void>;
  purchase: (sku: string) => Promise<boolean>;
  restore: () => Promise<void>;
  noteUse: (feature: string) => Promise<number>;
};

const EntitlementsContext = createContext<EntitlementsContextValue | null>(null);

export function EntitlementsProvider({ children }: { children: React.ReactNode }) {
  const [entitlements, setEntitlements] = useState<Set<string>>(new Set());
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [ready, setReady] = useState(false);

  const provider = getPurchaseProvider();

  const loadUsage = useCallback(async () => {
    const store = getUsageStore();
    const features = Object.keys(monetization.free_tier_limits);
    const entries = await Promise.all(
      features.map(async (feature) => [feature, await store.get(feature)] as const)
    );
    setUsage(Object.fromEntries(entries));
  }, []);

  const refresh = useCallback(async () => {
    const [active] = await Promise.all([getPurchaseProvider().activeEntitlements(), loadUsage()]);
    setEntitlements(active);
  }, [loadUsage]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const purchase = useCallback(async (sku: string) => {
    const point = monetization.price_points.find((p) => p.sku === sku);
    const outcome = await getPurchaseProvider().purchase(sku);
    if (outcome.ok) {
      setEntitlements(outcome.entitlements);
      track({ name: 'purchase', properties: { sku, price_usd: point?.price_usd ?? 0 } });
    } else {
      track({
        name: 'purchase_failed',
        properties: { sku, reason: outcome.reason ?? 'unknown' },
      });
    }
    return outcome.ok;
  }, []);

  const restore = useCallback(async () => {
    setEntitlements(await getPurchaseProvider().restore());
  }, []);

  const noteUse = useCallback(async (feature: string) => {
    const next = await getUsageStore().increment(feature);
    setUsage((current) => ({ ...current, [feature]: next }));
    return next;
  }, []);

  const value = useMemo<EntitlementsContextValue>(
    () => ({
      entitlements,
      usage,
      ready,
      purchasesAvailable: provider.configured,
      refresh,
      purchase,
      restore,
      noteUse,
    }),
    [entitlements, usage, ready, provider.configured, refresh, purchase, restore, noteUse]
  );

  return <EntitlementsContext.Provider value={value}>{children}</EntitlementsContext.Provider>;
}

export function useEntitlements(): EntitlementsContextValue {
  const value = useContext(EntitlementsContext);
  if (!value) {
    throw new Error('useEntitlements must be used inside an <EntitlementsProvider>');
  }
  return value;
}

export function useEntitlement(feature: string): EntitlementState {
  const { entitlements, usage, ready, noteUse } = useEntitlements();
  const entitlement = entitlementFor(feature);
  const limit = freeLimitFor(feature);
  const used = usage[feature] ?? 0;

  const holdsEntitlement = entitlement !== null && entitlements.has(entitlement);
  const remaining = limit === null ? null : Math.max(limit - used, 0);

  let reason: EntitlementReason;
  if (!ready) reason = 'loading';
  else if (holdsEntitlement) reason = 'entitled';
  else if (limit === null) reason = 'locked';
  else if ((remaining ?? 0) > 0) reason = 'free_quota';
  else reason = 'quota_exhausted';

  const allowed = reason === 'entitled' || reason === 'free_quota';

  const recordUse = useCallback(async () => {
    if (holdsEntitlement) return true;
    if (limit === null) return false;
    if (used >= limit) {
      track({ name: 'quota_exhausted', properties: { feature, limit } });
      return false;
    }
    await noteUse(feature);
    return true;
  }, [holdsEntitlement, limit, used, feature, noteUse]);

  return { allowed, reason, remaining, limit, entitlement, recordUse };
}
