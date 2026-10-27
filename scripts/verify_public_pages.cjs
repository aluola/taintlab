/* Anonymous public GitHub page/media smoke check; no existing browser profile. */
const fs = require('node:fs');
const path = require('node:path');
const {chromium, executablePath} = require('./browser_dependencies.cjs');
const root = path.resolve(__dirname,'..');
const report = {checked_at_utc:new Date().toISOString(),authentication:'new isolated anonymous browser context',checks:[],all_passed:false};
async function main(){
  const browser = await chromium.launch({headless:true,executablePath:executablePath()});
  try{
    const context=await browser.newContext({viewport:{width:1366,height:900}});
    const page=await context.newPage();
    const out=path.join(root,'results/publication');fs.mkdirSync(out,{recursive:true});
    for(const item of [
      {name:'repository_readme',url:'https://github.com/aluola/taintlab',text:'最短上手路径'},
      {name:'user_manual',url:'https://github.com/aluola/taintlab/blob/v2.0.0/docs/USER_MANUAL.md',text:'首次安装与项目根目录'},
      {name:'release',url:'https://github.com/aluola/taintlab/releases/tag/v2.0.0',text:'taintlab_project_light.zip'}
    ]){
      const response=await page.goto(item.url,{waitUntil:'domcontentloaded',timeout:90000});
      await page.getByText(item.text,{exact:false}).first().waitFor({timeout:30000});
      await page.screenshot({path:path.join(out,'anonymous_'+item.name+'.png'),fullPage:false});
      const visibleText=await page.locator('body').innerText();
      report.checks.push({name:item.name,url:item.url,status:response.status(),expected_text_visible:visibleText.includes(item.text),passed:response.status()===200&&visibleText.includes(item.text)});
    }
    report.all_passed=report.checks.every(c=>c.passed);
    await context.close();
  }catch(error){report.error=String(error);}
  finally{await browser.close();fs.writeFileSync(path.join(root,'results/publication/public_pages.json'),JSON.stringify(report,null,2));}
  console.log(JSON.stringify(report,null,2));if(!report.all_passed)process.exitCode=1;
}
main();
