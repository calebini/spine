/** Browser QA. Requires playwright-core externally; no production npm dependencies. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, stat, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.SPINE_PLAYWRIGHT_PATH || 'playwright-core');
const siteDir=path.dirname(fileURLToPath(import.meta.url));
const out=path.join(siteDir,'qa-output');
await mkdir(out,{recursive:true});
const url=process.env.SPINE_DOCS_URL||'http://127.0.0.1:8765/docs/site/';
const browser=await chromium.launch({headless:true,...(process.env.SPINE_CHROME_PATH?{executablePath:process.env.SPINE_CHROME_PATH}:{channel:'chrome'})});
const context=await browser.newContext({viewport:{width:1512,height:1100},deviceScaleFactor:1,acceptDownloads:true});
const page=await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
page.on('response',response=>{if(response.status()>=400)errors.push(`${response.status()} ${response.url()}`);});
const failures=[];
try {
  await page.goto(url);
  await page.evaluate(()=>document.fonts.ready);
  assert.equal(await page.title(),'Overview — Spine field guide');
  await page.screenshot({path:path.join(out,'01-overview-desktop.png'),fullPage:true,animations:'disabled'});
  const routes=['getting-started','scheduling','time','delivery','operations','reference','architecture',...Array.from({length:10},(_,i)=>`architecture/${String(i+1).padStart(2,'0')}`)];
  const sources=new Set();
  for(const route of routes){
    await page.goto(`${url}#${route}`);
    await page.waitForFunction(()=>!!document.querySelector('h1'));
    await page.evaluate(()=>document.fonts.ready);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
    assert.equal(overflow,false,`Horizontal page overflow: ${route}`);
    for(const href of await page.locator('#main a[href^="../"]').evaluateAll(as=>as.map(a=>a.getAttribute('href'))))sources.add(href);
    if(route.startsWith('architecture/')){
      assert.equal(await page.locator('.diagram-canvas svg').count(),1);
      await page.locator('.diagram-tools [data-trace]').click();
      assert.ok(await page.locator('.s-trace').count()>0);
      await page.locator('.diagram-tools [data-trace]').click();
      assert.equal(await page.locator('.s-trace').count(),0);
      const clipping=await page.locator('.diagram-canvas svg').evaluate(svg=>{
        const box=svg.viewBox.baseVal;
        const faults=[];
        svg.querySelectorAll('text').forEach(t=>{const b=t.getBBox();if(b.x<0||b.y<0||b.x+b.width>box.width+1||b.y+b.height>box.height+1)faults.push(`outside canvas: ${t.textContent}`);});
        svg.querySelectorAll('.s-node').forEach(g=>{const r=g.querySelector('rect');const right=Number(r.getAttribute('x'))+Number(r.getAttribute('width'));g.querySelectorAll('text').forEach(t=>{const b=t.getBBox();if(b.x+b.width>right-6)faults.push(`outside node: ${t.textContent}`);});});
        return faults;
      });
      if(clipping.length)failures.push({route,clipping});
      await page.screenshot({path:path.join(out,`diagram-${route.split('/')[1]}.png`),fullPage:true,animations:'disabled'});
      await page.getByRole('button',{name:'Expand diagram'}).click();
      assert.equal(await page.locator('#diagram-dialog').evaluate(el=>el.open),true);
      await page.getByRole('button',{name:'Zoom in',exact:true}).click();
      assert.equal(await page.locator('#zoom-level').textContent(),'125%');
      await page.getByRole('button',{name:'Fit',exact:true}).click();
      assert.equal(await page.locator('#zoom-level').textContent(),'100%');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#diagram-dialog').evaluate(el=>el.open),false);
    }
  }
  for(const href of sources)await stat(path.resolve(siteDir,decodeURIComponent(href.split('#')[0])));
  await page.goto(`${url}#architecture/01`);
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'↓ SVG',exact:true}).click();
  const download=await downloadPromise;
  const svg=await readFile(await download.path(),'utf8');
  assert.match(svg,/<svg/);assert.doesNotMatch(svg,/var\(--/);
  await page.keyboard.press('Control+k');
  await page.getByRole('searchbox').fill('retry');
  assert.ok(await page.locator('.search-result').count()>0);
  await page.getByRole('searchbox').fill('<script>nothing matches');
  assert.ok(await page.locator('.empty-result').count()>0);
  await page.getByRole('searchbox').fill('temporal');
  await page.locator('.search-result').first().click();
  assert.equal(await page.locator('#search-dialog').evaluate(el=>el.open),false);
  await page.goto(`${url}#getting-started`);
  await page.locator('.copy-button').first().click();
  await page.waitForFunction(()=>/copied|Clipboard/.test(document.querySelector('#toast').textContent));
  assert.match(await page.locator('#toast').textContent(),/copied|Clipboard/);
  for(const theme of ['voltage-blue','cortex-purple','signal-live','inverted','cortex-dark']){
    await page.selectOption('#theme-select',theme);
    assert.equal(await page.evaluate(()=>document.documentElement.className),`theme-${theme}`);
    if(theme==='inverted')await page.screenshot({path:path.join(out,'theme-inverted.png'),fullPage:true,animations:'disabled'});
  }
  await page.goto(`${url}#scheduling`);
  await page.locator('.toc a').filter({hasText:'Update, cancel, and replay'}).click();
  await page.waitForFunction(()=>location.hash==='#scheduling/change');
  await page.goto(`${url}#overview`);
  const mobile=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1,isMobile:true,hasTouch:true,reducedMotion:'reduce'});
  const phone=await mobile.newPage();
  phone.on('pageerror',error=>errors.push(error.message));
  await phone.goto(url);
  await phone.evaluate(()=>document.fonts.ready);
  await phone.screenshot({path:path.join(out,'02-overview-mobile.png'),fullPage:true});
  await phone.getByRole('button',{name:'Open navigation'}).click();
  assert.equal(await phone.locator('#menu-button').getAttribute('aria-expanded'),'true');
  await phone.locator('.sidebar a[href="#getting-started"]').click();
  await phone.waitForFunction(()=>document.querySelector('#menu-button').getAttribute('aria-expanded')==='false');
  assert.equal(await phone.locator('#menu-button').getAttribute('aria-expanded'),'false');
  for(const route of routes){
    await phone.goto(`${url}#${route}`);
    assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`Mobile overflow: ${route}`);
  }
  await phone.goto(`${url}#architecture/07`);
  await phone.screenshot({path:path.join(out,'03-diagram-mobile.png'),fullPage:true});
  await phone.getByRole('button',{name:'Expand diagram'}).click();
  await phone.getByRole('button',{name:'Zoom in',exact:true}).click();
  await phone.getByRole('button',{name:'Close expanded diagram'}).click();
  await phone.goto(`${url}#scheduling`);
  await phone.screenshot({path:path.join(out,'04-guide-mobile.png'),fullPage:true});
  const local=await browser.newPage();
  await local.goto(`file://${path.join(siteDir,'index.html')}#architecture/08`);
  assert.equal(await local.locator('.diagram-canvas svg').count(),1,'File URL must work without a server');
  const accessibility=[];
  if(process.env.SPINE_AXE_PATH){
    await page.emulateMedia({reducedMotion:'reduce'});
    for(const route of ['overview','getting-started','architecture','architecture/03','delivery']){
      await page.goto(`${url}#${route}`);
      await page.addScriptTag({path:process.env.SPINE_AXE_PATH});
      const violations=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary})).slice(0,6)}));});
      if(violations.length)accessibility.push({route,violations});
    }
    for(const theme of ['voltage-blue','cortex-purple','signal-live','inverted']){
      await page.goto(`${url}?theme=${theme}#overview`);
      await page.addScriptTag({path:process.env.SPINE_AXE_PATH});
      const violations=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}));});
      if(violations.length)accessibility.push({theme,violations});
    }
  }
  console.log(JSON.stringify({routes:routes.length,sourceLinks:sources.size,errors,diagramTextClipping:failures,accessibility,output:out},null,2));
  assert.deepEqual(errors,[],'Browser errors');
  assert.deepEqual(failures,[],'Diagram text clipping');
  assert.deepEqual(accessibility,[],'Accessibility violations');
} finally {await browser.close();}
