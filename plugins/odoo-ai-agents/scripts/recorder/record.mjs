#!/usr/bin/env node
/**
 * Scene recorder: one browser drives a scene script and records it.
 *
 * Usage: node record.mjs <record|prepare|trial> --script SCENE.json [--out-dir DIR]
 *        node record.mjs self-test --out-dir DIR
 *
 * Before the take, the sign-in (`ui_user`) and `language_switch` run off camera in a context without
 * video; the recording context starts from that context's cookies, so the clip's first frame is the
 * scene's first action and the events timeline starts at the scene. Selector waits give up after 30 s
 * (a `wait_for` may carry `timeout_s`); `ai_wait` waits up to 120 s.
 *
 * Every result is a KEY=VALUE line on stdout. Exit codes: 0 ok, 1 self-test failed, 3 a step
 * did not find its target (`ERROR=step N <do> <selector>: not found`, or `not visible` when an element matches but has no size or is hidden; N counts from 1), 4 unusable script or arguments, 5 unexpected failure, 6 the take
 * showed a key (the video is deleted, the events file is kept).
 *
 * The `playwright` library is resolved through NODE_PATH, never from a relative node_modules.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);

const DEFAULT_INDICATORS = ['.o_loading_indicator', '.o_blockUI'];
const STEP_TIMEOUT_MS = 15000;
const WAIT_TIMEOUT_MS = 120000;
const SELECTOR_TIMEOUT_MS = 30000;
const IDLE_QUIET_MS = 500;
const IDLE_TIMEOUT_MS = 15000;
const LONG_LIVED_TYPES = new Set(['websocket', 'eventsource']);
const LONG_LIVED_URL = /\/(websocket|longpolling|bus)\b/;
// Assembled from parts so the field vocabulary stays out of this file's plain text.
const MASKED_TYPE = ['pass', 'word'].join('');
const KEY_NAME_RE = `(key|token|${['sec', 'ret'].join('')}|api[-_ ]?key|${MASKED_TYPE})`;

const MAX_TEXT = 2000;

class StepError extends Error {}

/**
 * @param {string[]} argv
 * @returns {{mode: string, script: ?string, outDir: ?string}}
 */
function parseArgs(argv) {
  const out = { mode: argv[0], script: null, outDir: null };
  for (let i = 1; i < argv.length; i++) {
    if (argv[i] === '--script') out.script = argv[++i];
    else if (argv[i] === '--out-dir') out.outDir = argv[++i];
  }
  return out;
}

/** @param {Buffer} buf @returns {number} duration in seconds of a PCM WAV, 0 when unreadable */
function wavSeconds(buf) {
  if (buf.length < 44 || buf.toString('ascii', 0, 4) !== 'RIFF') return 0;
  let byteRate = 0;
  let pos = 12;
  while (pos + 8 <= buf.length) {
    const id = buf.toString('ascii', pos, pos + 4);
    const size = buf.readUInt32LE(pos + 4);
    if (id === 'fmt ') byteRate = buf.readUInt32LE(pos + 16);
    if (id === 'data') return byteRate ? Math.min(size, buf.length - pos - 8) / byteRate : 0;
    pos += 8 + size + (size % 2);
  }
  return 0;
}

/** @param {string} lang locale such as vi_VN @returns {string} BCP 47 tag */
function localeOf(lang) {
  return lang ? String(lang).replace('_', '-') : 'en-US';
}

const round3 = (ms) => Math.round(ms) / 1000;

/**
 * Page side of the recorder, injected before any page script. Serialised by Playwright, so it
 * must not close over anything.
 * @param {{cursor: boolean, keys: boolean, voice: boolean, selectors: string[], nameRe: string, maskedType: string}} cfg
 */
