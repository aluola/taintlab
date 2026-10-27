// Isolated browser smoke test of the actual running Streamlit service.
// No user browser profile is accessed. It does not claim mouse double-clicks.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('./browser_dependencies.cjs');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'results/launcher/validation');
async function main() {
  const port = JSON.parse(fs.readFileSync(path.join(root,'configs/launcher.json'),'utf8')).ui_port;
  const browser = await chromium.launch({headless:true, executablePath:require('./browser_dependencies.cjs').executablePath()});
  try {
    const context = await browser.newContext({viewport:{width:1600,height:1000}});
    const errors=[];
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    const response = await page.goto(`http://127.0.0.1:${port}/`);
    await page.getByRole('heading', {name:'本地小模型 Agent 间接提示注入攻防与污点追踪系统',exact:true}).waitFor({timeout:30000});
    await page.screenshot({path:path.join(out,'actual_running_ui.png'),fullPage:true});
    const text = await page.locator('body').innerText();
    const result = {checked_at:new Date().toISOString(),kind:'actual_running_Streamlit_frontend',url:page.url(),title:await page.title(),http_status:response.status(),page_errors:errors,visible_text:text, screenshot:'results/launcher/validation/actual_running_ui.png',all_passed:response.status()===200 && errors.length===0 && text.includes('Qwen')};
    fs.writeFileSync(path.join(out,'frontend_validation.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2));
    if(!result.all_passed) process.exitCode=1;
  } finally {await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
