import type { ConfigContext, ExpoConfig } from 'expo/config';

import product from './product.json';

/**
 * Everything product-specific comes from `product.json`, which the pipeline
 * generates from the design spec. Editing this file by hand for a single
 * product is a smell - regenerate `product.json` instead.
 */
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: product.name,
  slug: product.slug,
  scheme: product.scheme,
  version: product.version,
  orientation: 'portrait',
  userInterfaceStyle: 'automatic',
  icon: './assets/images/icon.png',
  ios: {
    supportsTablet: true,
    bundleIdentifier: product.bundleId,
    buildNumber: String(product.buildNumber),
  },
  android: {
    package: product.packageName,
    versionCode: product.buildNumber,
    adaptiveIcon: {
      backgroundColor: product.backgroundColor,
      foregroundImage: './assets/images/android-icon-foreground.png',
      monochromeImage: './assets/images/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  web: {
    output: 'static',
    favicon: './assets/images/favicon.png',
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
    [
      'expo-splash-screen',
      {
        backgroundColor: product.backgroundColor,
        image: './assets/images/splash-icon.png',
        imageWidth: 160,
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
});