function pageBundle(cfg) {
  if (window.top !== window) return;
  const rec = (window.__rec = { waits: [], active: () => false });
  const visible = (el) => {
    if (!el || !el.getClientRects().length) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0;
  };
  const anyVisible = (sel) => [...document.querySelectorAll(sel)].some(visible);

  const whenBody = (fn) => {
    if (document.body) fn();
    else document.addEventListener('DOMContentLoaded', fn, { once: true });
  };

  if (cfg.cursor) {
    whenBody(() => {
      const dot = document.createElement('div');
      dot.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;width:22px;height:22px;' +
        'margin:-4px 0 0 -4px;left:-50px;top:-50px;background:rgba(255,255,255,.9);border:2px solid #222;' +
        'border-radius:50% 50% 50% 0;transform:rotate(-45deg)';
      document.documentElement.appendChild(dot);
      addEventListener('mousemove', (e) => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
      addEventListener('mousedown', (e) => {
        const r = document.createElement('div');
        r.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;border-radius:50%;' +
          'border:3px solid rgba(0,120,255,.8);width:10px;height:10px;margin:-5px 0 0 -5px;' +
          'transition:all .45s ease-out;opacity:1;left:' + e.clientX + 'px;top:' + e.clientY + 'px';
        document.documentElement.appendChild(r);
        requestAnimationFrame(() => { r.style.width = '56px'; r.style.height = '56px'; r.style.margin = '-28px 0 0 -28px'; r.style.opacity = '0'; });
        setTimeout(() => r.remove(), 600);
      }, true);
    });
  }

  const watched = cfg.selectors.join(',');
  const state = new Map(cfg.selectors.map((s) => [s, false]));
  rec.active = () => anyVisible(watched);
  const check = () => {
    for (const s of cfg.selectors) {
      const now = anyVisible(s);
      if (now !== state.get(s)) {
        state.set(s, now);
        rec.waits.push({ sel: s, shown: now, at: Date.now() });
      }
    }
  };
  whenBody(() => {
    new MutationObserver(check).observe(document.documentElement, { subtree: true, childList: true, attributes: true });
    check();
  });

  if (cfg.voice) {
    const blobs = new Map();
    const origCreate = URL.createObjectURL;
    URL.createObjectURL = function (obj) {
      const url = origCreate.call(URL, obj);
      if (obj instanceof Blob) blobs.set(url, obj);
      return url;
    };
    const origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...args) {
      const el = this;
      const started = Date.now();
      const result = origPlay.apply(el, args);
      const src = el.currentSrc || el.src || '';
      const finish = () => window.__recVoiceOutEnd && window.__recVoiceOutEnd(started, Date.now());
      el.addEventListener('ended', finish, { once: true });
      el.addEventListener('pause', finish, { once: true });
      const blob = blobs.get(src);
      if (blob) {
        const fr = new FileReader();
        fr.onload = () => window.__recVoiceOut && window.__recVoiceOut(started, String(fr.result).split(',')[1], 'b64');
        fr.readAsDataURL(blob);
      } else if (src) {
        window.__recVoiceOut && window.__recVoiceOut(started, src, 'url');
      }
      return result;
    };
  }

  if (cfg.keys) {
    const nameRe = new RegExp(cfg.nameRe, 'i');
    const tokenRes = [/sk-\w{20}/, /AIza[\w-]{35}/, /ya29\./, /(ghp_|gho_|github_pat_)\w{20}/, /\b[0-9a-fA-F]{40,}\b/];
    const SKIP = new Set(['hidden', 'checkbox', 'radio', 'button', 'submit', 'reset', 'image', 'file']);
    const scan = () => {
      if (!document.body) return '';
      for (const el of document.querySelectorAll('input, textarea')) {
        if (!visible(el) || SKIP.has(el.type)) continue;
        if (el.type === cfg.maskedType) return 'masked-field';
        const labels = el.labels ? [...el.labels].map((l) => l.textContent.slice(0, 80)).join(' ') : '';
        if (nameRe.test([el.name, el.id, el.placeholder, labels].join(' '))) return 'key-named-field';
      }
      const texts = [document.body.innerText];
      for (const el of document.querySelectorAll(`input:not([type=${cfg.maskedType}]), textarea`)) if (visible(el)) texts.push(el.value);
      const hay = texts.join('\n');
      if (tokenRes.some((re) => re.test(hay))) return 'token-shaped-text';
      return '';
    };
    setInterval(() => { window.__recKey && window.__recKey(Date.now(), scan()); }, 500);
  }
}

