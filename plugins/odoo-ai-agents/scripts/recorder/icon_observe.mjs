#!/usr/bin/env node
/**
 * Icon observer: signs in like the recorder, opens the apps screens and measures how the client
 * draws module icons.
 *
 * Usage: node icon_observe.mjs --base-url URL --ui-user USER --module NAME --out-dir DIR
 *
 * Every result is a KEY=VALUE line on stdout: BOX_PX, THEME_TILE, TILE_BOX_PX, TILE_BG,
 * TILE_RADIUS, TILE_PADDING, ICON_COUNT, ICON_OVERRIDE, SCREENSHOT, UNKNOWN. Exit codes: 0 a
 * measurement was made, 4 nothing could be measured or the arguments are unusable.
 *
 * The icons are found by their pixels and text, never by a class name: square images whose
 * source, alt text or surroundings point at a module. The `playwright` library is resolved
 * through NODE_PATH, never from a relative node_modules.
 */
import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
const TIMEOUT_MS = 60000;
const SETTLE_MS = 2000;
// Screens that list apps, tried in order: the client's root, then the apps list of newer and older clients.
const SCREENS = ['/', '/odoo/apps', '/web#action=base.open_module_tree'];

function parseArgs(argv) {
  const out = { baseUrl: null, user: null, module: null, outDir: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--base-url') out.baseUrl = argv[++i];
    else if (argv[i] === '--ui-user') out.user = argv[++i];
    else if (argv[i] === '--module') out.module = argv[++i];
    else if (argv[i] === '--out-dir') out.outDir = argv[++i];
  }
  return out;
}

/** Runs in the page: every square module-looking image with its box and its nearest backing box. */
function collectIcons(moduleName) {
  const needle = moduleName.toLowerCase();
  const loose = needle.replace(/_/g, ' ');
  const transparent = (c) => !c || c === 'transparent' || /rgba\(\s*\d+,\s*\d+,\s*\d+,\s*0\s*\)/.test(c);
  const rows = [];
  for (const img of document.querySelectorAll('img')) {
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    if (!img.complete || nw < 8 || Math.abs(nw - nh) > 1) continue;
    const r = img.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) continue;
    const src = img.currentSrc || img.src || '';
    const alt = img.alt || '';
    let near = '';
    let el = img.parentElement;
    for (let depth = 0; el && depth < 2; depth++, el = el.parentElement) {
      near += ' ' + (el.innerText || '').slice(0, 120) + ' ' + Array.from(el.attributes).map((a) => a.value).join(' ');
    }
    const own = ((src.startsWith('data:') ? '' : src) + ' ' + alt).toLowerCase();
    const around = near.toLowerCase();
    const looksModule = /\/static\//.test(src) || src.startsWith('data:image') || /\/web\/image/.test(src) || alt.trim() !== '' || near.trim() !== '';
    if (!looksModule) continue;
    const cs = getComputedStyle(img);
    let tile = null;
    el = img.parentElement;
    for (let depth = 0; el && depth < 3; depth++, el = el.parentElement) {
      const ecs = getComputedStyle(el);
      const er = el.getBoundingClientRect();
      if (!transparent(ecs.backgroundColor) && er.width <= r.width * 2 + 4 && er.height <= r.height * 2 + 4) {
        tile = { w: er.width, h: er.height, bg: ecs.backgroundColor, radius: ecs.borderRadius, padding: ecs.padding };
        break;
      }
    }
    if (!tile && !transparent(cs.backgroundColor)) {
      tile = { w: r.width, h: r.height, bg: cs.backgroundColor, radius: cs.borderRadius, padding: cs.padding };
    }
    const has = (hay) => hay.includes(needle) || hay.includes(loose);
    rows.push({ src, w: r.width, h: r.height, strong: has(own), weak: has(around), tile });
  }
  return rows;
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor(s.length / 2)] : 0;
};
const px = (n) => String(Math.round(n * 10) / 10).replace(/\.0$/, '');

