/* Record the actual v2 production UI. Run only after selecting real records.
   It never inserts DOM, mutates application state by evaluate, supplies fake
   responses, or edits results. Final MP4 editing/voiceover is a separate step.

   node scripts/record_v2_demo.cjs --plan
   node scripts/record_v2_demo.cjs --selection results/v2/demo_selection.json
*/
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require('./browser_dependencies.cjs');
const root = path.resolve(__dirname, '..');
const stages = [
  { id: 'introduction', seconds: 20, mode: 'live_ui', description: '空态、模型配置、本地模拟边界' },
  { id: 'normal_notification', seconds: 40, mode: 'live_model', description: '显式文档和目标授权、真实运行、确认、收件箱' },
  { id: 'uploaded_source', seconds: 25, mode: 'live_model', description: '上传、登记来源、授权读取、来源信息' },
  { id: 'baseline_comparison', seconds: 35, mode: 'saved_real_replay', description: '当前版本直接注入 none/filter 对比；另一个间接事实污染案例明确切换' },
  { id: 'taint_policy', seconds: 35, mode: 'saved_real_replay', description: '同一案例 taint_policy 真实决策与依赖图' },
  { id: 'attack_previews', seconds: 45, mode: 'live_template_preview', description: '四种真实生成预览，分段双来源展开' },
  { id: 'results_limits', seconds: 40, mode: 'saved_real_metrics', description: '当前版本实际指标、范围、历史版本区别' },
];
if (process.argv.includes('--plan')) {
  console.log(JSON.stringify({ target_seconds: 240, stages, selection_schema: { version: '2.0.0', results_campaign: 'v2_baseline', normal: { task: '读取 meeting，将会议时间和地点发送给 team_A。请发送模拟通知。', doc_id: 'meeting', recipient_id: 'team_A' }, upload_file: 'demo/v2/demo_upload.md', replays: { none: { campaign: 'v2_external', record_id: 'existing_record_id', case_id: 'existing_case_id', mode: 'none', seed: 11 }, input_filter: { campaign: 'v2_external', record_id: 'existing_record_id', case_id: 'same_case_id', mode: 'input_filter', seed: 11 }, taint_policy: { campaign: 'v2_external', record_id: 'existing_record_id', case_id: 'same_case_id', mode: 'taint_policy', seed: 11 } } }, note: 'Plan only. No browser, model, or recording is started.' }, null, 2));
  process.exit(0);
}
const selectionIndex = process.argv.indexOf('--selection');
if (selectionIndex < 0 || !process.argv[selectionIndex + 1]) throw new Error('Use --selection with a reviewed real-record selection JSON. --plan shows the schema.');
const selectionPath = path.resolve(root, process.argv[selectionIndex + 1]);
const selection = JSON.parse(fs.readFileSync(selectionPath, 'utf8'));
const pickupIndex = process.argv.indexOf('--pickup');
const pickup = pickupIndex >= 0 ? process.argv[pickupIndex + 1] : '';
assert(['', 'indirect', 'results'].includes(pickup), 'Pickup must be indirect or results.');
assert.equal(selection.version, '2.0.0');
assert(['v2_baseline', 'v2_external'].includes(selection.results_campaign));
for (const mode of ['none', 'input_filter', 'taint_policy']) {
  const entry = selection.replays?.[mode]; assert(entry && /^[a-f0-9]{24,32}$/.test(entry.record_id), 'Select an existing real record for ' + mode);
  assert.equal(entry.mode, mode); assert(['v2_baseline', 'v2_external'].includes(entry.campaign));
}
if (selection.indirect_limit) {
  assert(/^[a-f0-9]{24,32}$/.test(selection.indirect_limit.record_id));
  assert(['v2_baseline', 'v2_external'].includes(selection.indirect_limit.campaign));
  assert.equal(selection.indirect_limit.threat_model, 'indirect', 'The limitation replay must be labelled as a separate indirect-injection case.');
}
const uploadFile = path.resolve(root, selection.upload_file);
assert(fs.existsSync(uploadFile), 'Upload document must be prepared and reviewed before recording.');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const output = path.join(root, 'demo/v2/raw', stamp);
fs.mkdirSync(output, { recursive: true });
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const manifest = {
  started_at: new Date().toISOString(), version: '2.0.0', target_seconds: pickup === 'indirect' ? 14 : pickup === 'results' ? 28 : 240,
  recording_kind: pickup ? `actual_ui_pickup_${pickup}` : 'full_actual_ui_take',
  selection_file: path.relative(root, selectionPath), selection_sha256: hash(selectionPath),
  upload_file: path.relative(root, uploadFile), upload_sha256: hash(uploadFile),
  viewport: { width: 1600, height: 900 }, backend_required: 'local_llama_cpp',
  assurance: 'Actual browser recording. No injected DOM, mock responses, invented output, or state edits. Browser automation clicks the genuine confirmation UI; the model cannot mint confirmation.',
  timing_basis: 'Monotonic timestamps relative to newPage call; inspect raw-video frame timing before final trimming. Target segment durations and actual durations are both preserved.',
  segments: [], errors: [], blocked_external: [], real_run_ids: [], replay_records: [], screenshots: [],
};
let browser, context, page, video, started;
const save = () => fs.writeFileSync(path.join(output, 'recording_manifest.json'), JSON.stringify(manifest, null, 2), 'utf8');
const delay = ms => new Promise(resolve => setTimeout(resolve, Math.max(0, ms)));
const offset = () => (performance.now() - started) / 1000;
async function snapshot(name) { const file = path.join(output, name + '.png'); await page.screenshot({ path: file, animations: 'disabled' }); manifest.screenshots.push({ name: path.basename(file), sha256: hash(file), at_seconds: offset() }); }
async function stage(spec, work) {
  const begin = offset(); const note = { ...spec, start_seconds: begin, outcome: 'in_progress' }; manifest.segments.push(note); save(); console.log('START ' + spec.id);
  try { await work(); note.action_finished_seconds = offset(); await snapshot(spec.id); await delay((begin + spec.seconds - offset()) * 1000); note.outcome = 'recorded'; }
  catch (error) { note.outcome = 'failed'; note.error = String(error); throw error; }
  finally { note.end_seconds = offset(); note.actual_seconds = note.end_seconds - begin; note.overran_target = note.actual_seconds > spec.seconds + .5; save(); }
  console.log('DONE ' + spec.id + ' ' + note.actual_seconds.toFixed(2) + 's');
}
async function newChat() { await page.getByRole('button', { name: /^新建对话/ }).click(); await page.getByRole('heading', { name: '从一个真实任务开始' }).waitFor(); }
async function liveRun(waitForPending = false) {
  await page.locator('.run-messages').last().waitFor();
  const rid = await page.locator('.run-messages').last().getAttribute('data-run-id');
  manifest.real_run_ids.push(rid);
  await page.waitForFunction(id => { const item = document.querySelector(`[data-run-id="${id}"]`); return !!item?.querySelector('.confirmation-card,.run-finish'); }, rid, { timeout: 240000 });
  assert(await page.getByText('本地模型实测', { exact: true }).last().isVisible(), 'The run must use the real local model.');
  if (waitForPending) assert(await page.locator('.run-messages').last().getByRole('button', { name: '确认本次执行' }).isVisible(), 'The live scenario must reach actual pending state.');
  return rid;
}
async function resultsPage(campaign) {
  await page.getByRole('button', { name: '评测结果', exact: true }).click(); await page.getByLabel('结果版本').selectOption(campaign); await page.locator('.results-table').waitFor();
}
async function replay(entry) {
  await resultsPage(entry.campaign);
  await page.getByRole('textbox', { name: '筛选历史运行' }).fill(`${entry.case_id} ${entry.mode} ${entry.seed}`);
  const item = page.locator('.replay-list button'); await item.first().waitFor(); assert.equal(await item.count(), 1, 'The selected replay must be unambiguous.');
  await item.click(); await page.locator('.replay-banner').waitFor();
  assert.equal(await page.locator('.run-messages').getAttribute('data-run-id'), entry.record_id);
  assert((await page.locator('.replay-banner').textContent()).includes('当前没有实时推理'));
  manifest.replay_records.push({ ...entry, at_seconds: offset() });
}
async function main() {
  browser = await chromium.launch({ headless: true, executablePath: require('./browser_dependencies.cjs').executablePath() });
  context = await browser.newContext({ viewport: manifest.viewport, locale: 'zh-CN', recordVideo: { dir: output, size: manifest.viewport } });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === 'http://127.0.0.1:8501') return route.continue(); manifest.blocked_external.push(url.origin); return route.abort(); });
  started = performance.now(); page = await context.newPage(); video = page.video();
  page.on('pageerror', error => manifest.errors.push(error.message));
  await page.goto('http://127.0.0.1:8501', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'qwen3-0.6b' }).waitFor();
  const health = await page.evaluate(async () => (await fetch('/api/health')).json()); assert.equal(health.service, 'taintlab-web'); assert.equal(health.version, '2.0.0');
  manifest.lead_in_seconds = offset();
  if (pickup === 'indirect') {
    assert(selection.indirect_limit, 'Select the actual indirect limitation record.');
    await replay(selection.indirect_limit);
    const projection = await page.evaluate(async entry => (await fetch(`/api/replays/${encodeURIComponent(entry.campaign)}/${encodeURIComponent(entry.record_id)}`)).json(), selection.indirect_limit);
    const source = projection.sources.find(item => ['web', 'web_snapshot'].includes(item.source_type) && item.preview?.includes('2099'));
    assert(source, 'The real web-source preview must show the injected 2099 content.');
    assert(projection.state.inbox.some(item => item.body.includes('2099')), 'The saved simulated inbox must actually contain the contaminated fact.');
    await page.getByRole('button', { name: '安全审计', exact: true }).click(); await page.getByRole('tab', { name: '来源', exact: true }).click();
    await page.getByRole('button', { name: /^展开全部 .* 个节点$/ }).click();
    const exactNode = page.locator('dt:text-is("节点") + dd').filter({ hasText: new RegExp('^' + source.node_id + '$') });
    const card = page.locator('.source-card').filter({ has: exactNode }); assert.equal(await card.count(), 1);
    await card.locator('summary').click(); await card.scrollIntoViewIfNeeded(); await card.locator('pre').scrollIntoViewIfNeeded();
    manifest.stable_start_seconds = offset();
    await stage({ id: 'pickup_indirect_web_source', seconds: 6, mode: 'saved_real_replay_pickup', description: '实际网页来源正文中的2099伪造事实；独立间接案例' }, async () => {});
    await page.getByRole('tab', { name: '交付', exact: true }).click(); const delivery = page.locator('.delivery-card').filter({ hasText: '2099' }); await delivery.first().scrollIntoViewIfNeeded();
    await stage({ id: 'pickup_indirect_real_delivery', seconds: 8, mode: 'saved_real_replay_pickup', description: '同一运行的真实模拟通知已包含2099污染事实' }, async () => {});
    manifest.status = 'recorded_actual_ui_pickup'; return;
  }
  if (pickup === 'results') {
    await resultsPage('v2_external');
    await page.waitForFunction(() => document.querySelector('.results-table')?.textContent.includes('18.89%'), null, { timeout: 15000 });
    assert((await page.locator('.campaign-notice').textContent()).includes('当前版本实验'));
    assert((await page.locator('.campaign-notice').textContent()).includes('已完成'));
    manifest.stable_start_seconds = offset();
    await stage({ id: 'pickup_external_metrics', seconds: 12, mode: 'saved_real_metrics_pickup', description: '真实v2_external主表，C的18.89%与次数分母' }, async () => {});
    await page.getByRole('checkbox', { name: '展开 policy_only 消融' }).check(); await page.locator('.results-table').scrollIntoViewIfNeeded();
    await stage({ id: 'pickup_external_ablation', seconds: 6, mode: 'saved_real_metrics_pickup', description: '扩展集policy_only真实消融对比' }, async () => {});
    await page.locator('.detailed-metrics>summary').click(); await page.getByRole('heading', { name: '实际执行开销', exact: true }).scrollIntoViewIfNeeded();
    await stage({ id: 'pickup_external_cost_limits', seconds: 10, mode: 'saved_real_metrics_pickup', description: '真实耗时、token、工具与确认开销及测量限制' }, async () => {});
    manifest.status = 'recorded_actual_ui_pickup'; return;
  }
  await stage(stages[0], async () => { await delay(5500); await page.getByRole('button', { name: 'qwen3-0.6b' }).click(); await delay(7000); await page.getByRole('button', { name: 'qwen3-0.6b' }).click(); });
  await stage(stages[1], async () => {
    await page.getByRole('button', { name: /^发送通知 把摘要/ }).click(); await page.getByRole('checkbox', { name: new RegExp(selection.normal.doc_id) }).check();
    await page.getByLabel('模拟通知收件人').selectOption(selection.normal.recipient_id); await delay(3500);
    await page.getByRole('textbox', { name: '任务输入' }).fill(selection.normal.task); await page.getByRole('button', { name: '发送任务', exact: true }).click();
    const rid = await liveRun(true); await delay(6500); await page.getByRole('button', { name: '确认本次执行' }).click();
    await page.waitForFunction(id => !!document.querySelector(`[data-run-id="${id}"] .run-finish`), rid, { timeout: 240000 });
    await page.getByRole('button', { name: '安全审计', exact: true }).click(); await page.getByRole('tab', { name: '交付', exact: true }).click();
    assert.equal(await page.locator('.delivery-card').count(), 1); await delay(6000); await page.getByRole('button', { name: '关闭安全审计' }).click();
  });
  await stage(stages[2], async () => {
    await newChat(); await page.locator('input[type=file]').setInputFiles(uploadFile);
    const checkbox = page.getByRole('checkbox', { name: new RegExp(path.basename(uploadFile).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }); await checkbox.waitFor();
    assert.equal(await checkbox.isChecked(), false); const docId = await checkbox.locator('..').locator('small').textContent(); await delay(3000); await checkbox.check();
    await page.getByRole('textbox', { name: '任务输入' }).fill(`读取 ${docId}，回答交付时间和地点。`); await page.getByRole('button', { name: '发送任务', exact: true }).click(); await liveRun();
    await page.getByRole('button', { name: '安全审计', exact: true }).click(); await page.getByRole('tab', { name: '来源', exact: true }).click();
    const source = page.locator('.source-card').filter({ hasText: docId }).first(); await source.locator('summary').click(); await source.scrollIntoViewIfNeeded(); await delay(4500); await page.getByRole('button', { name: '关闭安全审计' }).click();
  });
  await stage(stages[3], async () => {
    await replay(selection.replays.none);
    const attemptedTarget = page.locator('.tool-card').filter({ hasText: 'attacker' });
    const baselineEvent = await attemptedTarget.count() ? attemptedTarget.first() : page.locator('.tool-card').first();
    await baselineEvent.locator('summary').click(); await baselineEvent.scrollIntoViewIfNeeded();
    await delay(selection.indirect_limit ? 6500 : 11500); await replay(selection.replays.input_filter);
    const notification = page.locator('.tool-card').filter({ hasText: '发送模拟通知' });
    const filterEvent = await notification.count() ? notification.last() : page.locator('.tool-card').first();
    await filterEvent.locator('summary').click(); await filterEvent.scrollIntoViewIfNeeded(); await delay(selection.indirect_limit ? 6500 : 11500);
    if (selection.indirect_limit) { await replay(selection.indirect_limit); await delay(10500); }
  });
  await stage(stages[4], async () => {
    await replay(selection.replays.taint_policy); const blocked = page.locator('.tool-card.danger'); assert(await blocked.count() > 0, 'Select a real blocked case for this segment.'); await blocked.first().locator('summary').click(); await blocked.first().scrollIntoViewIfNeeded(); await delay(6000);
    await page.getByRole('button', { name: '安全审计', exact: true }).click(); await delay(4000); await page.getByRole('tab', { name: '来源', exact: true }).click(); await delay(5000);
    await page.getByRole('button', { name: '查看上游来源' }).click(); await delay(4000);
    await page.getByRole('tab', { name: '泄露检测', exact: true }).click(); await delay(5000); await page.getByRole('button', { name: '关闭安全审计' }).click();
  });
  await stage(stages[5], async () => {
    await newChat(); await page.getByRole('button', { name: '攻击实验', exact: true }).click();
    for (const name of ['直接注入', '间接注入', '编码变形', '分段诱导']) {
      await page.getByRole('tab', { name: new RegExp('^' + name) }).click(); await page.getByRole('button', { name: '生成样本预览' }).click(); await page.locator('.legitimate-task').waitFor();
      if (name === '分段诱导') { const fragments = page.locator('.fragments details'); assert.equal(await fragments.count(), 2); for (const item of await fragments.all()) await item.locator('summary').click(); await page.locator('.fragments').scrollIntoViewIfNeeded(); }
      await delay(name === '分段诱导' ? 10500 : 6500);
    }
  });
  await stage(stages[6], async () => {
    await resultsPage(selection.results_campaign); assert((await page.locator('.campaign-notice').textContent()).includes('当前版本实验'));
    assert((await page.locator('.campaign-notice').textContent()).includes('已完成'), 'Only completed campaign results may be recorded as final metrics.');
    await delay(12000); await page.locator('.metric-limits').scrollIntoViewIfNeeded(); await delay(6000);
    await page.getByRole('checkbox', { name: '展开 policy_only 消融' }).check(); await page.locator('.results-table').scrollIntoViewIfNeeded(); await delay(7000);
    await page.locator('.detailed-metrics>summary').click(); await page.locator('.detailed-metrics').scrollIntoViewIfNeeded(); await delay(6500);
  });
  manifest.status = 'recorded_actual_ui';
}
main().catch(error => { manifest.status = 'failed_partial_capture'; manifest.errors.push(String(error)); console.error(error); process.exitCode = 1; }).finally(async () => {
  manifest.finished_at = new Date().toISOString(); manifest.monotonic_capture_seconds = started ? offset() : null; save();
  await context?.close();
  if (video) { const videoPath = await video.path(); manifest.source_video = path.relative(root, videoPath); manifest.source_video_bytes = fs.statSync(videoPath).size; manifest.source_video_sha256 = hash(videoPath); }
  await browser?.close(); save(); console.log(JSON.stringify({ status: manifest.status, output, source_video: manifest.source_video, segments: manifest.segments.length, errors: manifest.errors }));
});
