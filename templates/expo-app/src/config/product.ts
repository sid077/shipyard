import raw from '../../product.json';

export type ProductConfig = {
  name: string;
  slug: string;
  tagline: string;
  scheme: string;
  version: string;
  buildNumber: number;
  bundleId: string;
  packageName: string;
  primaryColor: string;
  backgroundColor: string;
};

export const product: ProductConfig = raw;
