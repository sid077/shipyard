import { ScrollViewStyleReset } from 'expo-router/html';
import type { PropsWithChildren } from 'react';

import { product } from '@/config/product';

/**
 * The HTML shell for the static web export.
 *
 * It exists mainly so every page has a `<title>`: without one, screen-reader
 * users cannot tell pages apart, and the design-QA stage reports it as a
 * serious accessibility violation on every route.
 */
export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"
        />
        <title>{product.name}</title>
        <meta name="description" content={product.tagline} />
        <ScrollViewStyleReset />
      </head>
      <body>{children}</body>
    </html>
  );
}
