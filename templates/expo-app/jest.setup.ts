/**
 * Native modules are stubbed here so unit tests exercise our own logic rather
 * than a simulator. Anything that talks to a store, a keychain or the network
 * is mocked; everything else runs for real.
 */

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn() },
  Stack: Object.assign(({ children }: { children?: unknown }) => children ?? null, {
    Screen: () => null,
  }),
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
}));

jest.mock('expo-splash-screen', () => ({
  preventAutoHideAsync: jest.fn().mockResolvedValue(undefined),
  hideAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('@react-native-async-storage/async-storage', () => {
  const store = new Map<string, string>();
  return {
    __esModule: true,
    default: {
      getItem: jest.fn(async (k: string) => store.get(k) ?? null),
      setItem: jest.fn(async (k: string, v: string) => void store.set(k, v)),
      removeItem: jest.fn(async (k: string) => void store.delete(k)),
      getAllKeys: jest.fn(async () => [...store.keys()]),
      multiRemove: jest.fn(async (keys: string[]) => keys.forEach((k) => store.delete(k))),
    },
  };
});

jest.mock('react-native-purchases', () => ({
  __esModule: true,
  default: {
    configure: jest.fn().mockResolvedValue(undefined),
    getCustomerInfo: jest.fn().mockResolvedValue({ entitlements: { active: {} } }),
    getProducts: jest.fn().mockResolvedValue([]),
    purchaseStoreProduct: jest.fn(),
    restorePurchases: jest.fn().mockResolvedValue({ entitlements: { active: {} } }),
  },
}));
