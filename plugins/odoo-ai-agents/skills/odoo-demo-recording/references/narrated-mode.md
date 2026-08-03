# Narrated evidence mode - overlay bundle + calling convention

Supporting reference for `SKILL.md` § Narrated evidence mode. This file is the concrete bundle -
copy it verbatim as the injected script; do not re-derive or "improve" it mid-run, so a before/
after pair stays visually consistent.

## The bundle (inline HTML/CSS/JS - no CDN, no external fetch)

Pass this exact string as `initScript` (chrome-devtools `navigate_page`) on the FIRST navigation,
and again on every SUBSEQUENT navigation this run (a fresh document wipes injected globals). For
playwright (no `initScript` param exists), pass the identical string as the `function` body of a
`browser_evaluate` call immediately after every `browser_navigate`.

```javascript
(function () {
  if (document.getElementById('__ev_style')) { return; }
  var style = document.createElement('style');
  style.id = '__ev_style';
  style.textContent =
    '#__ev_caption{position:fixed;left:0;right:0;bottom:24px;margin:auto;width:max-content;' +
    'max-width:90%;padding:10px 20px;background:rgba(0,0,0,0.78);color:#fff;' +
    'font:600 20px/1.4 system-ui,sans-serif;text-align:center;border-radius:8px;' +
    'z-index:2147483000;pointer-events:none}' +
    '#__ev_badge{position:fixed;top:16px;right:16px;padding:8px 14px;' +
    'font:700 16px/1.2 system-ui,sans-serif;color:#fff;border-radius:6px;' +
    'z-index:2147483000;pointer-events:none}' +
    '#__ev_badge.before{background:#c0392b}' +
    '#__ev_badge.after{background:#1e8449}' +
    '#__ev_endcard{position:fixed;inset:0;display:none;flex-direction:column;' +
    'align-items:center;justify-content:center;color:#fff;' +
    'font:600 28px/1.5 system-ui,sans-serif;text-align:center;z-index:2147483001;padding:40px}' +
    '#__ev_endcard.bug{background:#c0392b}' +
    '#__ev_endcard.fixed{background:#1e8449}';
  document.head.appendChild(style);

  window.__setCaption = function (text) {
    var el = document.getElementById('__ev_caption');
    if (!el) {
      el = document.createElement('div');
      el.id = '__ev_caption';
      document.body.appendChild(el);
    }
    el.textContent = text;
  };

  window.__setBadge = function (label, sha) {
    var el = document.getElementById('__ev_badge');
    if (!el) {
      el = document.createElement('div');
      el.id = '__ev_badge';
      document.body.appendChild(el);
    }
    el.className = label; // 'before' | 'after'
    el.textContent = (label === 'before' ? 'BEFORE (unfixed)' : 'AFTER (fixed)') + ' ' + sha;
  };

  window.__endCard = function (status, expected, observed) {
    var el = document.getElementById('__ev_endcard');
    if (!el) {
      el = document.createElement('div');
      el.id = '__ev_endcard';
      document.body.appendChild(el);
    }
    el.className = status; // 'bug' | 'fixed'
    el.style.display = 'flex';
    el.innerHTML =
      '<div>' + (status === 'bug' ? 'BUG CONFIRMED' : 'FIX VERIFIED') + '</div>' +
      '<div style="font-size:18px;margin-top:16px">Expected: ' + expected + '</div>' +
      '<div style="font-size:18px;margin-top:8px">Observed: ' + observed + '</div>';
  };
})();
```

Idempotent by construction: re-running it (e.g. after a re-navigation) checks for `#__ev_style`
before creating anything, so calling it twice on the same document is a harmless no-op after the
first call - only a fresh document (new navigation) needs it again.

## Calling convention, in order

1. **Round 2 (state setup), first navigation:** pass the bundle above as `initScript`
   (chrome-devtools) or run it as the first `browser_evaluate` after `browser_navigate`
   (playwright). Immediately follow with one more script-execution call to set the badge, values
   inlined - never passed through `args` (chrome-devtools' `args` is documented for element-uid
   substitution, not arbitrary strings):
   ```javascript
   () => { window.__setBadge('before', 'a1b2c3d'); }
   ```
2. **Round 3 (recording), before EACH step's action:** update the caption with the step's text
   inlined, THEN perform the click/fill for that step, THEN capture the frame (chrome-devtools
   `take_screenshot`) or let playwright's continuous video keep rolling:
   ```javascript
   () => { window.__setCaption('Confirm sales order - line added'); }
   ```
3. **Any additional navigation mid-run:** re-pass the FULL bundle (step 0) again before resuming
   caption updates - a new document does not carry over the previous document's injected globals,
   even though the visual style/behavior is identical.
4. **End of Round 3, before stopping the recorder:** show the end-card and hold it on screen (>= 2s
   of frames / continuous-video time) before `stop_recording` / `browser_stop_video` /
   `close_page` / `browser_close` - mandatory for every narrated take, same as the base flow. Full
   rule: `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T2.
   ```javascript
   () => { window.__endCard('bug', 'Co-loader X appears as vendor on the LCL ocean line', 'Vendor field is empty'); }
   ```

## Why this specific mechanism (and not another)

- `initScript` / `browser_evaluate` are tools this skill's `## Browser tools` section already
  declares - no new MCP capability is introduced.
- The bundle is inline (a `<style>` tag + `window.*` functions built from string literals) - no
  `<script src=...>`, no font/icon CDN, so it survives an Odoo instance's default CSP without any
  CSP relaxation.
- pagecast's `record_page` / `interact_page` schema has no script-injection or evaluate action
  (verified by reading its declared parameters), so it is deliberately excluded as a narrated-mode
  driver - see `SKILL.md` § Narrated evidence mode, "Overlay mechanism".
