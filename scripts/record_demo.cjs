/* Reproducible recording of the actual local Streamlit application.
   Uses an isolated headless Chromium profile and blocks every non-loopback URL.
   No user browser profile, native windows, cloud service, or synthetic model state. */
const fs=require('node:fs');const path=require('node:path');
const {chromium}=require('./browser_dependencies.cjs');
const root=path.resolve(__dirname,'..');process.chdir(root);
const evidence=JSON.parse(fs.readFileSync('demo/selected_evidence.json','utf8'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  fs.mkdirSync('demo/raw',{recursive:true});fs.mkdirSync('demo/qa',{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:require('./browser_dependencies.cjs').executablePath()});
  const context=await browser.newContext({viewport:{width:1600,height:900},recordVideo:{dir:'demo/raw',size:{width:1600,height:900}},locale:'zh-CN',colorScheme:'light'});
  const blocked=[];
  await context.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();blocked.push(u.origin);return route.abort();});
  const started=Date.now();const page=await context.newPage();page.setDefaultTimeout(60000);
  const actions=[];let zero;
  const log=(name,extra={})=>{const entry={seconds:zero?(Date.now()-zero)/1000:null,name,...extra};actions.push(entry);console.log(JSON.stringify(entry));};
  const at=async second=>{const ms=zero+second*1000-Date.now();if(ms>0)await sleep(ms);else if(ms < -3000)log('schedule_late',{planned:second,late_ms:-ms});};
  const navigate=async(url,ready)=>{await page.goto('http://127.0.0.1:8501/'+url,{waitUntil:'domcontentloaded'});await page.getByText(ready,{exact:false}).first().waitFor({state:'visible'});};
  const showTab=async name=>{await page.getByRole('tab',{name,exact:true}).click();log('tab',{name});};
  const replay=async key=>{const r=evidence[key];await navigate(`?view=replay&record=${r.file}&dataset=${key==='recovery'?'dev':'test'}&case=${r.case_id||'dev_attack_01'}&mode=${r.mode||'taint_policy'}`,'真实运行记录回放 · 当前画面不执行实时模型推理');log('replay',{key,run_id:r.run_id});};
  try{
    await navigate('?case=dev_normal_notification_1&mode=taint_policy','运行本地模型案例');
    await sleep(500);zero=Date.now();log('recording_zero');
    await page.screenshot({path:'demo/qa/intro.png'});
    await at(6);await page.getByText('模型与推理配置',{exact:true}).click();log('model_configuration');
    await at(18);await page.getByText('模型与推理配置',{exact:true}).click();
    await at(22);await page.getByRole('button',{name:'运行本地模型案例',exact:true}).click();log('live_normal_start');
    await page.getByText('运行状态',{exact:true}).waitFor();log('live_normal_finished');
    await at(30);await showTab('模拟世界状态');
    await page.screenshot({path:'docs/qa/ui_overview.png'});
    await at(42);await showTab('动作时间线');await page.getByRole('slider').press('Home');
    await at(47);await page.getByRole('slider').press('ArrowRight');
    await at(55);await navigate('?view=live&dataset=test&case=test_attack_role_forgery_05&mode=none','合法任务与可见环境');
    await page.getByText('本地网页与检索快照',{exact:true}).click();log('indirect_payload');
    await at(68);await replay('indirect');await showTab('模拟世界状态');
    await at(82);await replay('none');await showTab('模拟世界状态');
    await at(94);await replay('input_filter');await showTab('动作时间线');
    await at(106);await replay('taint_policy');await showTab('动作时间线');await page.getByRole('slider').press('Home');
    await at(112);await page.getByRole('slider').press('ArrowRight');
    await at(120);await showTab('来源与污点图');await sleep(1500);await page.mouse.wheel(0,850);await sleep(700);
    await page.screenshot({path:'docs/qa/ui_provenance.png'});
    await at(134);await page.mouse.wheel(0,180);log('provenance_scroll');
    await at(148);await replay('recovery');await showTab('动作时间线');await page.getByRole('slider').press('Home');
    await at(158);await page.getByRole('slider').press('ArrowRight');
    await at(166);await page.getByRole('slider').press('End');
    await at(176);await navigate('?view=live&dataset=dev&case=dev_normal_export_2&mode=taint_policy','运行本地模型案例');
    await page.getByRole('button',{name:'运行本地模型案例',exact:true}).click();log('live_confirmation_start');
    await page.getByText('运行状态',{exact:true}).waitFor();await showTab('人工确认');
    await page.getByRole('button',{name:'确认执行一次',exact:true}).waitFor();
    await at(188);await page.getByRole('button',{name:'确认执行一次',exact:true}).click();log('trusted_ui_confirmation_click');
    await page.getByText('等待真实人工确认',{exact:true}).waitFor({state:'hidden'});
    await at(196);await showTab('模拟世界状态');
    await at(202);await navigate('?view=metrics','真实实验结果');log('actual_metrics');
    await sleep(3000);await page.screenshot({path:'demo/qa/metrics.png'});
    await at(215);await page.mouse.wheel(0,280);log('metrics_scroll');
    await at(228);await page.mouse.wheel(0,-280);
    await page.screenshot({path:'demo/qa/end.png'});
    await at(240);
    const trim=(zero-started)/1000;
    await context.close();const video=await page.video().path();await browser.close();
    fs.writeFileSync('demo/recording_timing.json',JSON.stringify({trim_start:trim,duration:240,source_video:path.relative(root,video),viewport:{width:1600,height:900},backend:'actual_streamlit_browser_recording',browser_version:'isolated Chromium 1228',blocked_external_origins:[...new Set(blocked)]},null,2));
    fs.writeFileSync('demo/recording_actions.json',JSON.stringify(actions,null,2));
    console.log('VIDEO '+video);
  }catch(error){
    await page.screenshot({path:'demo/qa/recording_error.png'}).catch(()=>{});
    fs.writeFileSync('demo/recording_actions_failed.json',JSON.stringify(actions,null,2));
    await browser.close();throw error;
  }
}
main().catch(e=>{console.error(e);process.exit(1)});
