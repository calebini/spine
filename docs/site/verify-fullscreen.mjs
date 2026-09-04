/** Native fullscreen and rejection checks; uses the same external tooling as verify.mjs. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SPINE_PLAYWRIGHT_PATH||'playwright-core');
const url=process.env.SPINE_DOCS_URL||'http://127.0.0.1:8765/docs/site/';
const out=path.join(path.dirname(fileURLToPath(import.meta.url)),'qa-output');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.SPINE_CHROME_PATH?{executablePath:process.env.SPINE_CHROME_PATH}:{channel:'chrome'})});
const page=await browser.newPage({viewport:{width:1512,height:1000},reducedMotion:'reduce'});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
try{
  await page.goto(url);
  const top=page.locator('.topbar [data-fullscreen]');
  await top.click();
  await page.waitForFunction(()=>document.fullscreenElement===document.documentElement);
  assert.equal(await top.getAttribute('aria-pressed'),'true');
  assert.equal(await top.getAttribute('aria-label'),'Exit native fullscreen');
  await page.screenshot({path:path.join(out,'native-fullscreen.png'),animations:'disabled'});
  await page.locator('.sidebar a[href="#architecture"]').click();
  assert.equal(await page.evaluate(()=>Boolean(document.fullscreenElement)),true);
  await top.click();
  await page.waitForFunction(()=>!document.fullscreenElement);
  assert.equal(await top.getAttribute('aria-pressed'),'false');

  await page.goto(`${url}#architecture/01`);
  await page.getByRole('button',{name:'Expand diagram',exact:false}).click();
  const dialogToggle=page.locator('#diagram-dialog [data-fullscreen]');
  await dialogToggle.click();
  await page.waitForFunction(()=>document.fullscreenElement===document.documentElement);
  const size=await page.evaluate(()=>{
    const r=document.querySelector('#diagram-dialog').getBoundingClientRect();
    return {width:r.width,height:r.height,viewportWidth:innerWidth,viewportHeight:innerHeight};
  });
  assert.ok(Math.abs(size.width-size.viewportWidth)<=1);
  assert.ok(Math.abs(size.height-size.viewportHeight)<=1);
  assert.equal(await page.evaluate(()=>Boolean(document.elementFromPoint(innerWidth/2,innerHeight/2)?.closest('#diagram-dialog'))),true,'Expanded diagram must remain above the fullscreen root');
  await page.screenshot({path:path.join(out,'native-fullscreen-diagram.png'),animations:'disabled'});
  await dialogToggle.click();
  await page.waitForFunction(()=>!document.fullscreenElement);
  assert.equal(await page.locator('#diagram-dialog').evaluate(d=>d.open),true);
  await page.getByRole('button',{name:'Close expanded diagram'}).click();

  // An exit initiated outside our button must also update its label and state.
  await top.click();
  await page.waitForFunction(()=>Boolean(document.fullscreenElement));
  await page.evaluate(()=>document.exitFullscreen());
  await page.waitForFunction(()=>document.querySelector('[data-fullscreen]').getAttribute('aria-pressed')==='false');

  // Deterministic policy-rejection branch; successful transitions above use the real API.
  await page.evaluate(()=>{
    document.documentElement.requestFullscreen=()=>Promise.reject(new DOMException('Denied by browser policy','NotAllowedError'));
  });
  await top.click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('blocked fullscreen'));
  assert.equal(await page.evaluate(()=>Boolean(document.fullscreenElement)),false);
  assert.equal(await top.isEnabled(),true);
  await page.getByRole('button',{name:'Expand diagram',exact:false}).click();
  await dialogToggle.click();
  await page.waitForFunction(()=>document.querySelector('#fullscreen-dialog-status').textContent.includes('blocked fullscreen'));
  assert.equal(await page.locator('#fullscreen-dialog-status').isVisible(),true);
  await page.keyboard.press('Escape');

  await page.evaluate(()=>{
    document.documentElement.requestFullscreen=undefined;
    document.documentElement.webkitRequestFullscreen=undefined;
  });
  await top.click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('unavailable here'));
  assert.equal(await top.getAttribute('aria-pressed'),'false');
  assert.equal(await top.isEnabled(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: real native enter/exit, navigation, expanded diagram fit, external exit events, blocked and unavailable fallbacks.');
}finally{await browser.close();}
