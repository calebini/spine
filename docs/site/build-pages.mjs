/** Package only public site assets; preserve local/offline source links in the checkout. */
import { copyFile, mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteDir=path.dirname(fileURLToPath(import.meta.url));
const repoDir=path.resolve(siteDir,'../..');
export const publicFiles=[
  'index.html','styles.css','app.js','content.js','diagrams.js','assets/spine.svg',
  'assets/fonts/inter-regular.ttf','assets/fonts/inter-semibold.ttf',
  'assets/fonts/syne-semibold.ttf','assets/fonts/jetbrains-mono.ttf',
  'assets/fonts/Inter-OFL.txt','assets/fonts/Syne-OFL.txt','assets/fonts/JetBrainsMono-OFL.txt',
];

export async function buildPages(output,{repository='calebini/spine',revision='main'}={}){
  if(!/^[a-z\d][a-z\d-]*\/[a-z\d][\w.-]*$/i.test(repository))throw new Error('Invalid GitHub repository');
  if(!/^(main|[a-f0-9]{40})$/.test(revision))throw new Error('Use main or a full commit SHA');
  // An existing destination is never deleted or overwritten.
  await mkdir(output);
  const base=`https://github.com/${repository}`;
  for(const file of publicFiles){
    const destination=path.join(output,file);
    await mkdir(path.dirname(destination),{recursive:true});
    if(!['index.html','content.js'].includes(file)){
      await copyFile(path.join(siteDir,file),destination);
      continue;
    }
    let text=await readFile(path.join(siteDir,file),'utf8');
    // Source pills are generated at runtime; their paths are repository-relative.
    text=text.replace('href="../../${p}"',`href="${base}/blob/${revision}/\${p}"`);
    const references=[...text.matchAll(/href="(\.\.\/[^\"]+)"/g)];
    for(const [,href] of references){
      const [source,fragment]=href.split('#');
      const absolute=path.resolve(siteDir,source);
      const relative=path.relative(repoDir,absolute);
      if(relative.startsWith('..')||path.isAbsolute(relative))throw new Error(`Source outside repository: ${href}`);
      const type=(await stat(absolute)).isDirectory()?'tree':'blob';
      const link=`${base}/${type}/${revision}/${relative.split(path.sep).map(encodeURIComponent).join('/')}${fragment?'#'+fragment:''}`;
      text=text.replaceAll(`href="${href}"`,`href="${link}"`);
    }
    await writeFile(destination,text);
  }
  await writeFile(path.join(output,'.nojekyll'),'');
  console.log(`Packaged ${publicFiles.length} public assets in ${output} (${repository}@${revision})`);
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  if(!process.argv[2])throw new Error('Usage: node docs/site/build-pages.mjs NEW_OUTPUT_DIRECTORY');
  await buildPages(path.resolve(process.argv[2]),{
    repository:process.env.GITHUB_REPOSITORY||'calebini/spine',
    revision:process.env.GITHUB_SHA||'main',
  });
}
