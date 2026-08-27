# Shipyard Expo template

The golden app the org clones. It is committed **green**: a fresh clone plus
`npm ci` passes `scripts/verify.sh` with no product applied. Nothing downstream
in the pipeline can work if this is red, so the template has its own tests.

Generated apps start here and are modified. They are never scaffolded from
scratch, which is what keeps an unattended build loop from re-deciding the stack
on every product.

## What is already wired

| Concern      | How                                                                             |
| ------------ | ------------------------------------------------------------------------------- |
| Navigation   | `expo-router`, file-based, under `src/app`                                      |
| Styling      | Design tokens in `src/theme`, derived light and dark palettes, contrast helpers |
| Purchases    | RevenueCat behind `src/purchases/client.ts`, pluggable and no-op without keys   |
| Entitlements | `useEntitlement(featureKey)` — the only sanctioned way to gate a paid feature   |
| Free tiers   | `src/purchases/usage.ts` counters, driven by `free_tier_limits`                 |
| Analytics    | Closed event union in `src/analytics` — an invented event name fails typecheck  |
| Errors       | `src/observability` behind one seam                                             |
| Backend      | Supabase in `src/lib/supabase.ts`, session tokens in the keychain, optional     |
| Tests        | Jest + React Native Testing Library, Maestro flows in `maestro/`                |
| Builds       | `eas.json` with development, preview and production profiles                    |

## Product configuration

Three files are generated, never hand-edited:

- `product.json` — name, slug, bundle ids, version, colours
- `monetization.json` — the plan, copied verbatim from the pipeline artifact
- `src/theme/tokens.generated.ts` — the design tokens

`scripts/apply-product.mjs --project <shipyard project dir>` writes all three
plus the Maestro flows, so the E2E paywall test always asserts against the
allowance the plan actually specifies.

## Gating a paid feature

```tsx
const { allowed, remaining, recordUse } = useEntitlement('export_pdf');

async function onExport() {
  if (!(await recordUse())) {
    router.push('/paywall'); // free allowance spent, or feature locked
    return;
  }
  await doTheExport();
}
```

Never gate on a boolean, a debug flag, or a stored preference. Entitlement state
comes from the store; the local counters only decide when the paywall _appears_.

## Running it

```bash
npm ci
npm run verify        # typecheck, lint, format, unit tests
npm start             # Expo dev server
```

Every integration is optional. With no keys in `.env`, purchases run in no-op
mode, analytics collect in memory, and Supabase returns null — so the app still
builds, boots, and tests green on a machine with no accounts anywhere.
