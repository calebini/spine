import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { buildPages, publicFiles } from './build-pages.mjs';

test('Pages artifact is allowlisted and source links are revision-pinned',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'spine-pages-test-'));
  const output=path.join(root,'site');
  const revision='a'.repeat(40);
  await buildPages(output,{revision});
  const files=(await readdir(output,{recursive:true,withFileTypes:true})).filter(e=>e.isFile()).map(e=>path.relative(output,path.join(e.parentPath||e.path,e.name))).sort();
  assert.deepEqual(files,[...publicFiles,'.nojekyll'].sort());
  const html=await readFile(path.join(output,'index.html'),'utf8');
  const content=await readFile(path.join(output,'content.js'),'utf8');
  assert.ok(html.includes(`/blob/${revision}/docs/AGENT_QUICKSTART.md`));
  assert.ok(html.includes(`/blob/${revision}/README.md`));
  assert.ok(content.includes(`/blob/${revision}/\${p}`));
  assert.ok(content.includes(`/tree/${revision}/deploy`));
  assert.doesNotMatch(html+content,/href="\.\.\//);
  assert.ok(html.includes('src="app.js"'),'Site assets stay relative for project Pages URLs');
  await assert.rejects(buildPages(output),{code:'EEXIST'});
  const local=await readFile(new URL('index.html',import.meta.url),'utf8');
  assert.ok(local.includes('href="../../README.md"'),'Local source links are unchanged');
});

test('Reject invalid publishing metadata',async()=>{
  const root=await mkdtemp(path.join(os.tmpdir(),'spine-pages-invalid-'));
  await assert.rejects(buildPages(path.join(root,'site'),{repository:'../secret'}),/Invalid GitHub/);
  await assert.rejects(buildPages(path.join(root,'site'),{revision:'../../secret'}),/full commit SHA/);
});
