(() => {
  const {all:diagrams,render:renderDiagram,escape:e}=window.SpineDiagrams;
  const {pages,sources}=window.SpineContent;
  const main=document.querySelector('#main');
  const diagramNav=document.querySelector('#diagram-nav');
  const searchDialog=document.querySelector('#search-dialog');
  const diagramDialog=document.querySelector('#diagram-dialog');
  const diagramPicker=document.querySelector('#diagram-picker');
  diagramPicker.innerHTML=diagrams.map(d=>`<option value="${d.id}">${d.id} / ${e(d.short)}</option>`).join('');
  const validThemes=['cortex-dark','voltage-blue','cortex-purple','signal-live','inverted'];
  const savedTheme=()=>{try{return localStorage.getItem('spine-docs-theme');}catch{return null;}};
  const requestedTheme=new URLSearchParams(location.search).get('theme')||savedTheme();
  let currentDiagram='01',zoom=1,toastTimer;
  const tracedDiagrams=new Set();
  const motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
  function syncTraceButtons(){
    document.querySelectorAll('[data-trace]').forEach(button=>{
      const enabled=tracedDiagrams.has(button.dataset.trace);
      button.setAttribute('aria-pressed',String(enabled));
      button.textContent=motionPreference.matches?(enabled?'Unhighlight paths':'Highlight paths'):(enabled?'Ⅱ Pause flow':'▷ Trace flow');
    });
  }
  function syncTraces(){
    // Only reader views participate, not the atlas's miniature previews.
    document.querySelectorAll('.diagram-canvas svg, .hero-art svg, #expanded-art svg').forEach(svg=>{
      const enabled=tracedDiagrams.has(svg.dataset.diagram);
      if(!enabled){svg.querySelectorAll('.s-trace').forEach(p=>p.remove());return;}
      if(svg.querySelector('.s-trace'))return;
      svg.querySelectorAll('.s-edge').forEach((path,i)=>{
        const trace=path.cloneNode();
        trace.removeAttribute('marker-end');
        trace.setAttribute('class','s-trace');
        trace.setAttribute('aria-hidden','true');
        trace.style.animationDelay=`${-(i%6)}s`;
        svg.append(trace);
      });
    });
    syncTraceButtons();
  }
  motionPreference.addEventListener('change',syncTraceButtons);
  function applyTheme(theme){const chosen=validThemes.includes(theme)?theme:'cortex-dark';document.documentElement.className=`theme-${chosen}`;document.querySelector('#theme-select').value=chosen;try{localStorage.setItem('spine-docs-theme',chosen);}catch{/* file/private contexts can disable storage */}}
  applyTheme(requestedTheme);
  document.querySelector('#theme-select').addEventListener('change',event=>applyTheme(event.target.value));
  diagramNav.innerHTML=diagrams.map(d=>`<a href="#architecture/${d.id}" data-route="architecture/${d.id}"><span>${d.id}</span>${d.short}</a>`).join('');
  const arrow='↗';
  function overview(){return `<div class="page home-page"><section class="hero"><div class="hero-top"><div class="eyebrow"><span class="line"></span>THE COORDINATION FIELD GUIDE</div><span class="badge">SPINE 0.3.0 / ALPHA</span></div><h1>Plans should survive<br><span class="accent">the agent that made them.</span></h1><div class="hero-intro"><p>A local-first coordination ledger for agents and the people they serve. Give every plan a durable home, every change a history, and every action an explanation.</p><div class="button-row"><a class="button primary" href="#getting-started">Start building plans <span>→</span></a><a class="button" href="#architecture">Explore the architecture <span>${arrow}</span></a></div></div><div class="hero-art"><div class="art-heading"><span>FIG. 01 / THE CONNECTED COORDINATION SYSTEM</span><span class="signal">CANONICAL BY DESIGN</span></div>${renderDiagram('01')}<div class="art-caption"><span>SPINE STORES TRUTH. TICKERD KEEPS TIME. ADAPTERS ACT.</span><a href="#architecture/01">Open system view ${arrow}</a></div></div></section><div class="stat-strip"><div class="stat"><b>One ledger</b><span>A canonical home for every plan</span></div><div class="stat"><b>Five facts</b><span>From authored to delivered</span></div><div class="stat"><b>Ten views</b><span>A complete architecture atlas</span></div><div class="stat"><b>Full history</b><span>Versions, receipts, and attempts</span></div></div><section><div class="section-heading"><div><div class="eyebrow">TWO WAYS INTO SPINE</div><h2>Operate it. Understand it.</h2></div><p>Start with a working plan, or follow the connections that make the system work.</p></div><div class="path-grid"><a class="path-card" href="#getting-started"><span class="card-number">01 / THE OPERATOR PATH</span><h3>From intent to evidence.</h3><p>Create your first schedule, manage time and relationships, and verify the delivery lifecycle.</p><span class="text-link">Open the operator guide →</span><span class="card-art" aria-hidden="true">↗</span></a><a class="path-card" href="#architecture"><span class="card-number">02 / THE ARCHITECTURE PATH</span><h3>See the whole system.</h3><p>Ten illustrated views of authority, data, lifecycles, execution, and operational resilience.</p><span class="text-link">Enter the architecture atlas →</span><span class="card-art" aria-hidden="true">⌘</span></a></div></section><section class="principles" aria-label="Spine design principles"><div><span>01 / AUTHORITY</span><b>The ledger is canonical.</b><p>Calendars, messengers, dashboards, and agents project from Spine’s coordination truth.</p></div><div><span>02 / DURABILITY</span><b>A change leaves a trace.</b><p>Immutable versions and deterministic receipts keep intent explainable and replayable.</p></div><div><span>03 / EVIDENCE</span><b>Every effect has a record.</b><p>External contact follows a persisted attempt. Its outcome becomes part of the ledger.</p></div></section></div>`;}
  function chapter(route){const p=pages[route];return `<article class="page"><header class="chapter-header"><div class="eyebrow"><span class="line"></span>${p.number} / ${p.label}</div><h1>${p.title}</h1><p class="lead">${p.lead}</p><div class="chapter-meta"><span>${p.time}</span><span>SPINE 0.3.0</span><span>SCHEMA 12</span></div></header><div class="content-layout"><div class="prose">${p.sections.map(s=>`<section id="${s.id}" data-section="${s.id}"><h2>${s.title}</h2>${s.body}</section>`).join('')}</div><aside class="toc"><h2>ON THIS PAGE</h2>${p.sections.map(s=>`<a href="#${route}/${s.id}" data-section-link="${s.id}">${s.title}</a>`).join('')}<a href="#architecture">Explore the diagrams ↗</a></aside></div></article>`;}
  function atlas(){return `<section class="page atlas-page"><div class="atlas-intro"><header class="chapter-header"><div class="eyebrow"><span class="line"></span>INSIDE SPINE / THE ARCHITECTURE ATLAS</div><h1>Follow the connections.</h1><p class="lead">Ten perspectives on one system. Begin with the boundaries, travel through the ledger, and trace a plan all the way to its consequences.</p></header><div class="atlas-mark" aria-hidden="true">01—10</div></div><p class="atlas-note">Each plate includes a reading guide, a core invariant, and direct source references. Open any diagram to explore it at full scale.</p><div class="atlas-grid">${diagrams.map(d=>`<a class="atlas-card" href="#architecture/${d.id}"><div class="atlas-card-art" aria-hidden="true">${renderDiagram(d.id)}</div><div class="atlas-card-meta"><span class="card-arrow">↗</span><div class="eyebrow">${d.id} / ${d.type}</div><h2>${d.short}</h2><p>${d.summary}</p></div></a>`).join('')}</div></section>`;}
  function diagramPage(id){const d=diagrams.find(x=>x.id===id);if(!d)return missing();currentDiagram=id;const index=diagrams.indexOf(d),prev=diagrams[index-1],next=diagrams[index+1];return `<article class="page diagram-page"><header class="chapter-header"><div class="diagram-preheading"><div class="eyebrow"><span class="line"></span>PLATE ${d.id} / ${d.type}</div><div class="diagram-pagination">${prev?`<a href="#architecture/${prev.id}" aria-label="Previous diagram">‹</a>`:''}<span>${d.id} / 10</span>${next?`<a href="#architecture/${next.id}" aria-label="Next diagram">›</a>`:''}</div></div><h1>${d.title}</h1><p class="lead">${d.summary}</p></header><figure class="diagram-frame" style="margin:0"><div class="diagram-toolbar"><span>SPINE / ${d.slug.toUpperCase()} / ${d.id}</span><div class="diagram-tools"><button class="small-button" data-expand="${d.id}">↗ Expand diagram</button><button class="small-button" data-download="${d.id}">↓ SVG</button><button class="small-button" data-copy-link>Copy link</button></div></div><div class="diagram-canvas">${renderDiagram(d.id)}</div><div class="diagram-legend"><span class="legend-item"><i class="legend-dot"></i>Coordination truth</span><span class="legend-item"><i class="legend-dot teal"></i>Execution & evidence</span><span class="legend-item"><i class="legend-dot purple"></i>Governance / derivation</span><span class="legend-item"><i class="legend-dot amber"></i>Attention / containment</span></div><figcaption class="diagram-description">${d.boundary||'Explanatory view · read the invariant and source references below for exact scope.'}</figcaption></figure><div class="diagram-notes"><section><h2>How to read this view</h2><ol class="reading-steps">${d.steps.map(s=>`<li>${s}</li>`).join('')}</ol></section><aside class="invariant"><div class="eyebrow" style="margin-bottom:13px">THE INVARIANT</div><p>${d.invariant}</p><div class="eyebrow" style="margin-top:22px">SOURCE OF TRUTH</div>${sources(d.sources)}</aside></div><details class="text-description"><summary>Read the diagram as text</summary><p>${d.desc}</p></details><nav class="diagram-bottom" aria-label="Architecture tour"><a href="${prev?'#architecture/'+prev.id:'#architecture'}"><small>← ${prev?'PREVIOUS PLATE':'ATLAS INDEX'}</small>${prev?prev.short:'All ten system views'}</a><a href="${next?'#architecture/'+next.id:'#getting-started'}"><small>${next?'NEXT PLATE':'START OPERATING'} →</small>${next?next.short:'Your first durable plan'}</a></nav></article>`;}
  function missing(){return `<section class="page"><header class="chapter-header"><div class="eyebrow">FIELD GUIDE / PAGE NOT FOUND</div><h1>Let’s find your way back.</h1><p class="lead">That chapter or diagram isn’t in this edition of the guide.</p><a href="#overview" class="button primary">Return to the overview →</a></header></section>`;}
  function setMenu(open){document.querySelector('#sidebar').classList.toggle('open',open);document.querySelector('#mobile-shade').classList.toggle('open',open);document.querySelector('#menu-button').setAttribute('aria-expanded',String(open));}
  let lastPage='';
  function route(){const raw=location.hash.slice(1)||'overview';if(raw==='main'){main.focus();return;}const [base,part]=raw.split('/');const routeKey=base==='architecture'&&part?raw:base;const changed=routeKey!==lastPage;let label='Overview';
    if(changed){if(base==='overview')main.innerHTML=overview();else if(base==='architecture')main.innerHTML=part?diagramPage(part):atlas();else if(pages[base])main.innerHTML=chapter(base);else main.innerHTML=missing();lastPage=routeKey;window.scrollTo(0,0);}
    if(base==='architecture')label=part?(diagrams.find(x=>x.id===part)?.short||'Unknown diagram'):'Architecture atlas';else if(pages[base])label=pages[base].label;
    if(changed){
      const toolbar=main.querySelector('.diagram-tools');
      if(toolbar){const button=document.createElement('button');button.className='small-button';button.dataset.trace=part;button.type='button';toolbar.prepend(button);}
      const artHeading=main.querySelector('.art-heading');
      if(artHeading){const button=document.createElement('button');button.className='hero-expand';button.dataset.expand='01';button.textContent='Expand ↗';button.setAttribute('aria-label','Expand system context diagram');artHeading.append(button);}
      syncTraces();
    }
    document.querySelector('#breadcrumb').textContent=label;document.title=`${label} — Spine field guide`;
    document.querySelectorAll('[data-route]').forEach(a=>{const active=a.dataset.route===routeKey;a.toggleAttribute('data-active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    diagramNav.classList.toggle('visible',base==='architecture');setMenu(false);
    if(part&&base!=='architecture'){const target=document.getElementById(part);if(target)requestAnimationFrame(()=>target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'}));}
    if(changed&&document.activeElement!==document.body&&!document.activeElement.closest('dialog'))main.focus({preventScroll:true});
  }
  window.addEventListener('hashchange',route);route();
  document.querySelector('#menu-button').addEventListener('click',()=>setMenu(!document.querySelector('#sidebar').classList.contains('open')));
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-trace]');if(!button)return;
    const id=button.dataset.trace;
    if(tracedDiagrams.has(id))tracedDiagrams.delete(id);else tracedDiagrams.add(id);
    syncTraces();
  });
  document.querySelector('#mobile-shade').addEventListener('click',()=>setMenu(false));
  function toast(message,duration=2600){document.querySelector('#toast').textContent=message;document.querySelector('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>document.querySelector('#toast').classList.remove('visible'),duration);}
  const fullscreenButtons=[...document.querySelectorAll('[data-fullscreen]')];
  const fullscreenElement=()=>document.fullscreenElement||document.webkitFullscreenElement;
  let fullscreenWasActive=false;
  function syncFullscreen(){
    const active=Boolean(fullscreenElement());
    document.documentElement.dataset.nativeFullscreen=String(active);
    // Fullscreen promotes the root into the top layer. Re-promote an existing
    // modal so it stays visible above that root instead of being covered by it.
    if(active&&!fullscreenWasActive&&diagramDialog.open){
      const focused=diagramDialog.contains(document.activeElement)?document.activeElement:null;
      diagramDialog.close();
      diagramDialog.showModal();
      focused?.focus({preventScroll:true});
    }
    fullscreenWasActive=active;
    for(const button of fullscreenButtons){
      button.setAttribute('aria-pressed',String(active));
      button.setAttribute('aria-label',active?'Exit native fullscreen':'Enter native fullscreen');
      button.title=active?'Exit native fullscreen (Esc)':'Enter native fullscreen';
      const label=button.querySelector('.fullscreen-label');
      if(label)label.textContent=active?'Exit full screen':'Full screen';
      button.querySelector('path').setAttribute('d',active?'M3 9h6V3m6 0v6h6M9 21v-6H3m18 0h-6v6':'M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6');
    }
  }
  function fullscreenMessage(message){
    if(diagramDialog.open)document.querySelector('#fullscreen-dialog-status').textContent=message;
    else toast(message,7000);
  }
  async function toggleFullscreen(){
    const exiting=Boolean(fullscreenElement()),root=document.documentElement;
    document.querySelector('#fullscreen-dialog-status').textContent='';
    fullscreenButtons.forEach(button=>button.disabled=true);
    try{
      if(exiting){
        const exit=document.exitFullscreen||document.webkitExitFullscreen;
        if(!exit){fullscreenMessage('Press Esc to leave native fullscreen.');return;}
        await exit.call(document);
      }else if(root.requestFullscreen){
        // The click's user activation must reach the native API without an earlier await.
        await root.requestFullscreen({navigationUI:'hide'});
      }else if(root.webkitRequestFullscreen){
        await root.webkitRequestFullscreen();
      }else{
        fullscreenMessage('Native fullscreen is unavailable here. Open this page in Chrome or Safari.');
      }
    }catch{
      fullscreenMessage(exiting?'Could not exit fullscreen. Press Esc to leave.':'This browser blocked fullscreen. Open this page in Chrome or Safari and try again.');
    }finally{
      fullscreenButtons.forEach(button=>button.disabled=false);
      syncFullscreen();
    }
  }
  fullscreenButtons.forEach(button=>button.addEventListener('click',toggleFullscreen));
  document.addEventListener('fullscreenchange',syncFullscreen);
  document.addEventListener('webkitfullscreenchange',syncFullscreen);
  syncFullscreen();
  async function copy(value){try{await navigator.clipboard.writeText(value);return true;}catch{const input=document.createElement('textarea');input.value=value;input.style.cssText='position:fixed;top:0;left:-9999px';document.body.append(input);input.select();let result=false;try{result=document.execCommand('copy');}catch{}input.remove();return result;}}
  function openDiagram(id){
    const diagram=diagrams.find(d=>d.id===id);if(!diagram)return;
    currentDiagram=id;zoom=1;
    diagramPicker.value=id;
    document.querySelector('#expanded-title').textContent=`${id} / ${diagram.short}`;
    document.querySelector('#expanded-art').innerHTML=renderDiagram(id);
    document.querySelector('#expanded-trace').dataset.trace=id;
    document.querySelector('#fullscreen-dialog-status').textContent='';
    syncTraces();updateZoom();
    if(!diagramDialog.open)diagramDialog.showModal();
    document.querySelector('#expanded-canvas').scrollTo(0,0);
  }
  diagramPicker.addEventListener('change',()=>openDiagram(diagramPicker.value));
  function updateZoom(){document.querySelector('#expanded-art').style.width=`${zoom*100}%`;document.querySelector('#zoom-level').textContent=`${Math.round(zoom*100)}%`;document.querySelector('#zoom-out').disabled=zoom<=.5;document.querySelector('#zoom-in').disabled=zoom>=3;}
  document.querySelector('#zoom-in').addEventListener('click',()=>{zoom=Math.min(3,zoom+.25);updateZoom();});
  document.querySelector('#zoom-out').addEventListener('click',()=>{zoom=Math.max(.5,zoom-.25);updateZoom();});
  document.querySelector('#zoom-reset').addEventListener('click',()=>{zoom=1;updateZoom();document.querySelector('#expanded-canvas').scrollTo(0,0);});
  function downloadSVG(id){let source=renderDiagram(id);const css=getComputedStyle(document.documentElement);source=source.replace(/var\((--[\w-]+)\)/g,(_,v)=>css.getPropertyValue(v).trim());const blob=new Blob([source],{type:'image/svg+xml'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`spine-${id}-${diagrams.find(x=>x.id===id).slug}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('SVG exported with the current theme.');}
  document.addEventListener('click',async event=>{const button=event.target.closest('button');if(!button)return;if(button.matches('[data-close-dialog]'))button.closest('dialog').close();if(button.matches('[data-expand]'))openDiagram(button.dataset.expand);if(button.matches('[data-download]'))downloadSVG(button.dataset.download);if(button.matches('[data-copy-link]'))toast(await copy(location.href)?'Diagram link copied.':'Copy the link from your address bar.');if(button.classList.contains('copy-button')){const ok=await copy(button.closest('.code-block').querySelector('code').textContent);button.textContent=ok?'Copied ✓':'Select code to copy';toast(ok?'Command copied. Review its paths before running.':'Clipboard unavailable. Select and copy the code.');setTimeout(()=>button.textContent='Copy ↗',2400);}});
  const searchItems=[{title:'Overview',text:'Canonical coordination ledger and planning fabric. Product introduction.',href:'#overview'},...Object.entries(pages).flatMap(([key,p])=>[{title:p.label,text:p.lead,href:'#'+key},...p.sections.map(s=>({title:s.title,text:s.body.replace(/<[^>]*>/g,' ').replace(/\s+/g,' '),href:'#'+key+'/'+s.id}))]),...diagrams.map(d=>({title:`${d.id} · ${d.short}`,text:d.summary+' '+d.desc,href:'#architecture/'+d.id})),...window.SpineContent.commands.map(([title,text,,chapter])=>({title,text,href:'#'+chapter}))];
  function search(query=''){const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);const hits=searchItems.filter(x=>terms.every(t=>(x.title+' '+x.text).toLowerCase().includes(t))).slice(0,18);document.querySelector('#search-results').innerHTML=hits.length?hits.map(x=>`<a class="search-result" role="listitem" href="${x.href}"><b>${e(x.title)}</b><span>${e(x.text.slice(0,125))}${x.text.length>125?'…':''}</span></a>`).join(''):'<p class="empty-result">No matching chapter. Try “work”, “replay”, “binding”, or “schema”.</p>';}
  function openSearch(){search();searchDialog.showModal();const input=document.querySelector('#search-input');input.value='';input.focus();}
  document.querySelector('.search-trigger').addEventListener('click',openSearch);
  document.querySelector('#search-input').addEventListener('input',event=>search(event.target.value));
  document.querySelector('#search-input').addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();document.querySelector('.search-result')?.focus();}if(event.key==='Enter')document.querySelector('.search-result')?.click();});
  document.querySelector('#search-results').addEventListener('click',event=>{if(event.target.closest('a'))searchDialog.close();});
  document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();if(searchDialog.open)searchDialog.close();else if(!diagramDialog.open)openSearch();}if(event.key==='Escape')setMenu(false);});
  for(const dialog of [searchDialog,diagramDialog])dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
})();
