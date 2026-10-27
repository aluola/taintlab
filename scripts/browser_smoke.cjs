// Isolated headless development browser; no user profile or external navigation.
const { chromium } = require('./browser_dependencies.cjs');
const fs = require('node:fs');
async function main(){
  const browser=await chromium.launch({headless:true,executablePath:require('./browser_dependencies.cjs').executablePath()});
  const context=await browser.newContext({viewport:{width:1600,height:900},colorScheme:'light',locale:'zh-CN'});
  await context.route('**/*',route=>{const url=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(url.hostname)?route.continue():route.abort();});
  const page=await context.newPage();
  await page.goto('http://127.0.0.1:8501/?case=dev_normal_notification_1');
  await page.getByRole('button',{name:'运行本地模型案例',exact:true}).waitFor();
  await page.screenshot({path:'docs/qa/ui_overview.png'});
  console.log((await page.locator('body').innerText()).slice(0,1500));
  await browser.close();
}
main().catch(e=>{console.error(e);process.exit(1)});