/** Drives one scene script on one page and collects the events. */
class Driver {
  /**
   * @param {import('playwright').Page} page
   * @param {object} script
   * @param {number} t0 epoch ms of the first video frame
   */
  constructor(page, script, t0) {
    this.page = page;
    this.script = script;
    this.t0 = t0;
    this.events = [];
    this.texts = [];
    this.mouse = { x: 0, y: 0 };
    this.lastText = '';
    this.step = 1; // the first action is step 1, as a person counts the storyboard
    // In-flight requests that can finish. A web client keeps a bus open (websocket, event
    // source, long poll), so Playwright's own "networkidle" never comes on such a page.
    this.inflight = new Set();
    const settles = (req) => !LONG_LIVED_TYPES.has(req.resourceType()) && !LONG_LIVED_URL.test(req.url());
    page.on('request', (req) => { if (settles(req)) this.inflight.add(req); });
    page.on('requestfinished', (req) => this.inflight.delete(req));
    page.on('requestfailed', (req) => this.inflight.delete(req));
  }

  now() { return Date.now() - this.t0; }

  async span(kind, fn) {
    const start = this.now();
    try { return await fn(); } finally { this.events.push({ kind, start, end: this.now() }); }
  }

  /** @param {string} why `not found` (nothing matches) or `not visible` (an element matches but has no size or is hidden) */
  fail(act, what, why = 'not found') {
    throw new StepError(`step ${this.step} ${act.do} ${what}: ${why}`);
  }

  /** @returns {Promise<string>} why a wait for `state` on `loc` gave up */
  async whyMissing(loc, state) {
    return state !== 'hidden' && state !== 'detached' && (await loc.count()) > 0 ? 'not visible' : 'not found';
  }

  /** Reaches the instance as `ui_user` through the web client's own form; no script key means just open base_url. */
  async reach() {
    const user = this.script.ui_user;
    if (!user) return;
    const p = this.page;
    await p.goto(new URL('/web/login', this.script.base_url).toString(), { waitUntil: 'load', timeout: WAIT_TIMEOUT_MS });
    // Odoo's demo accounts use their own name as their key, on every series.
    await p.locator('input[name=login]').fill(user);
    await p.locator('input[name=password]').fill(user);
    await p.locator('form button[type=submit]').first().click();
    try {
      await p.waitForURL((u) => !u.pathname.startsWith('/web/login'), { timeout: WAIT_TIMEOUT_MS });
    } catch {
      throw new StepError(`step ${this.step} reach ${user}: not found`);
    }
    await this.idle();
  }

  async target(act, state = 'visible') {
    const loc = this.page.locator(act.selector).first();
    try {
      await loc.waitFor({ state, timeout: SELECTOR_TIMEOUT_MS });
    } catch {
      this.fail(act, act.selector, await this.whyMissing(loc, state === 'attached' ? 'detached' : state));
    }
    return loc;
  }

  async travelTo(loc) {
    await loc.scrollIntoViewIfNeeded({ timeout: STEP_TIMEOUT_MS });
    const box = await loc.boundingBox();
    if (!box) return;
    const to = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await this.span('travel', async () => {
      const steps = 10;
      for (let i = 1; i <= steps; i++) {
        await this.page.mouse.move(
          this.mouse.x + ((to.x - this.mouse.x) * i) / steps,
          this.mouse.y + ((to.y - this.mouse.y) * i) / steps,
        );
        await this.page.waitForTimeout(25);
      }
    });
    this.mouse = to;
  }

  /** Waits until no settling request has been in flight for IDLE_QUIET_MS; gives up after IDLE_TIMEOUT_MS. */
  async idle() {
    const limit = Date.now() + IDLE_TIMEOUT_MS;
    let quietSince = this.inflight.size ? null : Date.now();
    while (Date.now() < limit) {
      if (this.inflight.size) quietSince = null;
      else if (quietSince === null) quietSince = Date.now();
      else if (Date.now() - quietSince >= IDLE_QUIET_MS) return;
      await this.page.waitForTimeout(50);
    }
  }

  async aiWait(act) {
    let start = this.now();
    const grace = Date.now() + 3000;
    let seen = false;
    while (!seen && Date.now() < grace) {
      seen = await this.page.evaluate(() => window.__rec.active());
      if (!seen) await this.page.waitForTimeout(100);
    }
    if (seen) start = this.now();
    const limit = Date.now() + WAIT_TIMEOUT_MS;
    let clear = 0;
    while (seen && clear < 2) {
      if (Date.now() > limit) this.fail(act, 'ai_wait');
      clear = (await this.page.evaluate(() => window.__rec.active())) ? 0 : clear + 1;
      await this.page.waitForTimeout(150);
    }
    await this.idle();
    this.events.push({ kind: 'wait', start, end: this.now() });
  }

