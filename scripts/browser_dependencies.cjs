/* Optional browser authoring dependency discovery. Daily application use never
   loads this module. Install Playwright separately or set TAINTLAB_PLAYWRIGHT. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const fromFrontend = createRequire(path.resolve(__dirname, '../frontend/package.json'));
function load() {
  const candidates = [process.env.TAINTLAB_PLAYWRIGHT, process.env.CODEX_RUNTIME_NODE_MODULES,
    'playwright', path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')].filter(Boolean);
  for (const candidate of candidates) {
    try { return fromFrontend(candidate); } catch (error) { if (error.code !== 'MODULE_NOT_FOUND') throw error; }
  }
  throw new Error('Browser QA needs Playwright (optional, not needed for daily use). Install it or set TAINTLAB_PLAYWRIGHT to its package directory.');
}
const playwright = load();
function executablePath() {
  if (process.env.TAINTLAB_CHROMIUM) return process.env.TAINTLAB_CHROMIUM;
  const normal = playwright.chromium.executablePath();
  if (fs.existsSync(normal)) return normal;
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData/Local'), 'ms-playwright');
  if (fs.existsSync(cache)) {
    for (const folder of fs.readdirSync(cache).filter(name => /^chromium_headless_shell-\d+$/.test(name)).sort().reverse()) {
      const candidate = path.join(cache, folder, 'chrome-headless-shell-win64/chrome-headless-shell.exe');
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return undefined; // Let Playwright report its precise installation command.
}
module.exports = { ...playwright, executablePath };
