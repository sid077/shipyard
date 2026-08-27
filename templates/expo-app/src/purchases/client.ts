import { Platform } from 'react-native';

/**
 * Entitlement state comes from the store, never from a local flag a user could
 * edit. This module is the only place that talks to RevenueCat, and it is
 * pluggable so tests and the simulator can run without a purchase backend.
 */

export type PurchaseOutcome = {
  ok: boolean;
  entitlements: Set<string>;
  reason?: string;
};

export type PurchaseProvider = {
  readonly configured: boolean;
  configure(): Promise<void>;
  activeEntitlements(): Promise<Set<string>>;
  purchase(sku: string): Promise<PurchaseOutcome>;
  restore(): Promise<Set<string>>;
};

/** Used when no purchase backend is configured: nothing is entitled, and a
 *  purchase attempt fails loudly rather than silently granting access. */
export class NoopPurchaseProvider implements PurchaseProvider {
  readonly configured = false;
  async configure(): Promise<void> {}
  async activeEntitlements(): Promise<Set<string>> {
    return new Set();
  }
  async purchase(_sku: string): Promise<PurchaseOutcome> {
    return { ok: false, entitlements: new Set(), reason: 'purchases_not_configured' };
  }
  async restore(): Promise<Set<string>> {
    return new Set();
  }
}

/** Grants a fixed set of entitlements. For tests and store review builds. */
export class StubPurchaseProvider implements PurchaseProvider {
  readonly configured = true;
  private granted: Set<string>;
  private readonly grantsOnPurchase: string[];

  constructor(granted: Iterable<string> = [], grantsOnPurchase: Iterable<string> = granted) {
    this.granted = new Set(granted);
    this.grantsOnPurchase = [...grantsOnPurchase];
  }

  async configure(): Promise<void> {}
  async activeEntitlements(): Promise<Set<string>> {
    return new Set(this.granted);
  }
  async purchase(_sku: string): Promise<PurchaseOutcome> {
    this.granted = new Set([...this.granted, ...this.grantsOnPurchase]);
    return { ok: true, entitlements: new Set(this.granted) };
  }
  async restore(): Promise<Set<string>> {
    return new Set(this.granted);
  }
}

function apiKey(): string | undefined {
  return Platform.OS === 'ios'
    ? process.env.EXPO_PUBLIC_REVENUECAT_IOS_KEY
    : process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_KEY;
}

export class RevenueCatProvider implements PurchaseProvider {
  readonly configured = true;
  private ready = false;

  async configure(): Promise<void> {
    if (this.ready) return;
    const key = apiKey();
    if (!key) throw new Error('RevenueCat key is missing for this platform');
    const Purchases = (await import('react-native-purchases')).default;
    await Purchases.configure({ apiKey: key });
    this.ready = true;
  }

  private async entitlementsFromCustomerInfo(): Promise<Set<string>> {
    const Purchases = (await import('react-native-purchases')).default;
    const info = await Purchases.getCustomerInfo();
    return new Set(Object.keys(info.entitlements.active));
  }

  async activeEntitlements(): Promise<Set<string>> {
    await this.configure();
    return this.entitlementsFromCustomerInfo();
  }

  async purchase(sku: string): Promise<PurchaseOutcome> {
    await this.configure();
    try {
      const Purchases = (await import('react-native-purchases')).default;
      const products = await Purchases.getProducts([sku]);
      const product = products.find((p) => p.identifier === sku);
      if (!product) {
        return { ok: false, entitlements: new Set(), reason: `unknown sku ${sku}` };
      }
      const { customerInfo } = await Purchases.purchaseStoreProduct(product);
      return { ok: true, entitlements: new Set(Object.keys(customerInfo.entitlements.active)) };
    } catch (error) {
      const reason =
        typeof error === 'object' && error !== null && 'userCancelled' in error
          ? 'cancelled'
          : String(error);
      return { ok: false, entitlements: await this.activeEntitlements(), reason };
    }
  }

  async restore(): Promise<Set<string>> {
    await this.configure();
    const Purchases = (await import('react-native-purchases')).default;
    const info = await Purchases.restorePurchases();
    return new Set(Object.keys(info.entitlements.active));
  }
}

let provider: PurchaseProvider = new NoopPurchaseProvider();

export function setPurchaseProvider(next: PurchaseProvider): void {
  provider = next;
}

export function getPurchaseProvider(): PurchaseProvider {
  return provider;
}

/**
 * Attach RevenueCat when a platform key is present. Returns whether purchases
 * are live, so the UI can show a clear "purchases unavailable" state instead of
 * a paywall that cannot complete.
 */
export async function initPurchases(): Promise<boolean> {
  if (!apiKey()) return false;
  const revenueCat = new RevenueCatProvider();
  try {
    await revenueCat.configure();
    setPurchaseProvider(revenueCat);
    return true;
  } catch {
    setPurchaseProvider(new NoopPurchaseProvider());
    return false;
  }
}
