import { Stack } from 'expo-router';
import Head from 'expo-router/head';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';

import { initAnalytics, track } from '@/analytics';
import { product } from '@/config/product';
import { initObservability, reportError } from '@/observability';
import { EntitlementsProvider } from '@/purchases/entitlements';
import { initPurchases } from '@/purchases/client';
import { useTheme } from '@/theme';

SplashScreen.preventAutoHideAsync().catch(() => {
  // Nothing to do: the splash screen is already hidden.
});

export default function RootLayout() {
  const theme = useTheme();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      initObservability();
      try {
        await Promise.all([initAnalytics(), initPurchases()]);
        track({ name: 'app_open' });
      } catch (error) {
        reportError(error, { where: 'RootLayout.bootstrap' });
      } finally {
        if (!cancelled) await SplashScreen.hideAsync().catch(() => {});
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <EntitlementsProvider>
      {/*
        The web export manages <head> with react-helmet, which empties whatever
        the HTML shell declared. Setting the default title through the router's
        own head API is what actually survives hydration - without it every
        route ships with no <title>, which is a serious a11y violation.
      */}
      <Head>
        <title>{product.name}</title>
        <meta name="description" content={product.tagline} />
      </Head>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.background },
          headerTintColor: theme.text,
          contentStyle: { backgroundColor: theme.background },
        }}
      >
        <Stack.Screen name="index" options={{ title: product.name }} />
        <Stack.Screen name="paywall" options={{ presentation: 'modal', title: 'Go Pro' }} />
      </Stack>
    </EntitlementsProvider>
  );
}
