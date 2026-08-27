#!/usr/bin/env node
/**
 * Render the app, photograph it, and measure it.
 *
 * Exports the app to static web, serves it, drives it with Playwright at phone
 * viewports, and writes screenshots plus two machine-readable reports. This is
 * how the pipeline stops trusting that the UI is fine and starts checking.
 *
 *   node scripts/screenshots.mjs --out ../qa --routes /,/paywall,/__gallery
 *
 * Exit codes: 0 clean, 1 defects found, 2 the run itself failed.
 */

import { spawn } from 'node:child_process';
import { createReadStream, existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, resolve } from 'node:path';

const APP_ROOT = resolve(import.meta.dirname, '..');

const VIEWPORTS = [
  { name: 'iphone', width: 390, height: 844, scale: 3 },
  { name: 'android', width: 360, height: 800, scale: 3 },
];

const MIME = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.woff2': 'font/woff2',
};

function arg(flag, fallback = null) {
  const index = process.argv.indexOf(flag);
  return index === -1 ? fallback : process.argv[index + 1];
}

function run(command, args, cwd) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { cwd, stdio: 'inherit' });
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolvePromise() : reject(new Error(`${command} exited ${code}`))
    );
  });
}

/** A static server for the exported bundle. No dependency, no surprises. */
function serve(root) {
  const server = createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    let path = join(root, decodeURIComponent(url.pathname));
    if (!existsSync(path) || extname(path) === '') {
      // Expo's static export writes `paywall.html` for the `/paywall` route.
      const candidates = [`${path}.html`, join(path, 'index.html'), join(root, 'index.html')];
      path = candidates.find((c) => existsSync(c)) ?? candidates[candidates.length - 1];
    }
    if (!existsSync(path)) {
      res.writeHead(404).end('not found');
      return;
    }
    res.writeHead(200, { 'content-type': MIME[extname(path)] ?? 'application/octet-stream' });
    createReadStream(path).pipe(res);
  });
  return new Promise((resolvePromise) => {
    server.listen(0, '127.0.0.1', () => resolvePromise({ server, port: server.address().port }));
  });
}

/**
 * Probes that run inside the page. These are the defects a screenshot shows but
 * a human reviewer should not have to measure with a ruler.
 */
const PROBE = `() => {
  const findings = [];
  const MIN_TARGET = 44;
  const interactive = 'button,a,[role="button"],[role="tab"],[role="link"],input,select,textarea,[onclick]';

  const seen = new Set();
  for (const el of document.querySelectorAll(interactive)) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const label = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60);
    if (rect.width < MIN_TARGET || rect.height < MIN_TARGET) {
      const key = 'target:' + label + Math.round(rect.width) + 'x' + Math.round(rect.height);
      if (seen.has(key)) continue;
      seen.add(key);
      findings.push({
        kind: 'touch_target',
        label,
        detail: Math.round(rect.width) + 'x' + Math.round(rect.height) + 'px is below ' + MIN_TARGET + 'px',
      });
    }
  }

  for (const el of document.querySelectorAll('*')) {
    if (!el.childNodes.length) continue;
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) continue;
    const style = getComputedStyle(el);
    if (style.overflow === 'visible' && style.textOverflow !== 'ellipsis') continue;
    if (el.scrollWidth > el.clientWidth + 2 && style.textOverflow !== 'ellipsis') {
      findings.push({
        kind: 'clipped_text',
        label: el.textContent.trim().slice(0, 60),
        detail: 'content is ' + el.scrollWidth + 'px in a ' + el.clientWidth + 'px box',
      });
    }
  }

  if (document.documentElement.scrollWidth > window.innerWidth + 2) {
    findings.push({
      kind: 'horizontal_overflow',
      label: 'page',
      detail: 'page scrolls sideways: ' + document.documentElement.scrollWidth + 'px in ' + window.innerWidth + 'px',
    });
  }

  const tiny = [...document.querySelectorAll('*')].filter((el) => {
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    return hasText && parseFloat(getComputedStyle(el).fontSize) < 12;
  });
  for (const el of tiny.slice(0, 5)) {
    findings.push({
      kind: 'text_too_small',
      label: el.textContent.trim().slice(0, 60),
      detail: getComputedStyle(el).fontSize + ' is below the 12px floor',
    });
  }

  return findings;
}`;

/**
 * Launch Chromium, preferring whatever Playwright resolves by itself.
 *
 * A sandboxed CI image often has a pre-installed browser whose build number
 * does not match the pinned Playwright version. Downloading a second copy is
 * usually blocked and always wasteful, so fall back to whatever is already on
 * disk under PLAYWRIGHT_BROWSERS_PATH rather than failing the run.
 */
