// Local-only playback verification in an isolated test browser, without a user profile.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { chromium } = require('./browser_dependencies.cjs');
const root = path.resolve(__dirname, '..');
const media = path.join(root, 'demo/demo.mp4');
const size = fs.statSync(media).size;
const server = http.createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
    res.end('<!doctype html><meta charset="utf-8"><title>本地演示播放验收</title><body style="margin:0;background:#fff"><video id="v" controls muted playsinline style="width:100vw;height:100vh" src="/demo.mp4"></video></body>');
    return;
  }
  if (req.url !== '/demo.mp4') { res.writeHead(404); res.end(); return; }
  const range = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range || '');
  const start = range ? Number(range[1]) : 0;
  const end = range && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
  if (start > end || start >= size) {res.writeHead(416); res.end(); return;}
  const headers = {'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1};
  if (range) headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
  res.writeHead(range ? 206 : 200, headers);
  fs.createReadStream(media, {start, end}).pipe(res);
});
async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({headless: true, executablePath: require('./browser_dependencies.cjs').executablePath()});
  try {
    const context = await browser.newContext({viewport:{width:1600,height:900}});
    const blocked=[];
    await context.route('**/*', route => {const u = new URL(route.request().url()); if(u.hostname==='127.0.0.1') return route.continue(); blocked.push(u.origin); return route.abort();});
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(() => document.querySelector('#v').readyState >= 2, null, {timeout: 15000});
    const metadata = await page.$eval('#v', v => ({duration:v.duration,width:v.videoWidth,height:v.videoHeight,h264Support:v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"')}));
    const samples=[];
    for(const position of [0.5,75,130,169,190,238]) {
      await page.$eval('#v', (v,t) => {v.pause();v.currentTime=t;}, position);
      await page.waitForFunction(t => {const v=document.querySelector('#v');return !v.seeking && Math.abs(v.currentTime-t)<0.2 && v.readyState>=2;}, position);
      await page.$eval('#v',v=>v.play());
      await page.waitForFunction(t => document.querySelector('#v').currentTime > t + 0.5, position);
      const state=await page.$eval('#v',v=>({time:v.currentTime,readyState:v.readyState,paused:v.paused,error:v.error?.message||null,quality:v.getVideoPlaybackQuality().toJSON?.()||{totalVideoFrames:v.getVideoPlaybackQuality().totalVideoFrames,droppedVideoFrames:v.getVideoPlaybackQuality().droppedVideoFrames}}));
      samples.push({requested:position,...state});
    }
    const result={checked_at:new Date().toISOString(),kind:'actual_isolated_browser_playback',metadata,samples,blocked_external_origins:blocked,video_sha256:crypto.createHash('sha256').update(fs.readFileSync(media)).digest('hex'),all_passed:metadata.duration===240 && samples.every(s=>!s.error && s.readyState>=2 && s.time>s.requested+0.5)};
    result.project_version = process.env.TAINTLAB_PROJECT_VERSION || 'unspecified';
    const output = path.resolve(root, process.env.TAINTLAB_PLAYBACK_REPORT || 'demo/playback_validation.json');
    fs.mkdirSync(path.dirname(output), {recursive: true});
    fs.writeFileSync(output,JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2));
    if(!result.all_passed) process.exitCode=1;
  } finally {await browser.close(); await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error(e);server.close();process.exitCode=1});