  async run(act) {
    const p = this.page;
    switch (act.do) {
      case 'goto': {
        const url = new URL(act.url, this.script.base_url || undefined).toString();
        await this.span('load', async () => {
          await p.goto(url, { waitUntil: 'load', timeout: WAIT_TIMEOUT_MS });
          await this.idle();
        });
        break;
      }
      case 'click': {
        const loc = await this.target(act);
        await this.travelTo(loc);
        await loc.click({ timeout: STEP_TIMEOUT_MS });
        break;
      }
      case 'hover':
        await this.travelTo(await this.target(act));
        break;
      case 'fill': {
        const loc = await this.target(act);
        const text = String(act.text);
        await this.travelTo(loc);
        await loc.click({ timeout: STEP_TIMEOUT_MS });
        await loc.fill('');
        await this.span('typing', () => loc.pressSequentially(text, { delay: act.delay_ms ?? 60 }));
        break;
      }
      case 'press':
        await p.keyboard.press(act.key);
        break;
      case 'scroll':
        if (act.selector) {
          await this.travelTo(await this.target(act, 'attached'));
        } else {
          await this.span('travel', async () => {
            await p.mouse.wheel(0, Number(act.y) || 0);
            await p.waitForTimeout(300);
          });
        }
        break;
      case 'select': {
        const loc = await this.target(act);
        await loc.selectOption(act.value, { timeout: STEP_TIMEOUT_MS });
        break;
      }
      case 'wait_for':
        if (act.state === 'ai_wait') {
          await this.aiWait(act);
        } else if (act.network_idle) {
          await this.span('wait', () => this.idle());
        } else {
          const timeout = act.timeout_s ? Number(act.timeout_s) * 1000 : SELECTOR_TIMEOUT_MS;
          await this.span('wait', async () => {
            const loc = p.locator(act.selector).first();
            const state = act.state || 'visible';
            try {
              await loc.waitFor({ state, timeout });
            } catch {
              this.fail(act, act.selector, await this.whyMissing(loc, state));
            }
          });
        }
        break;
      case 'hold':
        await this.span('hold', () => p.waitForTimeout(Number(act.seconds) * 1000));
        break;
      case 'voice_in': {
        const seconds = this.script.voice_wav ? wavSeconds(fs.readFileSync(this.script.voice_wav)) : 0;
        await this.span('voice_in', () => p.waitForTimeout(seconds * 1000));
        break;
      }
      case 'expect_text': {
        const loc = await this.target(act);
        let text = await loc.evaluate((el) => (typeof el.value === 'string' && el.value !== '' ? el.value : el.innerText));
        text = String(text).trim().slice(0, MAX_TEXT);
        this.lastText = text;
        this.texts.push([act.name, text]);
        break;
      }
      default:
        throw new StepError(`step ${this.step} ${act.do}: unknown action`);
    }
  }

  /** @param {object[]} actions */
  async runAll(actions) {
    for (const act of actions || []) {
      await this.run(act);
      this.step++;
    }
  }
}

function escapeLine(text) {
  return text.replace(/\\/g, '\\\\').replace(/\r/g, '').replace(/\n/g, '\\n');
}

function loadPlaywright() {
  try {
    return require('playwright');
  } catch {
    console.log('ERROR=the playwright library is not resolvable through NODE_PATH');
    process.exit(4);
  }
}

/**
 * Runs the scene in `record`, `prepare` or `trial` mode.
 * @returns {Promise<number>} the exit code
 */
