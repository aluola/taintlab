/* Record two ready-state excerpts of the real local Streamlit application.
 * Uses a fresh headless test profile, only loopback traffic, and existing frozen
 * data/records. No model request, mock state, DOM text replacement or user profile.
 * The original recording and final MP4 are never changed by this script.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {performance} = require('node:perf_hooks');
const {chromium} = require('./browser_dependencies.cjs');

const root = path.resolve(__dirname, '..');
process.chdir(root);
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const folder = path.join(root, 'demo', 'pickups', stamp);
fs.mkdirSync(folder, {recursive: true});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const relative = file => path.relative(root, file).replaceAll('\\', '/');
const caseFile = path.join(root, 'data/test.jsonl');
const recordFile = path.join(root, 'results/main/records/2e2103f68f4fb005422e4c7c.json');
const initialCaseHash = sha(caseFile);
const initialRecordHash = sha(recordFile);
const scenario = fs.readFileSync(caseFile, 'utf8').trim().split(/\r?\n/).map(JSON.parse).find(c => c.id === 'test_attack_role_forgery_05');
const record = JSON.parse(fs.readFileSync(recordFile, 'utf8'));
if (!scenario || record.case_id !== scenario.id || record.run_id !== '2e2103f68f4fb005422e4c7c' || record.mode !== 'none' || !record.backend_type.includes('llama')) throw new Error('Unexpected frozen recording evidence');
const webpage = scenario.runtime.search_results.find(item => item.id === 'web_1');
const notification = record.state.inbox.find(item => item.recipient_id === 'team_A' && item.body.includes('2099'));
if (!webpage?.content.includes('2099') || !notification) throw new Error('Required injection or actual notification absent from saved data');

async function visibleBox(locator) {
  await locator.waitFor({state: 'visible', timeout: 120000});
  const box = await locator.boundingBox();
  if (!box || box.y < 90 || box.y + box.height > 790 || box.width < 250) {
    throw new Error('Key content is outside the caption-safe region: ' + JSON.stringify(box));
  }
  return box;
}

async function positionStableContent(locator) {
  for (let attempt=0; attempt<20; attempt++) {
    await locator.evaluate(el => el.scrollIntoView({block:'center', behavior:'instant'}));
    await sleep(750);
    const first=await locator.boundingBox();
    await sleep(750);
    const second=await locator.boundingBox();
    if (first && second && Math.abs(first.y-second.y)<2 && Math.abs(first.height-second.height)<2 && second.y>=90 && second.y+second.height<=790) return second;
  }
  return visibleBox(locator);
}

async function recordClip(browser, purpose, duration) {
  const clipDir = path.join(folder, purpose);
  fs.mkdirSync(clipDir, {recursive: true});
  const context = await browser.newContext({
    viewport: {width: 1600, height: 900},
    recordVideo: {dir: clipDir, size: {width: 1600, height: 900}},
    locale: 'zh-CN', colorScheme: 'light', serviceWorkers: 'block'
  });
  const blocked = [];
  const errors = [];
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.hostname === '127.0.0.1') return route.continue();
    blocked.push(url.origin);
    return route.abort();
  });
  const pageCreationStart = performance.now();
  const page = await context.newPage();
  const pageCreationEnd = performance.now();
  page.setDefaultTimeout(120000);
  page.on('pageerror', error => errors.push(String(error)));
  const events = [];
  let zero;
  function log(name, data = {}) {
    const entry = {seconds: zero === undefined ? null : (performance.now()-zero)/1000, name, ...data};
    events.push(entry);
    console.log(JSON.stringify({clip: purpose, ...entry}));
  }
  async function at(second) {
    const wait = zero + second*1000 - performance.now();
    if (wait > 0) await sleep(wait);
  }
  try {
    let target;
    if (purpose === 'source') {
      await page.goto('http://127.0.0.1:8501/?view=live&dataset=test&case=test_attack_role_forgery_05&mode=none', {waitUntil: 'domcontentloaded'});
      await page.getByText('实验注入入口：web；来源：web_1', {exact: true}).waitFor();
      await page.getByText('本地网页与检索快照', {exact: true}).click();
      target = page.locator('pre').filter({hasText: '2099'}).first();
      await target.waitFor({state:'visible'});
      const text = await target.innerText();
      if (text !== webpage.content) throw new Error('Displayed source differs from frozen webpage');
    } else {
      await page.goto('http://127.0.0.1:8501/?view=replay&record=2e2103f68f4fb005422e4c7c&dataset=test&case=test_attack_role_forgery_05&mode=none', {waitUntil:'domcontentloaded'});
      await page.getByText('真实运行记录回放 · 当前画面不执行实时模型推理', {exact:true}).waitFor();
      await page.getByText('运行 ID：2e2103f68f4fb005422e4c7c', {exact:false}).waitFor();
      await page.getByRole('tab', {name:'模拟世界状态', exact:true}).click();
      target = page.getByText(notification.body, {exact:true});
      await target.waitFor({state:'visible'});
      await page.getByText('1. team_A', {exact:true}).waitFor({state:'visible'});
    }
    await positionStableContent(target);
    // Readiness is established before the excerpt starts; the entire loading
    // interval remains in the raw clip, excluded by the recorded trim value.
    await sleep(1500);
    const initialBox = await visibleBox(target);
    const scrollDelta = Math.max(0, Math.min(40, Math.floor(780-initialBox.y-initialBox.height)));
    zero = performance.now();
    log('clip_start_after_key_content_visible', {key_content_box: initialBox});
    await page.screenshot({path:path.join(clipDir, 'start.png')});
    await at(4);
    // A small real UI scroll keeps the already-visible text readable while
    // showing that this is the application rather than an inserted slide.
    await page.mouse.move(1200, 500);
    await page.mouse.wheel(0, -scrollDelta);
    await sleep(250);
    log('ui_scroll', {delta_y:-scrollDelta, key_content_box:await visibleBox(target)});
    await at(6);
    await page.screenshot({path:path.join(clipDir, 'middle.png')});
    await at(9);
    await page.mouse.wheel(0, scrollDelta);
    await sleep(250);
    log('ui_scroll', {delta_y:scrollDelta, key_content_box:await visibleBox(target)});
    await at(duration-0.5);
    await page.screenshot({path:path.join(clipDir, 'end.png')});
    await visibleBox(target);
    await at(duration);
    log('clip_end');
    // Keep a real, already-loaded tail. Encoding can select the exact requested
    // length without padding or extending a static frame.
    await sleep(750);
    const video = page.video();
    await context.close();
    const sourceVideo = await video.path();
    const result = {
      purpose, source_video:relative(sourceVideo),
      trim_start:Number(((zero-pageCreationStart)/1000).toFixed(3)),
      duration, source_sha256:sha(sourceVideo),
      case_id:scenario.id,
      run_id:purpose === 'result' ? record.run_id : null,
      mode:'none', backend:'actual_streamlit_browser_recording',
      content_basis:purpose === 'source' ? 'frozen test scenario web_1 displayed by application' : 'frozen local llama.cpp run simulated inbox displayed by application',
      timing_basis:'monotonic elapsed time from Playwright newPage request; key content was stable for 1.5s before excerpt start and remains visible beyond excerpt end',
      new_page_creation_interval_ms:Number((pageCreationEnd-pageCreationStart).toFixed(3)),
      loading_removed_by_trim:true,
      recommended_overlay:'页面加载已剪辑 · 真实记录回放',
      caption_safe_region:{top:90,bottom:790},
      screenshots:['start.png','middle.png','end.png'].map(name=>relative(path.join(clipDir,name))),
      events, blocked_external_origins:[...new Set(blocked)], page_errors:errors
    };
    fs.writeFileSync(path.join(clipDir, 'timing.json'), JSON.stringify(result,null,2));
    return result;
  } catch (error) {
    await page.screenshot({path:path.join(clipDir,'failed.png')}).catch(()=>{});
    fs.writeFileSync(path.join(clipDir,'failed_events.json'),JSON.stringify(events,null,2));
    await context.close();
    throw error;
  }
}

async function main() {
  const browser = await chromium.launch({headless:true, executablePath:require('./browser_dependencies.cjs').executablePath()});
  try {
    const clips = [];
    clips.push(await recordClip(browser, 'source', 13));
    clips.push(await recordClip(browser, 'result', 14));
    if (sha(caseFile)!==initialCaseHash || sha(recordFile)!==initialRecordHash) throw new Error('Frozen evidence changed during capture');
    const metadata = {
      created_at_utc:new Date().toISOString(), clips,
      source_dataset_sha256:initialCaseHash,
      source_record_sha256:initialRecordHash,
      runtime:'isolated headless Chromium 1228 / Playwright',
      network_policy:'Only 127.0.0.1 requests are allowed; no user browser profile; no cloud or model calls are initiated.',
      original_final_video_modified:false,
      assembly_plan:'original 0-55s + source 13s + result 14s + original 82-240s',
      visual_review:'Screenshots and post-capture frames must be inspected before assembly.'
    };
    fs.writeFileSync(path.join(folder, 'patch_recording_metadata.json'), JSON.stringify(metadata,null,2));
    fs.writeFileSync(path.join(root, 'demo/patch_recording_metadata.json'), JSON.stringify(metadata,null,2));
    console.log(JSON.stringify({metadata:'demo/patch_recording_metadata.json',clips:clips.map(({purpose,source_video,trim_start,duration,source_sha256})=>({purpose,source_video,trim_start,duration,source_sha256}))},null,2));
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