async function bytesOf(ctx, base, src) {
  if (src.startsWith('data:')) {
    const comma = src.indexOf(',');
    if (comma < 0) return null;
    return /;base64/.test(src.slice(0, comma)) ? Buffer.from(src.slice(comma + 1), 'base64') : Buffer.from(decodeURIComponent(src.slice(comma + 1)));
  }
  const res = await ctx.request.get(new URL(src, base).toString());
  return res.ok() ? Buffer.from(await res.body()) : null;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.baseUrl || !args.user || !args.module || !args.outDir) {
    console.log('ERROR=--base-url, --ui-user, --module and --out-dir are required');
    return 4;
  }
  let chromium;
  try {
    ({ chromium } = require('playwright'));
  } catch {
    console.log('ERROR=the recorder library is not installed');
    return 4;
  }
  fs.mkdirSync(args.outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    page.setDefaultTimeout(TIMEOUT_MS);
    await page.goto(new URL('/web/login', args.baseUrl).toString(), { waitUntil: 'load' });
    // Odoo's demo accounts use their own name as their key, on every series (as the recorder does).
    await page.locator('input[name=login]').fill(args.user);
    await page.locator('input[name=password]').fill(args.user);
    await page.locator('form button[type=submit]').first().click();
    try {
      await page.waitForURL((u) => !u.pathname.startsWith('/web/login'), { timeout: TIMEOUT_MS });
    } catch {
      console.log('UNKNOWN=sign-in did not leave the login page');
      return 4;
    }
    let rows = [];
    let shot = null;
    for (const screen of SCREENS) {
      await page.goto(new URL(screen, args.baseUrl).toString(), { waitUntil: 'load' });
      await page.waitForTimeout(SETTLE_MS);
      rows = await page.evaluate(collectIcons, args.module);
      if (rows.length) {
        shot = path.join(args.outDir, 'icon-observe.png');
        await page.screenshot({ path: shot, fullPage: true });
        break;
      }
    }
    if (!rows.length) {
      console.log('UNKNOWN=no square module icon was found on the apps screens');
      return 4;
    }
    const mine = rows.find((r) => r.strong) || rows.find((r) => r.weak) || null;
    const ref = mine || { w: median(rows.map((r) => r.w)), h: median(rows.map((r) => r.h)), tile: null };
    console.log(`ICON_COUNT=${rows.length}`);
    console.log(`BOX_PX=${px(ref.w)}x${px(ref.h)}`);
    const themed = mine ? !!mine.tile : rows.filter((r) => r.tile).length * 2 > rows.length;
    console.log(`THEME_TILE=${themed ? 'yes' : 'no'}`);
    const tile = mine ? mine.tile : (rows.find((r) => r.tile) || {}).tile;
    if (themed && tile) {
      console.log(`TILE_BOX_PX=${px(tile.w)}x${px(tile.h)}`);
      console.log(`TILE_BG=${tile.bg}`);
      console.log(`TILE_RADIUS=${tile.radius}`);
      console.log(`TILE_PADDING=${tile.padding}`);
    }
    if (mine) {
      try {
        const shown = await bytesOf(ctx, args.baseUrl, mine.src);
        const own = await bytesOf(ctx, args.baseUrl, `/${args.module}/static/description/icon.png`);
        if (shown && own) {
          const same = crypto.createHash('sha256').update(shown).digest('hex') === crypto.createHash('sha256').update(own).digest('hex');
          console.log(`ICON_OVERRIDE=${same ? 'no' : 'yes'}`);
        } else {
          console.log('UNKNOWN=the module icon bytes could not be fetched for comparison');
        }
      } catch {
        console.log('UNKNOWN=the module icon bytes could not be fetched for comparison');
      }
    } else {
      console.log('UNKNOWN=the icon of the module was not among the icons shown');
    }
    console.log(`SCREENSHOT=${shot}`);
    return 0;
  } finally {
    await browser.close();
  }
}

main().then((code) => process.exit(code), (err) => {
  console.log(`ERROR=${String(err && err.message ? err.message : err).split('\n')[0]}`);
  process.exit(4);
});
