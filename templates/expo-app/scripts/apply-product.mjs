#!/usr/bin/env node
/**
 * Project the pipeline's design and monetization artifacts into the app.
 *
 * This is deterministic code, not an agent task: the same artifacts must always
 * produce the same app configuration, and a typo here would be invisible in a
 * diff written by a model.
 *
 *   node scripts/apply-product.mjs --project ../../projects/tip-splitter
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function argValue(flag) {
  const index = process.argv.indexOf(flag);
  return index === -1 ? null : process.argv[index + 1];
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    throw new Error(`cannot read ${path}: ${error.message}`);
  }
}

function bundleIdFrom(slug) {
  const cleaned = slug.replace(/[^a-z0-9]+/g, '');
  return `com.shipyard.${cleaned || 'app'}`;
}

function main() {
  const projectDir = argValue('--project');
  if (!projectDir) {
    console.error('usage: apply-product.mjs --project <shipyard project dir>');
    process.exit(2);
  }
  const project = resolve(projectDir);

  const idea = readJson(join(project, 'idea.json'));
  const ui = readJson(join(project, 'design', 'ui.json'));
  const ux = readJson(join(project, 'design', 'ux.json'));
  const copy = readJson(join(project, 'design', 'copy.json'));
  const monetization = readJson(join(project, 'monetization.json'));

  const slug = idea.slug;
  const scheme = slug.replace(/-/g, '');
  const existing = (() => {
    try {
      return readJson(join(APP_ROOT, 'product.json'));
    } catch {
      return {};
    }
  })();

  // A different product starts its own version history; the same one keeps its.
  const sameProduct = existing.slug === slug;
  const product = {
    name: ui.app_name,
    slug,
    tagline: ui.tagline,
    scheme,
    version: sameProduct ? (existing.version ?? '1.0.0') : '1.0.0',
    // Build numbers only ever go up; the release stage bumps them.
    buildNumber: sameProduct ? (existing.buildNumber ?? 1) : 1,
    bundleId: bundleIdFrom(slug),
    packageName: bundleIdFrom(slug),
    primaryColor: ui.colors.primary,
    backgroundColor: ui.colors.background,
  };

  const camel = (name) => name.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
  const typeEntries = ui.type_scale
    .map(
      (step) =>
        `    ${camel(step.name)}: { size: ${step.size}, lineHeight: ${step.line_height}, ` +
        `weight: '${step.weight}', letterSpacing: ${step.letter_spacing ?? 0} },`
    )
    .join('\n');

  // Motion durations come from the transitions the UX spec actually declares,
  // so the design system moves at the speed the designer chose.
  const declared = (ux.transitions ?? []).map((t) => t.duration_ms).sort((a, b) => a - b);
  const medium = declared[0] ?? 240;
  const slow = declared.length ? declared[declared.length - 1] : 320;
  // `fast` is deliberately not one of the declared transitions: it is press and
  // toggle feedback, and a press that takes as long as a screen push feels
  // broken. Clamp it to the micro-interaction range instead.
  const fast = Math.min(Math.max(Math.round(medium / 2), 100), 180);

  const colorEntries = Object.entries(ui.colors)
    .map(([role, value]) => `    ${camel(role)}: '${value}',`)
    .join('\n');
  const radiiEntries = Object.entries(ui.radii)
    .map(([name, value]) => `${camel(name)}: ${value}`)
    .join(', ');

  const generated = `/**
 * GENERATED FILE - do not edit by hand.
 *
 * Written by \`scripts/apply-product.mjs\` from \`design/ui.json\` and
 * \`design/ux.json\`. Editing this file directly means the next pipeline run
 * overwrites your work.
 */

export const tokens = {
  colors: {
${colorEntries}
  },
  type: {
${typeEntries}
  },
  spacingUnit: ${ui.spacing_unit},
  radii: { ${radiiEntries} },
  elevation: [${ui.elevation.join(', ')}],
  minTouchTarget: ${ui.min_touch_target ?? 44},
  motion: {
    fast: ${fast},
    medium: ${medium},
    slow: ${slow},
  },
  mode: '${ui.mode ?? 'system'}',
} as const;

export type Tokens = typeof tokens;
export type TypeVariant = keyof typeof tokens.type;
`;

  // Maestro flows are generated too: the paywall flow asserts against the exact
  // free allowance in the plan, so a plan change cannot leave a stale E2E test.
  const meteredFeature =
    Object.keys(monetization.free_tier_limits ?? {})[0] ??
    Object.values(monetization.entitlements).flat()[0];
  const freeLimit = monetization.free_tier_limits?.[meteredFeature] ?? 0;

  const smokeFlow = `# The app launches and the home screen renders its quota state.
appId: ${product.bundleId}
---
- launchApp:
    clearState: true
- assertVisible:
    id: 'quota-label'
- assertVisible:
    id: 'add-item'
`;

  const paywallFlow = `# A free user hits the paywall at exactly the allowance in monetization.json
# (${freeLimit} use(s) of "${meteredFeature}"), and the paywall shows a real price.
appId: ${product.bundleId}
---
- launchApp:
    clearState: true
${
  freeLimit > 0
    ? `- repeat:
    times: ${freeLimit}
    commands:
      - tapOn:
          id: 'add-item'
- assertNotVisible:
    id: 'paywall'
`
    : ''
}- tapOn:
    id: 'add-item'
- assertVisible:
    id: 'paywall'
- assertVisible:
    id: 'paywall-price'
- tapOn:
    id: 'paywall-dismiss'
- assertNotVisible:
    id: 'paywall'
`;

  writeFileSync(join(APP_ROOT, 'maestro', 'smoke.yaml'), smokeFlow);
  writeFileSync(join(APP_ROOT, 'maestro', 'paywall.yaml'), paywallFlow);

  writeFileSync(join(APP_ROOT, 'product.json'), `${JSON.stringify(product, null, 2)}\n`);
  writeFileSync(join(APP_ROOT, 'monetization.json'), `${JSON.stringify(monetization, null, 2)}\n`);
  writeFileSync(join(APP_ROOT, 'src', 'theme', 'tokens.generated.ts'), generated);
  // The copy deck ships with the app: `t('key')` reads it at runtime, so a
  // wording change is a deck change rather than a code change.
  writeFileSync(join(APP_ROOT, 'copy.json'), `${JSON.stringify(copy, null, 2)}\n`);

  console.log(`applied ${product.name} (${slug}) from ${project}`);
  console.log(`  entitlements: ${Object.keys(monetization.entitlements).join(', ')}`);
  console.log(`  screens:      ${ux.screens.length}`);
  console.log(`  copy keys:    ${Object.keys(copy.entries ?? {}).length}`);
  console.log(`  components:   ${ui.components.length}`);
  console.log(`  paywall at:   ${freeLimit} use(s) of ${meteredFeature}`);
}

main();
