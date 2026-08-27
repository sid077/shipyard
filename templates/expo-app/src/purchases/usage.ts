/**
 * Free-tier counters. `free_tier_limits` in monetization.json says how much of a
 * feature a free user gets; this is where that allowance is spent.
 *
 * These counters decide when the paywall *appears*. They never decide what a
 * paying user may do - that is always read from the store.
 */

export type UsageStore = {
  get(feature: string): Promise<number>;
  increment(feature: string): Promise<number>;
  reset(feature?: string): Promise<void>;
};

export class MemoryUsageStore implements UsageStore {
  private counts = new Map<string, number>();
  async get(feature: string): Promise<number> {
    return this.counts.get(feature) ?? 0;
  }
  async increment(feature: string): Promise<number> {
    const next = (this.counts.get(feature) ?? 0) + 1;
    this.counts.set(feature, next);
    return next;
  }
  async reset(feature?: string): Promise<void> {
    if (feature) this.counts.delete(feature);
    else this.counts.clear();
  }
}

const KEY_PREFIX = 'usage:';

/** Persists counters across launches, falling back to memory if storage is
 *  unavailable rather than crashing the feature it gates. */
export class AsyncStorageUsageStore implements UsageStore {
  private fallback = new MemoryUsageStore();

  private async storage() {
    try {
      return (await import('@react-native-async-storage/async-storage')).default;
    } catch {
      return null;
    }
  }

  async get(feature: string): Promise<number> {
    const storage = await this.storage();
    if (!storage) return this.fallback.get(feature);
    const raw = await storage.getItem(KEY_PREFIX + feature);
    const parsed = Number.parseInt(raw ?? '0', 10);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  async increment(feature: string): Promise<number> {
    const storage = await this.storage();
    if (!storage) return this.fallback.increment(feature);
    const next = (await this.get(feature)) + 1;
    await storage.setItem(KEY_PREFIX + feature, String(next));
    return next;
  }

  async reset(feature?: string): Promise<void> {
    const storage = await this.storage();
    if (!storage) return this.fallback.reset(feature);
    if (feature) {
      await storage.removeItem(KEY_PREFIX + feature);
      return;
    }
    const keys = await storage.getAllKeys();
    for (const key of keys.filter((k: string) => k.startsWith(KEY_PREFIX))) {
      await storage.removeItem(key);
    }
  }
}

let store: UsageStore = new AsyncStorageUsageStore();

export function setUsageStore(next: UsageStore): void {
  store = next;
}

export function getUsageStore(): UsageStore {
  return store;
}