async function launchChromium(chromium) {
  try {
    return await chromium.launch();
  } catch (error) {
    const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
    if (!root || !existsSync(root)) throw error;

    const candidates = readdirSync(root)
      .filter((entry) => entry.startsWith('chromium'))
      .flatMap((entry) => [
        join(root, entry, 'chrome-linux', 'chrome'),
        join(root, entry, 'chrome-linux', 'headless_shell'),
        join(root, entry, 'chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
      ])
      .filter((path) => existsSync(path));

    if (!candidates.length) throw error;
    console.log(`playwright's own browser is missing; using ${candidates[0]}`);
    return chromium.launch({ executablePath: candidates[0] });
  }
}

async function main() {
  const outDir = resolve(arg('--out', join(APP_ROOT, '..', 'qa')));
  const routes = (arg('--routes', '/,/paywall,/__gallery') || '')
    .split(',')
    .map((r) => r.trim())
    .filter(Boolean);
  const screensDir = join(outDir, 'screens');
  mkdirSync(screensDir, { recursive: true });

  let baseUrl = arg('--base-url');
  let server = null;

  if (!baseUrl) {
    const distDir = join(APP_ROOT, 'dist-web');
    if (!existsSync(join(distDir, 'index.html'))) {
      await run(
        'npx',
        ['expo', 'export', '--platform', 'web', '--output-dir', 'dist-web'],
        APP_ROOT
      );
    }
    const started = await serve(distDir);
    server = started.server;
    baseUrl = `http://127.0.0.1:${started.port}`;
  }

  const { chromium } = await import('playwright');
  const { default: AxeBuilder } = await import('@axe-core/playwright');

  const browser = await launchChromium(chromium);
  const a11y = [];
  const layout = [];
  const captured = [];

  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        deviceScaleFactor: viewport.scale,
        isMobile: true,
        hasTouch: true,
      });
      const page = await context.newPage();

      for (const route of routes) {
        const name = (
          route === '/' ? 'home' : route.replace(/^\//, '').replace(/\//g, '-')
        ).replace(/^__/, '');
        const file = join(screensDir, `${name}.${viewport.name}.png`);
        await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle', timeout: 60_000 });
        // Let entry animations settle before photographing.
        await page.waitForTimeout(600);
        await page.screenshot({ path: file, fullPage: true });
        captured.push({ route, viewport: viewport.name, file });

        // Expo serves its own not-found page for a route the app does not
        // implement. Measuring that page tells us nothing about the product,
        // and reporting its small links as defects would send an engineer
        // chasing markup they do not own. The real defect is the missing screen.
        const unmatched = await page.evaluate(() => {
          const sitemap = document.querySelector('a[href="/_sitemap"], a[href$="/_sitemap"]');
          return Boolean(sitemap) || /unmatched route/i.test(document.body.innerText || '');
        });
        if (unmatched) {
          layout.push({
            route,
            viewport: viewport.name,
            kind: 'route_missing',
            label: route,
            detail: 'the app has no screen at this route; expo rendered its not-found page',
          });
          continue;
        }

        const findings = await page.evaluate(`(${PROBE})()`);
        for (const finding of findings) {
          layout.push({ route, viewport: viewport.name, ...finding });
        }

        // Accessibility is checked once per route; it does not vary by width.
        if (viewport.name === VIEWPORTS[0].name) {
          const results = await new AxeBuilder({ page })
            .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
            .analyze();
          for (const violation of results.violations) {
            a11y.push({
              route,
              id: violation.id,
              impact: violation.impact,
              help: violation.help,
              nodes: violation.nodes.slice(0, 3).map((n) => n.html.slice(0, 200)),
            });
          }
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
    server?.close();
  }

  writeFileSync(join(outDir, 'a11y.json'), `${JSON.stringify(a11y, null, 2)}\n`);
  writeFileSync(join(outDir, 'layout.json'), `${JSON.stringify(layout, null, 2)}\n`);
  writeFileSync(
    join(outDir, 'screens.json'),
    `${JSON.stringify({ routes, viewports: VIEWPORTS.map((v) => v.name), captured }, null, 2)}\n`
  );

  const serious = a11y.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  console.log(`captured ${captured.length} screenshots across ${routes.length} routes`);
  console.log(`accessibility violations: ${a11y.length} (${serious.length} serious or critical)`);
  console.log(`layout findings: ${layout.length}`);

  for (const v of serious.slice(0, 10)) console.log(`  a11y  ${v.route}  ${v.id}: ${v.help}`);
  for (const f of layout.slice(0, 15)) {
    console.log(`  ${f.kind}  ${f.route} (${f.viewport})  ${f.label || ''} - ${f.detail}`);
  }

  process.exit(serious.length > 0 || layout.length > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(`screenshot run failed: ${error.message}`);
  process.exit(2);
});
