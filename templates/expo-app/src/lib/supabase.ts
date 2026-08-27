import 'react-native-url-polyfill/auto';

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Session tokens live in the platform keychain, never in AsyncStorage. Only the
 * anon (publishable) key belongs in a client build; a service-role key in this
 * file would be a shipped credential leak.
 */

const secureStorage = {
  async getItem(key: string): Promise<string | null> {
    const SecureStore = await import('expo-secure-store');
    return SecureStore.getItemAsync(key);
  },
  async setItem(key: string, value: string): Promise<void> {
    const SecureStore = await import('expo-secure-store');
    await SecureStore.setItemAsync(key, value);
  },
  async removeItem(key: string): Promise<void> {
    const SecureStore = await import('expo-secure-store');
    await SecureStore.deleteItemAsync(key);
  },
};

let client: SupabaseClient | null = null;

/** The Supabase client, or null when the project is not configured. Callers
 *  must handle null: an offline-first app should work without a backend. */
export function getSupabase(): SupabaseClient | null {
  if (client) return client;
  const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) return null;
  client = createClient(url, anonKey, {
    auth: {
      storage: secureStorage,
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: false,
    },
  });
  return client;
}

export function isSupabaseConfigured(): boolean {
  return Boolean(process.env.EXPO_PUBLIC_SUPABASE_URL && process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY);
}

/** Test seam: drop the memoised client. */
export function resetSupabase(): void {
  client = null;
}
