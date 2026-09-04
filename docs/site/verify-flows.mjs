/** Expanded flow regressions. Same external browser tooling as verify.mjs. */
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
const page=await browser.newPage({viewport:{width:1512,height:1000},reducedMotion:'no-preference'});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const inline=page.locator('.diagram-tools [data-trace]');
const expanded=page.locator('#expanded-trace');
const open=()=>page.locator('.diagram-tools [data-expand]').click();
const close=()=>page.getByRole('button',{name:'Close expanded diagram'}).click();
async function moving(){
  const trace=page.locator('#expanded-art .s-trace').first();
  assert.equal(await trace.evaluate(p=>getComputedStyle(p).animationName),'trace-path');
  const offset=await trace.evaluate(p=>getComputedStyle(p).strokeDashoffset);
  await page.waitForFunction(previous=>getComputedStyle(document.querySelector('#expanded-art .s-trace')).strokeDashoffset!==previous,offset);
}
async function completeTraces(selector){
  assert.ok(await page.locator(`${selector} .s-edge`).count()>0);
  assert.equal(await page.locator(`${selector} .s-trace`).count(),await page.locator(`${selector} .s-edge`).count());
}
try{
  await page.goto(url);
  for(let n=1;n<=10;n++){
    const id=String(n).padStart(2,'0');
    await page.goto(`${url}#architecture/${id}`);
    assert.equal(await inline.getAttribute('aria-pressed'),'false','A new diagram starts independently');
    await inline.click();
    await open();
    assert.equal(await expanded.getAttribute('aria-pressed'),'true','Expanded view inherits inline state');
    await completeTraces('#expanded-art');
    await moving();
    await expanded.click();
    assert.equal(await inline.getAttribute('aria-pressed'),'false','Expanded control updates inline view');
    assert.equal(await page.locator('.s-trace').count(),0);
    await expanded.click();
    await completeTraces('.diagram-canvas');
    await page.locator('#zoom-in').click();
    await moving();
    await page.locator('#zoom-reset').click();
    await close();
    await open();
    assert.equal(await expanded.getAttribute('aria-pressed'),'true','Reopening retains state');
    await completeTraces('#expanded-art');
    await close();
  }
  await page.goto(`${url}#architecture/01`);
  assert.equal(await inline.getAttribute('aria-pressed'),'true','Route changes retain per-diagram state');
  await open();
  await page.locator('#diagram-dialog [data-fullscreen]').click();
  await page.waitForFunction(()=>Boolean(document.fullscreenElement));
  assert.equal(await page.locator('#diagram-dialog').evaluate(d=>d.open),true);
  await moving();
  await expanded.click();
  assert.equal(await page.locator('#expanded-art .s-trace').count(),0);
  await expanded.click();
  await moving();
  const picker=page.getByRole('combobox',{name:'Choose diagram'});
  assert.equal(await picker.locator('option').count(),10);
  for(let n=1;n<=10;n++){
    await page.locator('#zoom-in').click();
    await page.locator('#expanded-canvas').evaluate(el=>el.scrollTo(80,80));
    const id=String(n).padStart(2,'0');
    await picker.focus();
    await picker.selectOption(id);
    assert.equal(await page.locator('#expanded-art svg').getAttribute('data-diagram'),id);
    assert.equal(await page.locator('#expanded-trace').getAttribute('data-trace'),id);
    assert.equal(await page.locator('#zoom-level').textContent(),'100%');
    assert.deepEqual(await page.locator('#expanded-canvas').evaluate(el=>[el.scrollLeft,el.scrollTop]),[0,0]);
    assert.equal(await page.evaluate(()=>Boolean(document.fullscreenElement)),true,'Picker preserves fullscreen');
    assert.equal(await page.locator('#diagram-dialog').evaluate(d=>d.open),true);
    assert.equal(await picker.evaluate(el=>document.activeElement===el),true,'Picker keeps keyboard focus');
    assert.equal(await page.locator('#expanded-title').textContent(),await picker.locator('option:checked').textContent());
    await completeTraces('#expanded-art');
    await moving();
  }
  await expanded.click(); // Diagram 10 is paused independently of diagram 01.
  await picker.selectOption('01');
  assert.equal(await expanded.getAttribute('aria-pressed'),'true');
  await picker.selectOption('10');
  assert.equal(await expanded.getAttribute('aria-pressed'),'false');
  assert.equal(await page.locator('#expanded-art .s-trace').count(),0);
  await picker.selectOption('01');
  assert.equal(await page.evaluate(()=>location.hash),'#architecture/01','Picker leaves the underlying page in place');
  await page.screenshot({path:path.join(out,'expanded-flow-fullscreen.png'),animations:'disabled'});
  await page.locator('#diagram-dialog [data-fullscreen]').click();
  await page.waitForFunction(()=>!document.fullscreenElement);
  await moving();
  await close();

  // The homepage also opens a diagram, without an inline trace button.
  await page.goto(`${url}#overview`);
  await page.locator('.hero-expand').click();
  await expanded.click();
  assert.equal(await page.locator('.hero-art .s-trace').count(),0);
  await expanded.click();
  await completeTraces('.hero-art');
  await moving();

  // Changing system preferences while the viewer is open updates both UI and motion.
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>document.querySelector('#expanded-trace').textContent==='Unhighlight paths');
  assert.equal(await page.locator('#expanded-art .s-trace').first().evaluate(p=>getComputedStyle(p).animationName),'none');
  await expanded.click();
  assert.equal(await expanded.textContent(),'Highlight paths');
  await expanded.click();
  await completeTraces('#expanded-art');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.waitForFunction(()=>document.querySelector('#expanded-trace').textContent.includes('Pause flow'));
  await moving();

  for(const width of [741,390,320]){
    await page.setViewportSize({width,height:844});
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.evaluate(()=>document.fonts.ready);
    const bounds=await page.locator('#diagram-dialog').evaluate(dialog=>{
      const r=dialog.getBoundingClientRect();
      return [...dialog.querySelectorAll('.dialog-heading button, .dialog-heading select')].every(button=>{
        const b=button.getBoundingClientRect();
        return b.left>=r.left&&b.right<=r.right&&b.top>=r.top&&b.bottom<=r.bottom;
      });
    });
    assert.equal(bounds,true,`All expanded controls fit at ${width}px`);
    await expanded.click();
    await expanded.click();
    await page.screenshot({path:path.join(out,`expanded-flow-${width}.png`),animations:'disabled'});
  }
  if(process.env.SPINE_AXE_PATH){
    await page.addScriptTag({path:process.env.SPINE_AXE_PATH});
    const violations=await page.evaluate(async()=>{
      const result=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});
      return result.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}));
    });
    assert.deepEqual(violations,[],'Expanded viewer accessibility');
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: all 10 expanded flow animations and picker options, bidirectional state, zoom/reopen/navigation, native fullscreen, homepage, reduced motion, mobile controls, and accessibility.');
}finally{await browser.close();}
