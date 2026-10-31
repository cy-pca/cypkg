// browser.mjs: cypkg's browser build in a real (headless) Chrome.
//
//   node tests/browser.mjs --site DIR --chrome PATH [--shots DIR]
//
// DIR is tools/site.sh's output (DIR/apps/cypkg/: ari's xterm.js page plus cypkg's documents).
// tests/registry/fixture_registry.py serves it and the fixture API from one origin, with a strict
// Content-Security-Policy, as a registry would serve /apps/cypkg/. Chrome is driven over the
// DevTools protocol (Node 22's fetch and WebSocket; no other dependency). Each step sends real keys
// to the terminal and waits for ari's screen text (window.ariadneWeb.text(), from
// transfix/libcvc#887's page) to show what the step should. Exit status 0 when every step passes.
// --shots writes a screenshot of each failed step.

import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const argv = process.argv.slice(2);
const opt = name => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : undefined;
};
const SITE = opt('--site'), CHROME = opt('--chrome'), SHOTS = opt('--shots');
if (!SITE || !CHROME) {
  console.error('usage: browser.mjs --site DIR --chrome PATH [--shots DIR]');
  process.exit(2);
}
const here = path.dirname(fileURLToPath(import.meta.url));
const STEP_MS = Number(process.env.CYPKG_BROWSER_STEP_MS || 60000);
const children = [];
const cleanup = () => children.forEach(c => { try { c.kill(); } catch {} });
process.on('exit', cleanup);

// The fixture registry, serving the site too.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'cypkg-browser-'));
const portFile = path.join(tmp, 'port');
children.push(spawn('python3', ['-I', path.join(here, 'registry', 'fixture_registry.py'),
                                '--port', '0', '--port-file', portFile, '--site', SITE],
                    {stdio: 'inherit'}));
for (let i = 0; !fs.existsSync(portFile) || !fs.readFileSync(portFile, 'utf8'); i++) {
  if (i > 100) { console.error('the fixture registry did not start'); process.exit(1); }
  await new Promise(r => setTimeout(r, 100));
}
const ORIGIN = `http://127.0.0.1:${fs.readFileSync(portFile, 'utf8').trim()}`;

// Chrome, headless, its DevTools endpoint on a port it picks.
const chrome = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${path.join(tmp, 'profile')}`,
  '--no-first-run', '--no-default-browser-check', '--no-sandbox',
  '--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist',
  '--window-size=1024,768', 'about:blank'], {stdio: ['ignore', 'ignore', 'pipe']});
children.push(chrome);
const devtools = await new Promise((resolve, reject) => {
  let err = '';
  const t = setTimeout(() => reject(new Error('Chrome did not start:\n' + err)), 30000);
  chrome.stderr.on('data', d => {
    err += d;
    const m = /DevTools listening on (ws:\/\/[^\s]+)/.exec(err);
    if (m) { clearTimeout(t); resolve(new URL(m[1])); }
  });
  chrome.on('exit', c => reject(new Error(`Chrome exited (${c}):\n` + err)));
});

// The page, through its own DevTools socket.
const target = await (await fetch(`http://${devtools.host}/json/new?about:blank`,
                                  {method: 'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let nextId = 0;
const pending = new Map();
ws.onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
};
const send = (method, params = {}) => new Promise(res => {
  pending.set(++nextId, res);
  ws.send(JSON.stringify({id: nextId, method, params}));
});
const evaluate = async expr => {
  const m = await send('Runtime.evaluate', {expression: expr, returnByValue: true});
  return m.result && m.result.result ? m.result.result.value : undefined;
};
await send('Page.enable');
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: 'window.__csp = []; document.addEventListener("securitypolicyviolation", ' +
          'e => window.__csp.push(e.effectiveDirective + " " + (e.blockedURI || "inline")));'});
const started = Date.now();
await send('Page.navigate', {url: `${ORIGIN}/apps/cypkg/`});

