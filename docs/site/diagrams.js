/* Hand-composed, dependency-free vector diagrams. Specs and runtime remain authoritative. */
(() => {
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const palette = {blue:'var(--text-accent)',teal:'#00C896',purple:'#B080FF',amber:'#FF8C3A',muted:'var(--text-secondary)'};
  let serial = 0;
  const text = (x,y,value,cls='s-body',anchor='start',fill='') => `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}"${fill?` fill="${palette[fill]||fill}"`:''}>${esc(value)}</text>`;
  const tag = (x,y,value,color='blue',anchor='middle') => {
    const w = value.length * 6.4 + 18;
    return `<g><rect x="${anchor==='middle'?x-w/2:x-8}" y="${y-13}" width="${w}" height="20" rx="4" fill="var(--bg-surface)"/>${text(x,y,value,'s-label',anchor,color)}</g>`;
  };
  const node = (x,y,w,title,sub='',color='blue',eyebrow='',h=88) => `<g class="s-node"><title>${esc(title+'. '+sub)}</title><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" class="s-box"/><path d="M${x+1} ${y+19}v${h-38}" stroke="${palette[color]}" stroke-width="2"/>${eyebrow?text(x+18,y+20,eyebrow.toUpperCase(),'s-micro','start',color):''}${text(x+18,y+(eyebrow?45:32),title,'s-title')}${sub.split('|').map((line,i)=>text(x+18,y+(eyebrow?66:55)+i*18,line,'s-body')).join('')}</g>`;
  const edge = (d,color='blue',dashed=false) => `<path d="${d}" class="s-edge${dashed?' dashed':''}" stroke="${palette[color]}" marker-end="url(#ARROW_${color})"/>`;
  const line = (x1,y1,x2,y2,color='blue',dashed=false) => edge(`M${x1} ${y1} L${x2} ${y2}`,color,dashed);
  const boundary = (x,y,w,h,label,color='blue') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" class="s-boundary" stroke="${palette[color]}"/>${text(x+20,y+26,label,'s-micro','start',color)}`;
  const note = (x,y,value,color='muted') => text(x,y,value,'s-label','start',color);
  const point = (x,y,color='blue',r=4) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${palette[color]}"/>`;
  const marks = (w,h) => `<path d="M20 35V20h15 M${w-35} 20h15v15 M20 ${h-35}v15h15 M${w-35} ${h-20}h15v-15" fill="none" stroke="var(--border-default)"/>`;
  function wrap(content,{w=1120,h=620,title='',desc='',id=''}={}) {
    const uid=`s${++serial}`;
    const defs=Object.entries(palette).map(([key,col])=>`<marker id="ARROW_${key}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1L7 4L1 7" fill="none" stroke="${col}" stroke-width="1.2"/></marker>`).join('');
    const svg=`<svg xmlns="http://www.w3.org/2000/svg" class="diagram-svg" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="${uid}-title ${uid}-desc" data-diagram="${id}"><title id="${uid}-title">${esc(title)}</title><desc id="${uid}-desc">${esc(desc)}</desc><defs>${defs}<pattern id="GRID" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="var(--border-default)" stroke-width=".5" opacity=".24"/></pattern><radialGradient id="GLOW"><stop stop-color="var(--text-accent)" stop-opacity=".12"/><stop offset="1" stop-color="var(--text-accent)" stop-opacity="0"/></radialGradient><linearGradient id="CHARGE"><stop stop-color="var(--charge-start)"/><stop offset=".5" stop-color="var(--charge-mid)"/><stop offset="1" stop-color="var(--charge-end)"/></linearGradient><filter id="SOFT"><feGaussianBlur stdDeviation="4"/></filter></defs><style>.s-box{fill:var(--bg-surface);stroke:var(--border-default);stroke-width:.7}.s-node:hover .s-box{stroke:var(--text-accent)}.s-title{font:600 17px Syne,Arial,sans-serif;fill:var(--text-primary)}.s-body{font:12px Inter,Arial,sans-serif;fill:var(--text-secondary)}.s-label{font:11px 'JetBrains Mono',monospace}.s-micro{font:9px 'JetBrains Mono',monospace;letter-spacing:1.2px}.s-edge{fill:none;stroke-width:1;opacity:.85}.s-edge.dashed{stroke-dasharray:4 5}.s-boundary{fill:none;stroke-width:.7;stroke-dasharray:4 6;opacity:.55}.s-rule{stroke:var(--border-default);stroke-width:.7}.s-big{font:600 36px Syne,Arial,sans-serif;fill:var(--text-primary)}.s-strong{font:600 13px Inter,Arial,sans-serif;fill:var(--text-primary)}.s-mono{font:12px 'JetBrains Mono',monospace;fill:var(--text-primary)}.s-pulse{stroke-dasharray:2 24;animation:flow 6s linear infinite}@keyframes flow{to{stroke-dashoffset:-104}}@media(prefers-reduced-motion:reduce){.s-pulse{animation:none}}</style><rect width="${w}" height="${h}" fill="var(--bg-base)"/><rect width="${w}" height="${h}" fill="url(#GRID)"/>${marks(w,h)}${content}</svg>`;
    return svg.replaceAll('ARROW_',`${uid}-arrow-`).replaceAll('id="GRID"',`id="${uid}-grid"`).replaceAll('url(#GRID)',`url(#${uid}-grid)`).replaceAll('id="GLOW"',`id="${uid}-glow"`).replaceAll('url(#GLOW)',`url(#${uid}-glow)`).replaceAll('id="CHARGE"',`id="${uid}-charge"`).replaceAll('url(#CHARGE)',`url(#${uid}-charge)`).replaceAll('id="SOFT"',`id="${uid}-soft"`).replaceAll('url(#SOFT)',`url(#${uid}-soft)`);
  }
  function context() {
    return `<ellipse cx="553" cy="304" rx="340" ry="280" fill="url(#GLOW)"/>
      <circle cx="555" cy="305" r="164" fill="none" stroke="var(--border-default)" stroke-width=".7"/>
      <circle cx="555" cy="305" r="190" fill="none" stroke="var(--border-default)" stroke-width=".5" stroke-dasharray="2 9"/>
      <circle cx="555" cy="305" r="142" fill="none" stroke="var(--text-accent)" stroke-width=".5" opacity=".2"/>
      <path d="M416 216A164 164 0 0 1 660 179 M684 407A164 164 0 0 1 423 402" fill="none" stroke="var(--text-accent)" stroke-width="1" opacity=".5"/>
      <path d="M416 216A164 164 0 0 1 660 179 M684 407A164 164 0 0 1 423 402" fill="none" stroke="var(--text-accent)" stroke-width="4" opacity=".12" filter="url(#SOFT)"/>
      ${edge('M282 248H355Q376 248 392 267L421 298')}
      ${edge('M421 325H353Q333 325 314 351L282 393')}
      ${edge('M698 280H744Q766 280 780 251L825 175')}
      ${edge('M698 317H825','teal')}
      ${edge('M938 219V279','teal')}
      ${edge('M938 367V442','teal')}
      ${edge('M825 341H779Q763 341 757 370L740 437Q734 459 710 459H621Q592 459 592 415V368','teal')}
      ${edge('M671 95H752Q775 95 775 120V241Q775 253 789 253H938V279','purple',true)}
      ${tag(343,235,'commands')}${tag(336,376,'read models')}${tag(767,205,'eligible work')}${tag(760,307,'attempt gate','teal')}${tag(983,254,'cycle','teal')}${tag(980,408,'effect','teal')}${tag(681,449,'outcome evidence','teal')}
      ${node(55,206,227,'Agents & operators','Express intent. Inspect truth.','blue','INPUT / READBACK')}
      ${node(55,376,227,'Views & projections','Agenda · calendar · dashboard','blue','CONSUMERS')}
      ${node(435,57,236,'Governance authority','Configured boundary role','purple','AUTHORIZATION')}
      ${node(825,131,240,'Tickerd','Cadence · modes · singleton','teal','SCHEDULER RUNTIME')}
      ${node(825,279,240,'Adapters','Prepare · execute · normalize','teal','EXTERNAL BOUNDARY')}
      ${node(825,442,240,'External systems','Messenger · calendar · maps','teal','PROJECTION TARGETS')}
      <rect x="421" y="245" width="277" height="121" rx="12" fill="var(--bg-elevated)" stroke="var(--text-accent)" stroke-width=".8"/>
      <rect x="442" y="265" width="20" height="5" rx="1" fill="none" stroke="var(--text-accent)"/><rect x="439" y="275" width="26" height="5" rx="1" fill="none" stroke="var(--text-accent)"/><rect x="442" y="285" width="20" height="5" rx="1" fill="none" stroke="var(--text-accent)"/>
      ${text(479,288,'Spine','s-big')}${text(442,317,'CANONICAL COORDINATION LEDGER','s-micro','start','blue')}${text(442,343,'Intent → versions → durable evidence','s-body')}
      ${point(392,267)}${point(757,370,'teal')}${point(775,120,'purple')}
      ${text(555,502,'ONE SOURCE OF COORDINATION TRUTH','s-micro','middle','blue')}
      ${note(56,563,'Solid paths: commands, work, evidence. Dashed path: configured governance role.')}`;
  }
  function containers() {
    return boundary(36,45,700,495,'SPINE / LOCAL APPLICATION BOUNDARY')+boundary(769,45,315,495,'WORKER PROCESS / RUNTIME','teal')+
      edge('M352 150H393')+edge('M527 194V237')+edge('M704 150H720V349H605V367')+edge('M216 194V370')+edge('M317 414H359')+edge('M926 179V235','teal')+edge('M926 323V367','teal')+edge('M808 409H705','teal')+edge('M880 455V580H705','teal')+
      tag(376,95,'dispatch')+tag(581,224,'domain rules')+tag(634,352,'persist')+tag(248,338,'readback')+tag(925,216,'bounded cycle','teal')+tag(757,398,'ledger','teal')+
      node(66,106,286,'CLI / command surface','spine.commands · receipts','blue','PUBLIC CONTRACTS')+node(393,106,311,'Services','Scheduling · rendering · attempts','blue','ORCHESTRATION')+node(393,237,311,'Pure domain core','Time · recurrence · hashing','blue','DETERMINISTIC RULES')+
      node(66,370,251,'Read services','schedule.show · agenda.show','blue','COMPUTED VIEWS')+node(361,367,343,'SQLite ledger','spine.ledger · transactions · migrations','blue','CANONICAL PERSISTENCE')+
      node(802,91,249,'Tickerd kernel','Owns cadence and process modes','teal','ADMITTED PROVIDER')+node(802,235,249,'Spine runtime bridge','spine.runtime + adapters.tickerd','teal','ELIGIBILITY & DISPATCH')+node(802,367,249,'Attempt-gated adapter','spine.adapters.openclaw','teal','PROVIDER BOUNDARY')+
      node(420,540,284,'Gateway / fake sender','Transport / local evidence','teal','SIDE EFFECT TARGET',80)+note(58,515,'Core remains independent of vendor adapters. Commands and workers share the ledger.');
  }
  function erd() {
    const entity=(x,y,w,title,rows,color='blue')=>`<g class="s-node"><rect x="${x}" y="${y}" width="${w}" height="112" rx="7" class="s-box"/>${text(x+14,y+24,title,'s-mono','start',color)}<path d="M${x} ${y+37}h${w}" class="s-rule"/>${rows.map((r,i)=>text(x+14,y+59+i*18,r,'s-label','start',i===0?color:'muted')).join('')}</g>`;
    return note(36,48,'RELATIONAL MAP / SELECTED TABLES & LOGICAL LINKS')+
      edge('M310 148H335V249H418V272')+edge('M504 204V272')+edge('M364 328H310')+edge('M505 384V455')+edge('M644 328H696')+edge('M976 328H1000V495H1025')+edge('M1165 384V455','teal')+edge('M1165 567V638','teal')+edge('M1165 750V818','teal')+edge('M836 204V272','teal')+edge('M976 148H996V231H1013V521H1025','teal')+edge('M1165 204V272')+edge('M310 694H337V510H365')+edge('M172 455V384')+edge('M644 350H662V509H696')+edge('M662 509V672H696','purple')+edge('M976 694H1025','purple')+edge('M645 131H662V70H1165V92')+edge('M393 204V226H322V616H500V638')+
      tag(528,241,'1:N')+tag(336,315,'1:1*')+tag(670,316,'1:N')+tag(1193,425,'1:N','teal')+tag(1193,610,'1:N','teal')+tag(1210,793,'1:0..1','teal')+tag(861,241,'1:N','teal')+tag(528,425,'1:N')+
      entity(35,92,275,'subjects / subject_groups',['PK subject_id / group_id','membership and participant roles','Catalog scope ≠ send authority'])+
      entity(365,92,280,'coordination_items',['PK item_id','item_type · status','current_version → latest version'])+
      entity(697,92,280,'delivery_targets',['PK delivery_target_id','owner · channel · target_ref','Explicit, active routing identity'],'teal')+
      entity(1027,92,280,'recurrence_revisions',['PK recurrence_revision_id','FK recurrence_set_id → item','Immutable rules and tzdata'])+
      entity(35,272,275,'event_details / task_details',['PK/FK (item_id, version)','Exactly one matching type detail','FK start / due temporal anchor'])+
      entity(365,272,280,'coordination_item_versions',['PK (item_id, version)','Immutable canonical facts','Complete supporting sets'])+
      entity(697,272,280,'notification_policies',['PK policy_id','FK (item_id, version), target','Intent → schedule definition'])+
      entity(1027,272,280,'occurrence_provenance',['PK occurrence_provenance_id','Version + revision + occurrence','Current authorization evidence'])+
      entity(35,455,275,'temporal_anchors',['PK anchor_id','Local / UTC / date / window','Explicit timezone-data version'])+
      entity(365,455,280,'item_locations / roles',['FK (item_id, version)','location_id / subject_id','Copy forward each complete set'])+
      entity(697,455,280,'external_projections',['PK projection_id','FK item + projected version','Current / stale / failed'])+
      entity(1027,455,280,'work_instances',['PK work_instance_id','FK policy + target + provenance','eligible_at_utc · attempt_count'],'teal')+
      entity(35,638,275,'locations',['PK location_id','Place identity · address','Separate from schedule timezone'])+
      entity(365,638,280,'item relations / bindings',['source_item_id → target_item_id','part_of / depends_on','Immutable temporal revisions'])+
      entity(697,638,280,'candidate_actions',['PK candidate_action_id','FK source item + version','Persisted candidate evidence'],'purple')+
      entity(1027,638,280,'side_effect_attempts',['PK attempt_id','FK work / candidate / projection','Request hash · terminal outcome'],'teal')+
      entity(365,818,611,'command_receipts / audit_log',['Command replay evidence and append-only domain history','Cross-cutting evidence links omitted from this selected relational map','Profiles, selectors, and supporting child tables omitted for legibility'])+
      entity(1027,818,280,'notification_renderings',['FK attempt_id','Immutable rendered body evidence','Ordinary reminder prose'],'teal')+
      note(36,982,'1:N = one to many. * Exactly one detail row for events/tasks; none for projects/collections.')+note(36,1005,'Grouped labels summarize related tables. Consult schema + migrations for exhaustive keys and constraints.');
  }
  function lifecycle() {
    return boundary(40,47,1040,225,'01 / CANONICAL VERSION HISTORY')+
      edge('M312 155H421')+edge('M699 155H796')+edge('M548 198V219H911V199','teal')+
      node(76,110,237,'Version 1','Title · time · policies · roles','blue','IMMUTABLE')+node(421,110,278,'Version 2','Full supporting sets copied forward','blue','IMMUTABLE SUCCESSOR')+node(796,110,246,'Current pointer','current_version = 2','teal','ATOMIC SWITCH')+
      tag(365,143,'validated write')+tag(749,142,'commit')+tag(635,232,'same transaction','teal')+
      boundary(40,302,320,243,'02 / ITEM SHELL')+boundary(390,302,320,243,'03 / EVENT PROFILE')+boundary(740,302,340,243,'04 / TASK PROFILE')+
      node(69,356,260,'active','Shell identity is available','blue','',64)+node(69,460,260,'archived','Audit; historical versions intact','muted','',64)+line(199,420,199,458,'muted')+
      node(420,356,260,'scheduled','Current event version','blue','',64)+node(420,460,260,'cancelled','Terminal event state','amber','',64)+line(550,420,550,458,'amber')+
      node(785,351,250,'open','Current task version','blue','',64)+edge('M910 415V435H829V460','teal')+edge('M910 435H992V460','amber')+
      node(762,460,151,'done','Terminal','teal','',64)+node(930,460,131,'cancelled','Terminal','amber','',64)+note(56,583,'Stale target_version → reject. Event/task transitions create a version; shell archiving is audited separately.');
  }
  function sequence(kind) {
    const isCreate=kind==='create';
    const xs=[125,393,677,978];
    const headers=isCreate?['Operator / agent','Command service','SQLite transaction','Readback']:['Operator / agent','Mutation service','Successor truth','Work evidence'];
    let out=xs.map((x,i)=>node(x-93,47,186,headers[i],['Structured request','Deterministic validation','Canonical ledger','Bounded projection'][i],i===3?'teal':'blue','',68)+`<path d="M${x} 115V669" stroke="var(--border-default)" stroke-width=".7" stroke-dasharray="4 6"/>`).join('');
    const msg=(a,b,y,label,col='blue')=>line(xs[a],y,xs[b],y,col)+tag((xs[a]+xs[b])/2,y-10,label,col);
    if(isCreate){
      out+=`<rect x="365" y="273" width="346" height="235" rx="6" fill="var(--text-accent)" opacity=".045" stroke="var(--text-accent)"/>`+
        msg(0,1,162,'schedule.create')+msg(1,2,219,'receipt lookup / replay check')+
        note(414,254,'Replay returns the stored result.','teal')+
        msg(1,2,298,'BEGIN · validate complete bundle')+msg(1,2,354,'item + time + policies + recurrence')+msg(1,2,408,'bounded provenance + optional work')+msg(1,2,466,'audit + one receipt · COMMIT')+
        msg(1,0,541,'schedule_created + item_id','teal')+msg(0,3,590,'schedule.show(item_id)')+msg(3,2,639,'read current truth + lifecycle')+
        note(60,713,'Any child failure rolls back the whole bundle. Authoring creates no adapter attempt.');
    } else {
      out+=msg(0,1,163,'update / cancel + target_version')+msg(1,2,218,'check replay + expected version')+
        `<rect x="365" y="247" width="653" height="328" rx="7" fill="var(--text-accent)" opacity=".045"/>`+
        msg(1,2,276,'normalize successor canonical truth')+msg(2,3,333,'classify affected work')+
        note(721,369,'Stale + eligible + never attempted → cancel','amber')+
        note(721,398,'Still semantically current → retain','teal')+
        note(721,427,'Attempted / in progress → preserve','purple')+
        msg(1,3,477,'optional bounded replacement work')+msg(1,2,542,'truth + work + audit + receipt COMMIT')+
        msg(1,0,613,'receipt with disjoint work-ID sets','teal')+
        note(60,713,'Cancellation creates no replacement work. Protected stale work remains evidence, never fresh authorization.');
    }
    return out;
  }
  function notifications() {
    return boundary(34,53,1052,227,'01 / CANONICAL SCHEDULING · NO EXTERNAL CONTACT')+
      node(59,120,219,'Authored','Item + notification policy','blue','DURABLE INTENT')+node(328,120,219,'Expanded','Virtual opportunities','blue','BOUNDED COMPUTATION')+node(597,120,219,'Materialized','Durable work instances','blue','PERSISTED WORK')+
      line(278,164,326,164)+line(547,164,595,164)+edge('M816 164H979V332','teal')+
      tag(968,150,'eligible_at_utc')+note(60,250,'Recurrence provenance authorizes occurrence-bound opportunities. A policy never calls a provider.')+
      node(841,332,221,'Freshness gate','Source · route · late policy','teal','AT ATTEMPT START',93)+
      edge('M841 380H786','teal')+node(533,332,253,'Attempt started','Body + request durably committed','teal','SIDE_EFFECT_ATTEMPTS',93)+
      edge('M533 380H479','teal')+node(238,332,241,'Adapter invocation','External call permitted','teal','AFTER PERSISTENCE',93)+
      edge('M356 425V467H202V499','teal')+edge('M356 467H501V499','amber')+edge('M356 467H816V499','purple')+
      node(55,499,274,'Succeeded','Terminal success evidence','teal','DELIVERED',91)+node(369,499,274,'Failed / rejected','Reason-coded adapter outcome','amber','NOT DELIVERED',91)+node(683,499,380,'Retry posture','When permitted: same work, persisted next attempt time','purple','RETRY IS NOT A NEW REMINDER',91)+
      note(55,638,'Work lifecycle and attempt lifecycle are separate. “Delivered” requires successful terminal attempt evidence.');
  }
  function recurrence() {
    return node(50,67,290,'Authored time','Local instant / local date / UTC','blue','EXPLICIT BASIS')+node(393,67,285,'Recurrence revision','Rules · exceptions · overrides','blue','IMMUTABLE INPUT')+node(740,67,330,'Pinned timezone data','Stored concrete version + DST policy','purple','DETERMINISTIC RESOLUTION')+
      edge('M195 155V239H385V260')+edge('M535 155V260')+edge('M905 155V239H687V260','purple')+
      boundary(48,198,1024,338,'BOUNDED EXPANSION / EXPLICIT RANGE + LIMIT')+
      node(341,260,407,'Canonical occurrence expansion','Stable occurrence key + exact revision lineage','blue','VIRTUAL OCCURRENCES',94)+
      edge('M545 354V403')+node(341,403,407,'Current occurrence provenance','Persisted consumer authorization for notifications','blue','REGENERATE BEFORE OPPORTUNITIES',94)+
      note(73,470,'09:00 LOCAL')+note(73,492,'UTC is resolved, then persisted.')+note(796,466,'EXCLUSION ≠ DELETION')+note(796,490,'History is retained.')+
      edge('M545 497V574')+node(341,574,407,'Notification opportunities → work','Independent notification cadence; bounded selection','teal','DOWNSTREAM CONSUMER',94)+
      edge('M750 620H945V260H750','amber',true)+tag(941,557,'stale revision','amber')+
      note(53,715,'Series edits change revision identity. Historical UTC trigger and attempt values are never recomputed.');
  }
  function bindings() {
    return boundary(37,49,1045,220,'01 / COORDINATION GRAPH')+
      node(64,116,250,'Trip / project','Shared coordination_item shell','blue','CONTAINER')+node(440,116,250,'Scheduled event','Source start or selected occurrence','blue','SOURCE')+node(813,116,238,'Preparation task','Open task with due anchor','blue','TARGET')+
      line(440,160,316,160)+tag(376,147,'part_of')+line(813,160,692,160)+tag(750,147,'part_of')+
      note(64,240,'depends_on expresses a dependency. part_of expresses structure. Temporal bindings express derivation.')+
      boundary(37,307,501,289,'02 / SNAPSHOT · RESOLVE ONCE')+boundary(568,307,514,289,'03 / FOLLOW_SOURCE · RECONCILE EXPLICITLY','teal')+
      node(63,364,449,'Event moved: 14:00 → 16:00','Task originally derived at source − 2 elapsed hours','blue','SOURCE CHANGE',85)+
      line(286,449,286,487)+node(63,487,449,'Task stays due at 12:00','Snapshot remains derivation evidence','blue','UNCHANGED TARGET',85)+
      node(594,364,462,'Binding becomes stale','Bound due-time reminders become non-actionable','amber','FRESHNESS CHECK',85)+line(825,449,825,487,'teal')+
      node(594,487,462,'Reconcile → task due at 14:00','One binding · new revision · versioned task + work repair','teal','EXPLICIT COMMAND',85)+
      note(53,644,'Elapsed offsets are calculated after UTC resolution. Source mutation does not fan out unbounded task writes.')+note(53,668,'Terminal, unresolved, diverged, or inactive-relationship cases produce explicit reconciliation outcomes.');
  }
  function operations() {
    return boundary(38,42,1045,570,'HOST / SUPERVISOR OWNS RESTART, CAPACITY, AND EXTERNAL LOG ROTATION')+
      node(65,104,277,'Command / worker launch','Exact schema + runtime contracts','blue','BOUNDED PREFLIGHT')+node(423,104,277,'Tickerd admission','Audited package + descriptor','teal','COMPATIBILITY')+node(783,104,270,'Budget validation','Invalid config → readiness false','amber','RESOURCE LIMITS')+
      line(342,148,422,148)+line(700,148,782,148,'teal')+edge('M918 192V251H700','teal')+
      node(423,223,277,'Pre-cycle storage gate','Disk / WAL facts + durability latch','amber','BEFORE EFFECTS')+
      edge('M423 268H342','amber')+node(65,223,277,'Safety stop','No new external effects','amber','FAIL CLOSED')+
      edge('M561 311V363','teal')+node(423,363,277,'Tickerd cycle','Discover → reconcile → process','teal','BOUNDED EXECUTION')+
      edge('M700 407H783','teal')+node(783,363,270,'Attempt + adapter','Persist before external contact','teal','ACTIVE MODE')+
      edge('M918 451V529H700','amber')+node(423,497,277,'SQLite durability latch','I/O or disk-full failure is monotonic','amber','MID-CYCLE CONTAINMENT')+
      edge('M423 541H372V337H208V311','amber',true)+tag(372,460,'latched stop','amber')+
      node(65,497,277,'Health & event evidence','Bounded files · readiness · reasons','blue','OPERATOR READBACK')+
      note(65,659,'observe_only: inspect eligible work, no send attempts. suspended: runtime mode owned by Tickerd.')+
      note(65,684,'Recovery: preserve evidence → fix cause → explicit verification → supervised restart. No auto-deletion.');
  }
  const diagrams=[
    {id:'01',slug:'authority',short:'Context & authority',title:'One ledger. A connected world.',type:'SYSTEM CONTEXT',draw:context,h:610,summary:'Where Spine sits, who it serves, and which component owns each kind of truth.',desc:'Agents submit versioned commands to Spine. Spine owns canonical truth; views consume it. Tickerd receives eligible work and owns cadence. Adapters execute after attempt persistence and return outcome evidence. Governance is a configured boundary role. Calendar and map integrations illustrate the architecture, not shipped adapters.',steps:['Agents and operator tools propose changes through versioned commands; read models expose committed truth.','Spine determines eligible work. Tickerd owns cadence and runtime modes. Adapters perform external contact after attempt admission.','Outcomes return as durable evidence. Vendor state and rendered views remain projections.'],invariant:'Every external effect must have a persisted attempt. Governance is shown as a protocol role; the configured implementation and approval requirements belong to deployment.',sources:['specs/architecture.md','specs/overview.md','specs/decisions/0003-role-based-governance-boundary.md'],boundary:'Architecture view. Calendar/map targets and governance integrations are illustrative roles, not a claim that all adapters ship today.'},
    {id:'02',slug:'runtime',short:'Containers & runtime',title:'From command to canonical truth.',type:'CONTAINERS & COMPONENTS',draw:containers,h:650,summary:'Processes, service boundaries, pure rules, persistence, and the worker bridge.',desc:'The CLI dispatches commands to services using deterministic core rules and SQLite persistence. Read services compute projections. A worker process bridges Tickerd to Spine eligibility and attempt-gated adapters. These are code and process boundaries, not separate microservices.',steps:['The CLI resolves a public command. Services compose validation, domain rules, persistence, and receipts.','The pure core interprets time, recurrence, and identity. SQLite owns persistence and transactional evidence.','The worker admits Tickerd, maps Spine work, and invokes adapters through attempt accounting.'],invariant:'This is a mixed process/component view of the local Python application. A module boundary does not imply a separately deployed service.',sources:['specs/architecture.md','pyproject.toml','src/spine/runtime/worker.py','src/spine/services/attempts.py']},
    {id:'03',slug:'ontology',short:'Canonical ontology',title:'The anatomy of a durable plan.',type:'LOGICAL ENTITY–RELATIONSHIP MAP',draw:erd,w:1344,h:1040,summary:'Identity, immutable versions, time, policy, provenance, work, and evidence.',desc:'Coordination items have one-to-many immutable versions. Event and task versions have matching detail records and supporting locations, roles, and policies. Recurrence produces occurrence provenance. Policies and provenance authorize work, which records attempts and immutable notification rendering evidence. The map groups supporting tables and selected logical relationships.',steps:['Start at coordination_items and follow its current_version pointer into immutable canonical facts.','Follow the right side from recurrence and policy through provenance to work and side_effect_attempts.','Use the supporting tables to keep subject identity, delivery target, location, time, and audit evidence distinct.'],invariant:'This selected logical ERD is an orientation map. The schema, migrations, and contracts define exact columns, cardinalities, and constraints; grouped links are not an exhaustive foreign-key inventory.',sources:['specs/ontology.md','src/spine/ledger/schema.sql','src/spine/ledger/migrations/','specs/notification-profiles.md']},
    {id:'04',slug:'versions',short:'Versions & lifecycles',title:'Change the plan. Keep the past.',type:'VERSION LINEAGE & STATE MACHINES',draw:lifecycle,h:620,summary:'Immutable history, atomic current pointers, and distinct item lifecycles.',desc:'A canonical edit creates the next immutable item version with complete supporting sets and atomically updates the current pointer. The shell can move from active to archived. Events move from scheduled to cancelled. Tasks move from open to done or cancelled; these profile states are terminal in the MVP.',steps:['Validate target_version against current truth before preparing the next version.','Copy forward complete supporting sets, apply changes, and atomically switch the current pointer.','Keep shell archiving separate from event and task state transitions. Historical records are preserved.'],invariant:'Events and tasks share identity and history while retaining different lifecycle rules. No stale-version mutation may partially commit.',sources:['specs/ontology.md','src/spine/models/enums.py','specs/agent-command-contract.md']},
    {id:'05',slug:'atomic-create',short:'Atomic commands',title:'One request. One complete commit.',type:'SEQUENCE / SCHEDULE.CREATE',draw:()=>sequence('create'),h:750,summary:'How creation validates, commits, replays, and proves what happened.',desc:'An operator submits schedule.create. The service checks receipt replay, validates the complete request, then commits canonical item, time, policy, recurrence, optional provenance and work, audit, and a single receipt atomically. A repeat command replays the stored result. schedule.show reads committed truth and lifecycle evidence.',steps:['A compatible command replay returns its original result; a conflicting reuse is rejected.','One transaction commits the full requested schedule bundle, audit evidence, and deterministic receipt. Any child failure rolls back all writes.','Read back the item and lifecycle evidence with schedule.show. Delivery remains not_attempted after authoring.'],invariant:'Idempotency is a command identity and evidence contract. It does not turn authoring into delivery or promise exactly-once behavior from an external provider.',sources:['specs/schedule-create.md','specs/schedule-show.md','specs/agent-command-contract.md']},
    {id:'06',slug:'reconciliation',short:'Mutation & reconciliation',title:'When plans move, work follows.',type:'SEQUENCE / UPDATE & CANCEL',draw:()=>sequence('update'),h:750,summary:'Successor truth, stale-work classification, and preserved attempt history.',desc:'Update and cancel validate replay and expected version. Successor truth drives work classification: stale eligible never-attempted work is cancelled, current work is retained, and attempted or terminal stale work is protected history. Bounded replacement work is optional on update. All truth, reconciliation, audit, and receipt changes commit together.',steps:['Resolve the requested successor truth against the expected item version.','Classify affected work as cancelled, retained, or protected stale. Newly created replacement IDs form a separate set.','Commit truth and work changes together. A future attempt still has to pass the current freshness gate.'],invariant:'Never-attempted stale work may be cancelled. In-progress, retry, and terminal work remains evidence. Protected stale work is not fresh authorization to send.',sources:['specs/schedule-operations.md','specs/notifications.md','specs/relative-temporal-bindings.md']},
    {id:'07',slug:'delivery',short:'Notifications & effects',title:'Intent becomes work. Work leaves evidence.',type:'NOTIFICATION & ATTEMPT LIFECYCLE',draw:notifications,h:680,summary:'The complete path from authored reminders to a verified adapter outcome.',desc:'Canonical policies expand into virtual opportunities and materialize as durable work. At attempt start the worker checks eligibility and freshness, persists rendering and request evidence, then invokes the adapter. Success, failure, rejection, and retry posture are recorded. Retry belongs to the same work, not a new notification opportunity.',steps:['Authored, expanded, and materialized describe three different scheduling facts. None proves an external send.','After admission, persist the started attempt and ordinary reminder body before invoking a provider.','Interpret the terminal attempt outcome. Retry state belongs to the original work; reminder cadence creates distinct work.'],invariant:'No notification policy or virtual opportunity may directly invoke an adapter. The single generic ledger is side_effect_attempts.',sources:['specs/notifications.md','specs/notification-rendering.md','src/spine/services/attempts.py','src/spine/models/enums.py']},
    {id:'08',slug:'recurrence',short:'Time & provenance',title:'Make time explicit. Make replay exact.',type:'TEMPORAL DATA FLOW',draw:recurrence,h:750,summary:'Pinned time facts, recurrence identity, bounded expansion, and provenance.',desc:'Explicit local or UTC time, immutable recurrence rules, and pinned timezone data feed bounded occurrence expansion. Current persisted provenance authorizes occurrence-bound notification opportunities. Revision changes require fresh downstream evidence. Historical UTC values are preserved.',steps:['Resolve local date/instant intent against the pinned timezone database and explicit resolution policy.','Expand a bounded recurrence range, preserving revision lineage and stable occurrence keys.','Regenerate current notification-consumer provenance before recurrence-bound opportunity expansion and materialization.'],invariant:'Item recurrence, notification cadence, and adapter retry are separate clocks. Historical trigger and attempt timestamps must never be silently recomputed.',sources:['specs/recurrence.md','specs/notifications.md','specs/schedule-create.md']},
    {id:'09',slug:'bindings',short:'Relationships & bindings',title:'Connected plans, explicit consequences.',type:'DOMAIN GRAPH & CHANGE SCENARIO',draw:bindings,h:705,summary:'Structural relationships, dependencies, and snapshot versus follow-source timing.',desc:'A preparation task can be part of an event in a trip. Snapshot timing stays fixed after the source moves. Follow-source timing becomes stale and blocks due-time reminder actionability until an explicit bounded reconciliation refreshes the binding and target task. The example uses a two-hour elapsed offset.',steps:['Use part_of for containment and depends_on for dependency. An ordinary relationship alone does not move another item’s time.','Snapshot resolves once. Follow-source records a governing derivation that becomes stale when source or target facts diverge.','Reconcile one binding explicitly; refresh revision evidence, version the target when needed, and reconcile bounded notification work.'],invariant:'A stale follow-source binding makes bound due-time notification work non-actionable. Reads do not silently mutate tasks, and source changes do not trigger unbounded fan-out.',sources:['specs/relative-temporal-bindings.md','specs/ontology.md']},
    {id:'10',slug:'operations',short:'Operations & containment',title:'Protect truth, even under pressure.',type:'DEPLOYMENT & FAILURE CONTAINMENT',draw:operations,h:720,summary:'Runtime admission, bounded cycles, storage gates, durability failure, and recovery.',desc:'Host-supervised commands and workers perform bounded ledger, contract, Tickerd, and budget admission. A pre-cycle storage gate stops effects under pressure. An active cycle persists attempts before adapters. Mid-cycle durability failure latches containment. The host owns recovery and restart; health and bounded event evidence support diagnosis.',steps:['Admit the exact runtime dependencies and ledger structure before discovering or processing work.','Check storage safety before the cycle; a disk-full or I/O durability failure latches a stop on further effects.','Preserve the ledger and evidence, repair the cause, verify deliberately, and restart through the host supervisor.'],invariant:'Deep verification is an explicit operator action. Storage pressure grants no authority to delete canonical evidence. The full resilience spec also contains future qualification targets.',sources:['specs/compatibility.md','specs/operational-resilience.md','src/spine/runtime/storage_safety.py','docs/OPENCLAW_DEPLOYMENT_RUNBOOK.md']}
  ];
  window.SpineDiagrams = {all:diagrams,render(id){const d=diagrams.find(d=>d.id===id)||diagrams[0];return wrap(d.draw(),{w:d.w||1120,h:d.h,title:d.title,desc:d.desc,id:d.id});},escape:esc};
})();
