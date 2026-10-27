/* Inspect the real running v2 UI in an isolated headless browser.
   This script never starts a task, mocks a response, or changes model state.
   Use verify_model_offline_windows.py --execute for the controlled lifecycle. */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require('./browser_dependencies.cjs');
const root = path.resolve(__dirname, '..');
const expected = process.argv[2];
assert(['offline', 'restored'].includes(expected), 'Pass offline or restored; no process lifecycle is performed here.');
const directory = path.join(root, 'results/v2/browser');
fs.mkdirSync(directory, { recursive: true });
const evidence = path.join(directory, `model-${expected}.json`);
const screenshot = path.join(directory, `model-${expected}.png`);
const origin = 'http://127.0.0.1:8501';
const report = { started_at: new Date().toISOString(), expected, all_passed: false, browser_context: 'new non-persistent isolated headless context',
  viewport: { width: 1600, height: 900 }, mock_responses: false, dom_injection: false, model_tasks_submitted: 0,
  blocked_external: [], page_errors: [], scope: 'Actual UI and bootstrap response while the separate local model service is genuinely stopped or restored. No physical whole-machine network disconnection.' };
let browser;
async function main() {
  browser = await chromium.launch({ headless: true, executablePath: require('./browser_dependencies.cjs').executablePath() });
  const context = await browser.newContext({ viewport: report.viewport, locale: 'zh-CN' });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    report.blocked_external.push(url.origin);
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => report.page_errors.push(error.message));
  const bootstrapResponse = page.waitForResponse(response => response.url() === origin + '/api/bootstrap' && response.status() === 200);
  await page.goto(origin, { waitUntil: 'networkidle' });
  const bootstrap = await (await bootstrapResponse).json();
  // Never save the bootstrap cookie, CSRF token, or unrelated private session data.
  report.model = { available: bootstrap.model.available, name: bootstrap.model.name, endpoint: bootstrap.model.endpoint };
  assert.equal(report.model.available, expected === 'restored');
  await page.getByRole('button', { name: report.model.name, exact: true }).click();
  const phrase = expected === 'offline' ? '本地模型尚不可用' : '连接时健康检查通过';
  await page.locator('.model-popover').getByText(phrase, { exact: true }).waitFor();
  report.visible_model_status = await page.locator('.model-popover').innerText();
  report.online_indicator = await page.locator('.model-status .status-dot.online').count() === 1;
  assert.equal(report.online_indicator, expected === 'restored');
  assert.equal(await page.locator('.run-messages').count(), 0, 'This isolated browser must not run an inference task.');
  await page.screenshot({ path: screenshot, animations: 'disabled' });
  report.screenshot = path.relative(root, screenshot).replaceAll('\\', '/');
  report.screenshot_sha256 = crypto.createHash('sha256').update(fs.readFileSync(screenshot)).digest('hex');
  assert.equal(report.blocked_external.length, 0);
  assert.equal(report.page_errors.length, 0);
  report.all_passed = true;
  await context.close();
}
main().catch(error => { report.error = String(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  report.finished_at = new Date().toISOString();
  fs.writeFileSync(evidence, JSON.stringify(report, null, 2), 'utf8');
  console.log(JSON.stringify({ all_passed: report.all_passed, expected, evidence, screenshot: report.screenshot, error: report.error }));
});