const page = async () => {
  const s = await evaluate(
      'JSON.stringify(window.ariadneWeb ? {state: ariadneWeb.state, log: ariadneWeb.log,' +
      ' text: ariadneWeb.text ? ariadneWeb.text() : "", csp: window.__csp || []} : null)');
  return (s && JSON.parse(s)) || {state: 'none', log: [], text: '', csp: []};
};
// Keys go to xterm.js's input, as typing would.
const KEYS = {Tab: 9, Enter: 13, F10: 121, ArrowRight: 39, ArrowDown: 40};
const key = async name => {
  await evaluate('document.querySelector(".xterm-helper-textarea").focus()');
  for (const type of ['keyDown', 'keyUp'])
    await send('Input.dispatchKeyEvent', {type, key: name, code: name,
                                          windowsVirtualKeyCode: KEYS[name]});
  await new Promise(r => setTimeout(r, 150));
};
const type = async text => {
  await evaluate('document.querySelector(".xterm-helper-textarea").focus()');
  await send('Input.insertText', {text});
  await new Promise(r => setTimeout(r, 150));
};

let failed = 0, n = 0;
// step(name, check): wait until check(screen text) holds; fail on a load failure, a document
// warning or a CSP violation on the way.
async function step(name, check) {
  n++;
  const until = Date.now() + STEP_MS;
  let v;
  for (;;) {
    v = await page();
    const bad = v.state === 'failed' ? 'the page failed' :
                v.log.find(l => /warning|error|does not provide/i.test(l)) ? 'the document warned' :
                v.csp.length ? 'a CSP violation: ' + v.csp.join(', ') : '';
    if (!bad && check(v.text)) {
      console.log(`ok   ${name}` + (n === 1 ? ` (${Date.now() - started} ms from navigation)` : ''));
      return;
    }
    if (bad || Date.now() > until) {
      console.log(`FAIL ${name}${bad ? ': ' + bad : ': timed out'}`);
      console.log('     state: ' + v.state);
      console.log('     log:\n' + v.log.map(l => '       ' + l).join('\n'));
      console.log('     screen:\n' + v.text.split('\n').map(l => '       ' + l).join('\n'));
      if (SHOTS) {
        fs.mkdirSync(SHOTS, {recursive: true});
        const m = await send('Page.captureScreenshot', {format: 'png'});
        if (m.result) fs.writeFileSync(path.join(SHOTS, `${n}.png`), Buffer.from(m.result.data, 'base64'));
      }
      failed++;
      return;
    }
    await new Promise(r => setTimeout(r, 250));
  }
}

const has = s => t => t.includes(s);
await step('the page runs main.ari and searches every build', has('builds 1-10 of 196, 10 packages'));
await step('... against the registry that serves it', has(`registry: ${ORIGIN}`));
await key('Tab'); await type('zstd'); await key('Enter');
await step('typing a query and Enter searches', t => /builds 1-10 of 25, 1 package(?!s)/.test(t));
for (let i = 0; i < 4; i++) await key('Tab');
await key('Enter');
await step('Open starts the package module', has('package: zstd'));
await step('... which loads the package', t => t.includes('install: cvcpkg install zstd') &&
                                               t.includes('builds 1-10 of 25'));
await key('Tab'); await key('Tab'); await key('Enter');
await step('Next pages its builds', has('builds 11-20 of 25'));
await key('Tab'); await key('Enter');
await step('Back returns to the search', t => t.includes('Search: [zstd]') &&
                                              !t.includes('package: zstd'));
// The menu bar: View > Builders, whose window follows the registry's live feed (a WebSocket from
// the page, under the page's CSP).
await key('F10'); await key('ArrowRight'); await key('ArrowDown'); await key('Enter');
await step('View > Builders follows the live feed', has('14 of 20 online · live'));

console.log(failed ? `${failed} of ${n} steps failed` : `all ${n} steps passed`);
ws.close();
// Let Chrome exit before removing its profile: it writes there while it shuts down. Cleanup is
// best effort and never changes the result.
const exited = new Promise(r => chrome.exitCode !== null ? r() : chrome.once('exit', r));
cleanup();
await Promise.race([exited, new Promise(r => setTimeout(r, 5000))]);
try { fs.rmSync(tmp, {recursive: true, force: true, maxRetries: 5, retryDelay: 200}); } catch {}
process.exit(failed ? 1 : 0);