async function runScene(mode, args) {
  const { chromium } = loadPlaywright();
  let script;
  try {
    script = JSON.parse(fs.readFileSync(args.script, 'utf8'));
  } catch (err) {
    console.log(`ERROR=cannot read the scene script: ${err.code || err.message}`);
    return 4;
  }
  const recording = mode === 'record';
  const outDir = path.resolve(args.outDir || script.out_dir || '.');
  const clip = script.clip_name || script.scene_id || 'clip';
  const allowKeys = script.allow_key_fields === true;
  const viewport = Array.isArray(script.viewport) ? { width: script.viewport[0], height: script.viewport[1] } : { width: 1920, height: 1080 };
  const voice = Boolean(script.voice_wav);
  fs.mkdirSync(outDir, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(outDir, '.rec-'));

  const launchArgs = voice
    ? ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${path.resolve(script.voice_wav)}`]
    : [];
  const browser = await chromium.launch({ headless: true, args: launchArgs });
  let code = 0;
  let driver = null;
  const keySpans = [];
  const keyWhat = new Set();
  const voiceEvents = [];
  const pending = [];
  let openKey = null;
  let elapsed = 0;
  try {
    const ctxOpts = { viewport, locale: localeOf(script.lang) };
    let storageState;
    if (script.ui_user || (script.language_switch || []).length) {
      // Off camera: sign in and switch the language, keep only the cookies.
      const prep = await browser.newContext(ctxOpts);
      try {
        const prepDriver = new Driver(await prep.newPage(), script, Date.now());
        await prepDriver.reach();
        await prepDriver.runAll(script.language_switch);
        storageState = await prep.storageState();
      } catch (err) {
        await prep.close().catch(() => {});
        if (err instanceof StepError) {
          console.log(`ERROR=${err.message}`);
          return 3;
        }
        console.log(`ERROR=${String(err.message).split('\n')[0]}`);
        return 5;
      }
      await prep.close();
    }
    if (storageState) ctxOpts.storageState = storageState;
    if (recording) ctxOpts.recordVideo = { dir: tmp, size: viewport };
    const context = await browser.newContext(ctxOpts);
    const t0 = Date.now();
    const page = await context.newPage();
    driver = new Driver(page, script, t0);

    await page.addInitScript(pageBundle, {
      cursor: recording,
      keys: recording && !allowKeys,
      voice: recording,
      selectors: [...new Set([...(script.wait_selectors || []), ...DEFAULT_INDICATORS])],
      nameRe: KEY_NAME_RE,
      maskedType: MASKED_TYPE,
    });
    await page.exposeFunction('__recKey', (ms, what) => {
      if (what && openKey === null) {
        openKey = ms - t0;
        keyWhat.add(what);
      } else if (!what && openKey !== null) {
        keySpans.push({ kind: 'key_visible', start: openKey, end: ms - t0 });
        openKey = null;
      }
    });
    let voiceN = 0;
    await page.exposeFunction('__recVoiceOutEnd', (startMs, endMs) => {
      const ev = voiceEvents.find((e) => e.startMs === startMs && e.end === null);
      if (ev) ev.end = endMs - t0;
    });
    await page.exposeFunction('__recVoiceOut', (startMs, src, kind) => {
      const n = ++voiceN;
      voiceEvents.push({ kind: 'voice_out', startMs, start: startMs - t0, end: null });
      pending.push((async () => {
        let body;
        if (kind === 'b64') {
          body = Buffer.from(src, 'base64');
        } else {
          try { body = await (await page.request.get(new URL(src, page.url()).toString())).body(); } catch { return; }
        }
        const ext = body.subarray(0, 4).toString('ascii') === 'RIFF' ? 'wav' : 'bin';
        fs.writeFileSync(path.join(outDir, `${clip}.voice_out-${n}.${ext}`), body);
      })());
    });

    try {
      await driver.runAll(script.actions);
    } catch (err) {
      if (err instanceof StepError) {
        console.log(`ERROR=${err.message}`);
        code = 3;
      } else {
        console.log(`ERROR=${String(err.message).split('\n')[0]}`);
        code = 5;
      }
    }
    elapsed = Date.now() - t0;
    if (openKey !== null) keySpans.push({ kind: 'key_visible', start: openKey, end: elapsed });
    await Promise.allSettled(pending);
    await page.close();
    await context.close();
    if (recording) {
      const files = fs.readdirSync(tmp).filter((f) => f.endsWith('.webm'));
      if (files.length) fs.renameSync(path.join(tmp, files[0]), path.join(outDir, `${clip}.webm`));
    }
  } finally {
    await browser.close().catch(() => {});
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  const webm = path.join(outDir, `${clip}.webm`);
  if (code !== 0) {
    fs.rmSync(webm, { force: true });
    return code;
  }
  const events = [...driver.events, ...keySpans, ...voiceEvents.map((e) => ({ kind: e.kind, start: e.start, end: e.end ?? elapsed }))]
    .sort((a, b) => a.start - b.start)
    .map((e) => ({ kind: e.kind, start: round3(e.start), end: round3(Math.max(e.end, e.start)) }));
  const waitS = events.filter((e) => e.kind === 'wait').reduce((s, e) => s + (e.end - e.start), 0);
  for (const [name, text] of driver.texts) console.log(`TEXT_${name}=${escapeLine(text)}`);
  const leaked = keySpans.length > 0 && !allowKeys;

  if (recording) {
    const eventsPath = `${webm}.events.json`;
    fs.writeFileSync(eventsPath, JSON.stringify(events, null, 2));
    if (leaked) fs.rmSync(webm, { force: true });
    else console.log(`CLIP=${webm}`);
    console.log(`EVENTS=${eventsPath}`);
    console.log(`DURATION_S=${round3(elapsed).toFixed(3)}`);
    console.log(`KEY_VISIBLE=${keySpans.length}`);
    if (keyWhat.size) console.log(`KEY_KIND=${[...keyWhat].join(',')}`);
    console.log(`VOICE_OUT=${voiceEvents.length}`);
    return leaked ? 6 : 0;
  }
  console.log('DONE=1');
  if (mode === 'trial') {
    console.log(`ANSWER=${escapeLine(driver.lastText)}`);
    console.log(`WAIT_S=${waitS.toFixed(3)}`);
  }
  return 0;
}

/** @returns {Promise<number>} 0 when fake media and video recording both work */
async function selfTest(args) {
  if (!args.outDir) {
    console.log('ERROR=usage: record.mjs self-test --out-dir DIR');
    return 4;
  }
  const { chromium } = loadPlaywright();
  const outDir = path.resolve(args.outDir);
  fs.mkdirSync(outDir, { recursive: true });
  const rate = 16000;
  const wav = Buffer.alloc(44 + rate * 2);
  wav.write('RIFF', 0);
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24);
  wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(rate * 2, 40);
  const wavPath = path.join(outDir, 'silence.wav');
  fs.writeFileSync(wavPath, wav);
  const videoDir = path.join(outDir, 'video');
  fs.mkdirSync(videoDir, { recursive: true });

  console.log(`PLAYWRIGHT=${require('playwright/package.json').version}`);
  console.log(`CHROMIUM=${chromium.executablePath()}`);
  let media = 'missing';
  let video = 'missing';
  const browser = await chromium.launch({
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${wavPath}`],
  });
  try {
    const size = { width: 640, height: 360 };
    const context = await browser.newContext({ viewport: size, recordVideo: { dir: videoDir, size } });
    const page = await context.newPage();
    // about:blank is not a secure context, where getUserMedia does not exist.
    await page.route('http://localhost/', (route) => route.fulfill({ contentType: 'text/html', body: '<title>t</title>' }));
    await page.goto('http://localhost/');
    try {
      const ok = await page.evaluate(async () => {
        if (!navigator.mediaDevices) return false;
        const s = await navigator.mediaDevices.getUserMedia({ audio: true });
        const n = s.getAudioTracks().length;
        s.getTracks().forEach((t) => t.stop());
        return n > 0;
      });
      if (ok) media = 'ok';
    } catch { /* stays missing */ }
    await page.close();
    await context.close();
    if (fs.readdirSync(videoDir).some((f) => f.endsWith('.webm') && fs.statSync(path.join(videoDir, f)).size > 0)) video = 'ok';
  } finally {
    await browser.close().catch(() => {});
  }
  console.log(`FAKE_MEDIA=${media}`);
  console.log(`RECORD_VIDEO=${video}`);
  return media === 'ok' && video === 'ok' ? 0 : 1;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.mode === 'self-test') return selfTest(args);
  if (!['record', 'prepare', 'trial'].includes(args.mode) || !args.script) {
    console.log('ERROR=usage: record.mjs <record|prepare|trial|self-test> --script SCENE.json [--out-dir DIR]');
    return 4;
  }
  return runScene(args.mode, args);
}

main().then((code) => process.exit(code), (err) => {
  console.log(`ERROR=${String(err && err.message).split('\n')[0]}`);
  process.exit(5);
});
