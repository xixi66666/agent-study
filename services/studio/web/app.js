import { clearMotion, mountMotion } from './motion.js';

const $ = (selector) => document.querySelector(selector);
const h = (value = '') => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const clone = (value) => JSON.parse(JSON.stringify(value));
const media = (path, download = false) => path ? '/media/' + path.split('/').map(encodeURIComponent).join('/') + (download ? '?download=1' : '') : '';
const time = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2,'0')}:${String(Math.floor(seconds % 60)).padStart(2,'0')}`;
const date = value => new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
const state = {projects:[], assets:[], jobs:[], runs:[], project:null, run:null, view:'overview', selected:0, dirty:false, saving:false, saveError:'', previewMode:'video', captions:true, undo:[], health:null, drag:null, polling:false, autosave:null, toastTimer:null, projectQuery:'', projectFilter:'all', projectSort:'recent', workspaceUpdated:0};
const workViews = ['story','storyboard','audio','export','settings'];
const globalViews = ['overview','projects','assets','jobs','runs','engine'];
const inWork = () => workViews.includes(state.view);
const stageNames = {draft:'待制作',rendering:'制作中',visual_ready:'画面就绪',audio_ready:'配音就绪',complete:'成片就绪',attention:'需要处理',changed:'草稿待更新'};
const stageColor = stage => stage==='complete'?'green':stage==='attention'?'red':stage==='rendering'||stage==='changed'?'orange':'';
const icons = {
  home:'<path d="m3 10 9-7 9 7v11h-7v-7h-4v7H3Z"/>',
  film:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  board:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  book:'<path d="M12 6c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z"/><path d="M12 6v15"/>',
  mic:'<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  export:'<path d="M12 3v12M8 7l4-4 4 4M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
  image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5-10 11"/>',
  queue:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',
  archive:'<rect x="3" y="3" width="18" height="5" rx="1"/><path d="M5 8v12h14V8M9 12h6"/>',
  nodes:'<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M9 6h8v9M6 9v9h9"/>',
  settings:'<path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', save:'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
  play:'<path d="m8 4 12 8-12 8Z"/>', pause:'<path d="M8 5v14M16 5v14"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M18 18a8 8 0 0 1-14-6"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  up:'<path d="m6 14 6-6 6 6"/>',down:'<path d="m6 10 6 6 6-6"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',
  check:'<path d="m5 12 4 4L19 6"/>',download:'<path d="M12 3v12M7 10l5 5 5-5M4 17v4h16v-4"/>',
  upload:'<path d="M12 16V4M7 9l5-5 5 5M4 17v4h16v-4"/>',
  undo:'<path d="M3 10h12a6 6 0 0 1 0 12M3 10l5-5M3 10l5 5"/>',
  camera:'<path d="M8 5 9 3h6l1 2h5v15H3V5Z"/><circle cx="12" cy="12" r="4"/>',
  arrow:'<path d="M4 12h16M14 6l6 6-6 6"/>', external:'<path d="M14 3h7v7M10 14 21 3M10 3H3v18h18v-7"/>',
  volume:'<path d="M11 4 6 9H3v6h3l5 5ZM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', stop:'<rect x="6" y="6" width="12" height="12" rx="1"/>',
};
const icon = name => `<svg aria-hidden="true" viewBox="0 0 24 24">${icons[name] || icons.film}</svg>`;
const button = (label, action, name, classes='', extra='') => `<button class="${classes}" data-action="${action}" ${extra}>${name ? icon(name) : ''}${label}</button>`;
const iconButton = (label, action, name, extra='') => `<button class="icon-button ghost" data-action="${action}" aria-label="${h(label)}" title="${h(label)}" ${extra}>${icon(name)}</button>`;
const activeJob = () => state.jobs.find(job => ['queued','running','stopping'].includes(job.status));
const p = () => state.project;
const shot = () => p().story.shots[state.selected];
const duration = () => p().video.output_frames_per_clip / p().video.fps;
const shotMedia = index => state.run?.shots[index] || {};
const imageFor = index => shotMedia(index).image || p().story.shots[index]?.start_image;
const names = () => Object.keys(p().story.speakers || {});
const busy = () => activeJob() ? 'disabled' : '';
const cameraMode = () => p()?.video.generation_mode === 'fun_camera';
const visualBusy = () => activeJob() || cameraMode() && !state.health?.fun_camera?.ready ? 'disabled' : '';
const cameraLabels = [['Static','固定'],['Pan Up','向上移动'],['Pan Down','向下移动'],['Pan Left','向左移动'],['Pan Right','向右移动'],['Zoom In','推近'],['Zoom Out','拉远'],['Anti Clockwise (ACW)','逆时针旋转'],['ClockWise (CW)','顺时针旋转']];
state.randomizeSeed = true;
const statusText = status => ({pending:'未生成',submitting:'提交中',running:'生成中',success:'已完成',failed:'失败',cancelled:'已停止',complete:'已完成',partial:'部分完成',clips_ready:'画面就绪',interrupted:'待恢复',stopped:'已停止',stopping:'正在停止',queued:'等待执行',generating:'生成中'})[status] || status;
const actionText = action => ({film:'生成成片',generate:'生成画面',shot:'重做单镜头',from_shot:'从此镜头重做',voice:'生成配音字幕',compose:'合成成片',audition:'试听对白'})[action] || action;

async function api(path, method='GET', body) {
  const headers = method==='GET' ? {} : {'X-AIMedia-Client':'studio'};
  if (body && !(body instanceof FormData)) headers['Content-Type']='application/json';
  const response = await fetch(path,{method,headers,body:body ? body instanceof FormData ? body : JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败，请重试');
  return result;
}

function toast(message, error=false, undo=false) {
  clearTimeout(state.toastTimer);
  $('#toast').innerHTML=`<div class="toast ${error?'error':''}">${h(message)}${undo?'<button data-action="undo">撤销</button>':''}</div>`;
  state.toastTimer=setTimeout(()=>$('#toast').innerHTML='',error?7000:4000);
}

function field(path,label,value,{type='text',rows,help='',className='',min,max,step}={}) {
  const id='field-'+path.replaceAll('.','-');
  const attributes=`id="${h(id)}" data-bind="${h(path)}" ${type==='number'?'data-number="1"':''}`;
  return `<div class="field"><label for="${h(id)}">${h(label)}</label>${rows?`<textarea ${attributes} rows="${rows}" class="${className}">${h(value)}</textarea>`:`<input ${attributes} type="${type}" value="${h(value)}" ${min!==undefined?`min="${min}"`:''} ${max!==undefined?`max="${max}"`:''} ${step?`step="${step}"`:''}>`}${help?`<div class="field-hint">${help}</div>`:''}</div>`;
}

function selectField(path,label,value,options,help='') {
  return `<div class="field"><label for="select-${h(path)}">${h(label)}</label><select id="select-${h(path)}" data-bind="${h(path)}" ${typeof value==='number'?'data-number="1"':''}>${options.map(option=>{const [v,l]=Array.isArray(option)?option:[option,option];return `<option value="${h(v)}" ${v===value?'selected':''}>${h(l)}</option>`;}).join('')}</select>${help?`<div class="field-hint">${help}</div>`:''}</div>`;
}

function needsVisual(index) {
  if (!state.run?.story.shots[index] || shotMedia(index).status !== 'success') return true;
  const old = state.run.story.shots[index], current = p().story.shots[index];
  if ((p().video.generation_mode||'wan22') !== (state.run.video.generation_mode||'wan22')) return true;
  if (cameraMode() && ((old.camera_motion||'Static') !== (current.camera_motion||'Static') || (old.camera_speed??1) !== (current.camera_speed??1))) return true;
  if (p().video.generation_mode==='h3' && JSON.stringify(old.dialogue||[])!==JSON.stringify(current.dialogue||[])) return true;
  if (JSON.stringify(old.reference_shots||[])!==JSON.stringify(current.reference_shots||[])) return true;
  if (['prompt','description','camera','start_image'].some(key => (old[key]||'') !== (current[key]||''))) return true;
  if ((old.seed ?? state.run.video.seed+index+1)!==(current.seed ?? p().video.seed+index+1)) return true;
  if (['style','negative_prompt'].some(key=>p().story[key]!==state.run.story[key])) return true;
  const appearance = story => Object.fromEntries(Object.entries(story.speakers||{}).filter(([,role])=>role.appearance).map(([name,role])=>[name,role.appearance]));
  if(JSON.stringify(appearance(p().story))!==JSON.stringify(appearance(state.run.story)))return true;
  return Object.keys(p().video).filter(key=>!['comfyui_url','clip_timeout_seconds','output_frames_per_clip','seed','generation_mode',...(!cameraMode()?['clip_vision']:[])].includes(key)).some(key=>p().video[key]!==state.run.video[key]);
}

function cameraStatusText() {
  const status=state.health?.fun_camera;
  if(status?.ready)return '相机模型已就绪 · 来自魔搭 ModelScope';
  if(status?.download_status==='downloading'&&status.total_bytes)return `模型下载中 · ${(100*status.downloaded_bytes/status.total_bytes).toFixed(0)}% · 完成后可生成`;
  return status?.missing?.length?'相机模型未就绪 · 请检查下载进度':'正在检查相机模型';
}

function generationControls(withCamera=false) {
  const mode=p().video.generation_mode||'wan22';
  return `<div class="generation-controls"><div class="field"><label for="generation-mode">生成模型</label><select id="generation-mode"><option value="h3" ${mode==='h3'?'selected':''}>MiniMax H3 · 写实视频与原生音频</option>${mode!=='h3'?`<option value="${h(mode)}" selected>历史 Wan 配置 · 模型已移除</option>`:''}</select></div><div class="info-box">H3 使用文字设计运镜，原生生成对白与立体声。人物参考图用于保持身份；镜头角度与动作可逐段修改。${withCamera&&shot().reference_shots?.length?`<p>人物参考：镜头 ${shot().reference_shots.join('、')} 的末帧。</p>`:''}</div></div>`;
}

function navItem(view,label,name,count) {
  return `<button class="nav-button ${state.view===view?'active':''}" data-action="navigate" data-view="${view}" ${state.view===view?'aria-current="page"':''}>${icon(name)}${label}${count!==undefined?`<span class="nav-count">${count}</span>`:''}</button>`;
}

function shell() {
  clearMotion();
  const work=inWork();
  const navigation=work?`<div class="nav-group"><div class="nav-label">当前作品 · 制作台</div>${navItem('story','剧本与角色','book')}${navItem('storyboard','分镜与画面','board')}${navItem('audio','配音与字幕','mic')}${navItem('export','合成与导出','export')}${navItem('settings','作品生成设置','settings')}</div><div class="nav-group secondary-nav"><div class="nav-label">工作空间</div>${navItem('overview','返回总控台','home')}${navItem('jobs','全局任务','queue',activeJob()?1:0)}${navItem('engine','ComfyUI','nodes')}</div>`:`<div class="nav-group"><div class="nav-label">工作空间</div>${navItem('overview','总览','home')}${navItem('projects','作品管理','board',state.projects.length)}${navItem('jobs','任务中心','queue',activeJob()?1:0)}${navItem('assets','共享素材','image')}${navItem('runs','成片库','archive')}</div><div class="nav-group secondary-nav"><div class="nav-label">基础服务</div>${navItem('engine','ComfyUI','nodes')}</div>`;
  const header=work?`<div class="project-picker">${iconButton('返回作品管理','navigate','home','data-view="projects"')}<select id="project-picker" aria-label="选择作品">${state.projects.map(project=>`<option value="${project.id}" ${project.id===p().id?'selected':''}>${h(project.title)}</option>`).join('')}</select>${iconButton('复制当前作品','copy-project','copy')}<span class="save-state" id="save-state">已保存</span></div><div class="top-actions">${iconButton('撤销结构修改','undo','undo')}${iconButton('查看草稿历史','revisions','clock')}${button('保存','save','save')}${button('生成成片','job-film','play','primary',visualBusy())}</div>`:`<div class="workspace-label"><span class="status-dot online"></span><strong>AIMedia 工作空间</strong><span class="workspace-label-note">本地视频生产</span></div><div class="top-actions"><span class="pill" id="mimo-status">MiMo · 检查中</span>${iconButton('刷新工作空间','refresh-workspace','refresh')}${button('新建作品','new-project','plus','primary')}</div>`;
  $('#app').innerHTML=`<div class="app-shell ${work?'work-shell':'global-shell'}"><aside class="sidebar"><div class="brand"><div class="brand-logo">A</div><div><strong>AIMedia</strong><small>WORKSPACE</small></div></div>${work?button('返回总控台','navigate','home','new-project','data-view="overview"'):button('新建作品','new-project','plus','new-project')}${navigation}<div class="sidebar-bottom"><div class="engine-status" id="engine-status"><span class="status-dot"></span>检查本地引擎…</div><div class="sidebar-note">画面在本机生成<br>作品与素材独立归档</div>${button('使用说明','help','book','ghost small')}</div></aside><div class="workspace"><header class="topbar">${header}</header><main class="page" id="main" tabindex="-1"></main></div></div>`;
  renderPage(); updateSaveState(); updateHealth();
}

function pageHeader(eyebrow,title,description,actions='') {
  return `<div class="page-header"><div><h1>${h(title)}</h1><p>${description}</p></div><div class="header-side">${actions}</div></div>`;
}

function tabs() {
  return `<nav class="tabs" aria-label="制作阶段">${[['story','剧本与角色'],['storyboard','分镜与画面'],['audio','配音与字幕'],['export','合成与导出']].map(([view,label])=>`<button class="tab ${state.view===view?'active':''}" data-action="navigate" data-view="${view}" ${state.view===view?'aria-current="page"':''}>${label}</button>`).join('')}</nav>`;
}

function renderPage(animate=true) {
  clearMotion();
  const views = {overview:overviewPage,projects:projectsPage,story:storyPage,storyboard:storyboardPage,audio:audioPage,export:exportPage,assets:assetsPage,jobs:jobsPage,runs:runsPage,engine:enginePage,settings:settingsPage};
  $('#main').innerHTML=(views[state.view] || overviewPage)();
  bindPreview(); updateJobBanner();
  mountMotion($('#main'),animate);
  const carousel=$('#film-carousel');
  if(carousel){carousel.addEventListener('scroll',updateFilmControls,{passive:true});updateFilmControls();}
}

function updateFilmControls() {
  const carousel=$('#film-carousel');
  if(!carousel)return;
  $('[data-action="films-prev"]').disabled=carousel.scrollLeft<2;
  $('[data-action="films-next"]').disabled=carousel.scrollLeft>=carousel.scrollWidth-carousel.clientWidth-2;
}
window.addEventListener('resize',updateFilmControls);

function projectCard(project) {
  return `<article class="panel project-card"><button class="project-cover" data-action="open-project" data-project="${project.id}" aria-label="进入制作台：${h(project.title)}">${project.cover?`<img src="${media(project.cover)}" alt="${h(project.title)}的画面" loading="lazy">`:`<span class="cover-placeholder">${icon('film')}<span>从第一个镜头开始</span></span>`}<span class="pill ${stageColor(project.stage)}">${stageNames[project.stage]||'待制作'}</span><span class="cover-duration">${time(project.duration)}</span></button><div class="panel-body"><h3>${h(project.title)}</h3><p class="project-synopsis">${h(project.synopsis||'还没有故事梗概，进入制作台开始编写。')}</p><div class="project-facts"><span>${project.shots} 个镜头</span><span>${project.versions||0} 个版本</span><span>${project.audio_ready?'配音已就绪':'待配音'}</span></div><div class="project-progress"><span>画面 ${project.completed_shots||0}/${project.shots}</span><div class="progress"><div style="width:${Math.min(100,(project.completed_shots||0)/project.shots*100)}%"></div></div></div><div class="project-card-footer"><small>${date(project.updated_at)} 更新</small><div>${project.final?iconButton('预览成片：'+project.title,'view-run','play',`data-run="${project.run_id}"`):''}${button('进入制作台','open-project','arrow','small',`data-project="${project.id}"`)}</div></div></div></article>`;
}

function projectResults() {
  const query=state.projectQuery.toLocaleLowerCase().trim();
  const list=state.projects.filter(project=>(!query||(project.title+' '+project.synopsis).toLocaleLowerCase().includes(query))&&(state.projectFilter==='all'||project.stage===state.projectFilter));
  if(state.projectSort==='title')list.sort((a,b)=>a.title.localeCompare(b.title,'zh-CN'));
  else if(state.projectSort==='duration')list.sort((a,b)=>b.duration-a.duration);
  return list.length?list.map(projectCard).join(''):`<div class="panel empty-state"><strong>${state.projects.length?'没有符合条件的作品':'还没有作品'}</strong><span>${state.projects.length?'修改搜索词或选择其他制作状态。':'创建第一部作品，开始编写剧本。'}</span>${button(state.projects.length?'清除筛选':'新建作品',state.projects.length?'clear-project-filter':'new-project','plus','small')}</div>`;
}

function projectsPage() {
  return pageHeader('PROJECT LIBRARY','作品管理','在这里管理所有视频作品，选择一部进入它的制作台。')+`<div class="project-toolbar"><div class="field"><label for="project-search">搜索作品</label><input id="project-search" type="search" placeholder="搜索标题或故事内容" value="${h(state.projectQuery)}"></div><div class="field"><label for="project-filter">制作状态</label><select id="project-filter"><option value="all">全部作品</option>${Object.entries(stageNames).map(([key,label])=>`<option value="${key}" ${state.projectFilter===key?'selected':''}>${label}</option>`).join('')}</select></div><div class="field"><label for="project-sort">排序</label><select id="project-sort">${[['recent','最近更新'],['title','作品名称'],['duration','计划时长']].map(([key,label])=>`<option value="${key}" ${state.projectSort===key?'selected':''}>${label}</option>`).join('')}</select></div></div><div class="project-grid" id="project-results">${projectResults()}</div>`;
}

function overviewPage() {
  const count=stage=>state.projects.filter(project=>project.stage===stage).length;
  const active=state.jobs.filter(job=>['queued','running','stopping'].includes(job.status));
  const attention=state.jobs.filter(job=>['failed','interrupted'].includes(job.status));
  const films=state.runs.filter(run=>run.final);
  const metrics=[['作品总数',state.projects.length,'projects','board'],['制作中的作品',count('rendering'),'rendering','play'],['需要处理的作品',count('attention'),'attention','queue'],['成片版本',films.length,'runs','film']];
  const nameFor=job=>state.projects.find(project=>project.id===job.project_id)?.title||job.project_id;
  const featured=state.projects.find(project=>project.title==='小鱼饼失踪案')||state.projects.find(project=>project.cover);
  const titles=state.projects.filter(project=>project.cover).slice(0,4);
  const ribbon=titles.map(project=>`<span>${icon('film')}${h(project.title)}</span>`).join('');
  return `<section class="workspace-hero">
    <div class="hero-date">${new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}<span>你的创作空间</span></div>
    <h1>给灵感一点空间，<br>让故事<span class="inline-scene"><img src="${media('prompts/assets/cat_biscuit_opening.png')}" alt="原创小猫动画画面"></span>慢慢发生。</h1>
    <p class="hero-description">从剧本、分镜到配音与成片，每一个创作步骤都在这里。</p>
    <div class="hero-actions">${button('开始一个新故事','new-project','plus','primary')}${button('继续我的作品','navigate','arrow','','data-view="projects"')}</div>
    ${ribbon?`<div class="story-ribbon" aria-label="已有作品"><div class="ribbon-track"><div>${ribbon}</div><div aria-hidden="true">${ribbon}</div></div></div>`:''}
  </section>
  <div class="overview-metrics">${metrics.map(([label,value,target,name])=>`<button class="panel overview-metric" data-action="${['projects','runs'].includes(target)?'navigate':'filter-projects'}" ${['projects','runs'].includes(target)?`data-view="${target}"`:`data-filter="${target}"`}><span>${icon(name)}${label}</span><strong>${value}<small>${target==='runs'?'个版本':'部'}</small></strong><small>查看${label}${icon('arrow')}</small></button>`).join('')}</div>
  <div class="overview-columns"><section class="panel"><div class="panel-head"><h3>制作进程</h3>${button('查看全部作品','navigate','arrow','ghost small','data-view="projects"')}</div><div class="pipeline-grid">${[['draft','待制作'],['changed','待更新'],['visual_ready','画面就绪'],['audio_ready','配音就绪'],['complete','成片就绪']].map(([key,label])=>`<button class="pipeline-stage" data-action="filter-projects" data-filter="${key}"><strong>${count(key)}</strong><span>${label}</span></button>`).join('')}</div><div class="overview-note">草稿独立保存，生成的新版本会自动归档。</div></section><section class="panel service-panel"><div class="panel-head"><h3>引擎与服务</h3>${button('管理引擎','navigate','nodes','ghost small','data-view="engine"')}</div><div class="panel-body"><div class="service-line"><span><span id="overview-engine-dot" class="status-dot ${state.health?.connected?'online':'offline'}"></span>本地 ComfyUI</span><strong id="overview-engine-state">${state.health?.connected?'已连接':'未连接'}</strong></div><div class="service-line"><span>MiMo 配音</span><strong id="overview-mimo-state">${state.health?.mimo_configured?'已配置':'未配置'}</strong></div><div class="service-line"><span>共享参考素材</span>${button(state.assets.length+' 张','navigate','image','ghost small','data-view="assets"')}</div><small id="overview-device">${h(state.health?.devices?.[0]?.name||'本机画面生成 · 配音按需调用')}</small></div></section></div>
  <section class="recent-section" aria-labelledby="recent-title"><div class="recent-aside"><div class="section-heading"><div><h2 id="recent-title">故事，正在生长。</h2><p>打开最近的作品，接着上一次的灵感。</p></div></div>${featured?`<button class="featured-scene" data-action="open-project" data-project="${featured.id}" aria-label="继续制作：${h(featured.title)}"><img src="${media(featured.cover)}" alt="${h(featured.title)}的画面" loading="lazy"><span><strong>${h(featured.title)}</strong><small>进入制作台 ${icon('arrow')}</small></span></button>`:''}${button('查看全部作品','navigate','arrow','ghost','data-view="projects"')}</div><div class="recent-projects">${state.projects.slice(0,3).map(projectCard).join('')||'<div class="panel empty-state">创建第一部作品，让故事从这里开始。</div>'}</div></section>
  <div class="overview-columns overview-bottom"><section class="panel"><div class="panel-head"><h3>生产任务</h3>${button('任务中心','navigate','queue','ghost small','data-view="jobs"')}</div><div class="panel-body">${active.length?active.map(job=>`<div class="workspace-task"><div><strong>${h(nameFor(job))}</strong><p>${actionText(job.action)} · ${h(job.stage)}${job.sampling?` · ${job.sampling.value}/${job.sampling.max}`:''}</p></div>${button('进入作品','open-project','arrow','small',`data-project="${job.project_id}"`)}</div>`).join(''):`<div class="workspace-idle">${icon('check')}<div><strong>当前没有制作任务</strong><p>先整理作品，再进入制作台开始生成。</p></div></div>`}${attention.length?`<div class="attention-line">${attention.length} 个历史任务需要检查 ${button('查看任务','navigate','arrow','ghost small','data-view="jobs"')}</div>`:''}</div></section><section class="panel creation-next"><div class="panel-body"><span class="creation-symbol">${icon('book')}</span><h2>下一个故事，会是什么？</h2><p>写下想法，分镜、配音和画面都可以慢慢调整。</p>${button('新建作品','new-project','plus','primary')}</div></section></div>
  <section class="film-section" aria-labelledby="films-title"><div class="section-heading"><div><h2 id="films-title">已经完成的故事</h2><p>每一版成片，都为你保留。</p></div><div class="button-row">${iconButton('上一组成片','films-prev','up')}${iconButton('下一组成片','films-next','down')}${button('成片库','navigate','arrow','ghost small','data-view="runs"')}</div></div><div class="film-carousel" id="film-carousel" tabindex="0" aria-label="成片预览列表">${films.slice(0,8).map(run=>{const project=state.projects.find(project=>project.id===run.project_id)||state.projects.find(project=>project.run_id===run.id);return `<article class="film-slide panel">${project?.cover?`<img src="${media(project.cover)}" alt="${h(run.title)}的画面" loading="lazy">`:`<div class="film-placeholder">${icon('film')}</div>`}<div class="panel-body"><h3>${h(run.title)}</h3><p>${run.specs?`${run.specs.duration_seconds.toFixed(1)} 秒 · ${run.specs.width}×${run.specs.height} · ${run.specs.fps}fps`:'已有成片'}</p>${button('预览成片','view-run','play','small',`data-run="${run.id}"`)}</div></article>`;}).join('')||'<p class="field-hint">作品完成合成后，会自动出现在这里。</p>'}</div></section>
  <footer class="workspace-footer"><strong>AIMedia</strong><span>给每个故事，一个开始。</span>${button('使用说明','help','book','ghost small')}</footer>`;
}

async function refreshWorkspace(render=true) {
  const [data,jobs,runs]=await Promise.all([api('/api/projects'),api('/api/jobs'),api('/api/runs')]);
  state.projects=data.projects;state.assets=data.assets;state.jobs=jobs;state.runs=runs;state.workspaceUpdated=Date.now();
  if(render)renderPage();
}

async function openProject(id,view='storyboard') {
  await saveProject(false);state.view=view;await loadProject(id,true);
}

async function assetTargetOptions(id) {
  const data=await api('/api/projects/'+id);
  if($('#asset-target-project')?.value!==id)return;
  state.assetTarget=data.project;
  const select=$('#asset-target-shot');if(select)select.innerHTML=data.project.story.shots.map((item,index)=>`<option value="${index}">${String(index+1).padStart(2,'0')} · ${h(item.title)}</option>`).join('');
}

async function assignAsset(path) {
  await saveProject(false);
  openModal('将素材用于作品',`<div class="asset-assignment"><img src="${media(path)}" alt="待使用的参考图"><div><div class="field"><label for="asset-target-project">目标作品</label><select id="asset-target-project">${state.projects.map(project=>`<option value="${project.id}">${h(project.title)}</option>`).join('')}</select></div><div class="field"><label for="asset-target-shot">目标分镜</label><select id="asset-target-shot" aria-label="目标分镜"></select></div><p class="field-hint">图片将成为指定镜头的起始参考。再次生成后应用到视频画面。</p></div></div>`,button('保存到这个分镜','save-asset-target','image','primary',`data-path="${h(path)}"`));
  await assetTargetOptions($('#asset-target-project').value);
}

function storyPage() {
  const story=p().story;
  return pageHeader('STORY & CHARACTERS','让故事先发生','先确定剧情和角色，再把故事拆成可以逐段调整的镜头。',button('自动编剧与分镜','plan-open','book','primary')+button('导入分镜','import','upload','small')+button('导出草稿','export-json','download','small'))+tabs()+`<div class="story-summary"><div class="metric"><strong>${story.shots.length}<small>个分镜</small></strong></div><div class="metric"><strong>${(duration()*story.shots.length).toFixed(0)}<small>秒计划时长</small></strong></div><div class="metric"><strong>${names().length}<small>个角色</small></strong></div></div><div class="wide-grid"><div class="stack"><section class="panel story-panel"><div class="panel-head"><h3>故事剧本</h3><span class="pill green">草稿可随时修改</span></div><div class="panel-body">${field('story.title','作品标题',story.title)}${field('story.synopsis','故事梗概',story.synopsis,{rows:5,help:'在这里梳理起因、转折和结尾。具体镜头动作在分镜中编辑。'})}</div></section><section class="panel"><div class="panel-head"><h3>角色设定</h3>${button('添加角色','add-role','plus','small')}</div><div class="panel-body"><div class="role-grid">${roleCards()}</div>${!names().length?'<p class="field-hint">可以创作无对白视频，也可以添加角色来设置配音。</p>':''}</div></section><section class="panel story-panel"><div class="panel-head"><h3>统一视觉风格</h3><small>作用于全部镜头</small></div><div class="panel-body">${field('story.style','画面风格与角色一致性',story.style,{rows:6,className:'prompt',help:'描述画风、场景、角色外观和整体构图。修改后，所有镜头都需要重新生成。'})}${field('story.negative_prompt','避免出现的内容',story.negative_prompt,{rows:3,className:'prompt'})}</div></section></div>${previewPanel()}</div><div id="job-banner"></div>`;
}

function roleCards() {
  return names().map(name=>{const role=p().story.speakers[name];return `<article class="role-card"><div class="role-header"><div class="role-avatar">${h(name[0])}</div><input value="${h(name)}" data-role-name="${h(name)}" aria-label="角色名称">${iconButton('移除角色','remove-role','trash',`data-role="${h(name)}"`)}</div><div class="field"><label>外观设定</label><textarea rows="3" data-role="${h(name)}" data-role-field="appearance" aria-label="${h(name)}的外观设定" placeholder="例如：橘色虎斑小猫，戴青绿色围巾">${h(role.appearance||'')}</textarea><div class="field-hint">外观与全局风格一同提交给视频模型。</div></div><div class="field"><label>${p().video.generation_mode==='h3'?'备用 MiMo 配音音色':'配音音色'}</label><input data-role="${h(name)}" data-role-field="voice" value="${h(role.voice)}" list="voice-presets" aria-label="${h(name)}的配音音色"></div><div class="field"><label>MiMo 朗读风格</label><textarea rows="4" data-role="${h(name)}" data-role-field="style" aria-label="${h(name)}的朗读风格">${h(role.style)}</textarea></div></article>`;}).join('')+'<datalist id="voice-presets"><option value="苏打"><option value="茉莉"></datalist>';
}

function shotList() {
  return `<section class="panel shot-panel"><div class="panel-head"><h3>分镜列表</h3><small>${p().story.shots.length} 个</small></div><div class="shot-list" role="list">${p().story.shots.map((s,index)=>`<div class="shot-card ${state.selected===index?'active':''}" role="listitem" draggable="true" data-shot="${index}" tabindex="0" aria-label="镜头 ${index+1}：${h(s.title)}"><span class="order">${String(index+1).padStart(2,'0')}</span>${imageFor(index)?`<img class="shot-thumb" src="${media(imageFor(index))}" alt="镜头 ${index+1}参考图" loading="lazy">`:`<div class="shot-thumb shot-placeholder">${icon('image')}</div>`}<div class="shot-card-text"><div class="shot-card-title">${h(s.title)}</div><div class="shot-card-meta"><span>${time(index*duration())}</span><span>·</span><span style="color:${needsVisual(index)?'var(--orange)':'var(--accent)'}">${needsVisual(index)?shotMedia(index).clip?'待更新':'待生成':'已完成'}</span></div></div></div>`).join('')}</div><div class="shot-footer">${button('添加分镜','add-shot','plus','small')}</div></section>`;
}

function dialogueItem(line,index,shotIndex=state.selected) {
  const base=`story.shots.${shotIndex}.dialogue.${index}`;
  return `<div class="dialogue-item"><div class="dialogue-head"><select data-bind="${base}.speaker" aria-label="对白角色">${names().map(name=>`<option ${name===line.speaker?'selected':''}>${h(name)}</option>`).join('')}</select><small>对白 ${index+1}</small>${iconButton('移除对白','remove-dialogue','close',`data-line="${index}" data-index="${shotIndex}"`)}</div><textarea rows="2" data-bind="${base}.text" aria-label="镜头 ${shotIndex+1}对白 ${index+1}">${h(line.text)}</textarea></div>`;
}

function storyboardPage() {
  const s=shot(),base=`story.shots.${state.selected}`;
  return pageHeader('STORYBOARD WORKSPACE','每一个镜头，都由你决定','调整提示词、替换参考图、逐段重做。当前成片会保留在历史版本中。',`<span class="pill">${p().video.width} × ${p().video.height}</span><span class="pill">${p().video.fps} FPS</span><span class="pill green">${(p().story.shots.length*duration()).toFixed(0)} 秒</span>`)+tabs()+`<div class="editing-grid">${shotList()}<section class="panel"><div class="panel-head"><div class="editor-heading"><span class="pill green">${String(state.selected+1).padStart(2,'0')}</span><input data-bind="${base}.title" value="${h(s.title)}" aria-label="镜头标题"></div><div class="button-row">${iconButton('向前移动','move-up','up',state.selected===0?'disabled':'')}${iconButton('向后移动','move-down','down',state.selected===p().story.shots.length-1?'disabled':'')}${iconButton('复制镜头','duplicate-shot','copy')}${iconButton('移除镜头','remove-shot','trash')}</div></div><div class="panel-body"><div class="section-label">场景与动作</div>${field(`${base}.description`,'这一段发生什么',s.description,{rows:3,help:'场景说明和镜头运动会与下方提示词一同提交给视频模型。'})}${field(`${base}.camera`,'镜头运动',s.camera)}<div class="section-label">画面生成</div>${generationControls(true)}${field(`${base}.prompt`,'画面提示词',s.prompt,{rows:6,className:'prompt',help:'建议使用英文细化动作、表情与构图；全局风格会自动附加。'})}<div class="field"><label>${p().video.generation_mode==='h3'?'人物与场景参考图':'起始参考图'} <small>可上传或从已有素材选择</small></label><div class="image-reference">${s.start_image?`<img src="${media(s.start_image)}" alt="当前镜头起始参考图"><div class="reference-info">指定参考图<small>${h(s.start_image.split('/').pop())}</small></div>`:`<div class="reference-info">${s.reference_shots?.length?'使用镜头 '+String(s.reference_shots[0]).padStart(2,'0')+' 的人物参考':state.selected>0&&p().video.use_previous_frame?'沿用上一镜头末帧':'由提示词生成画面'}<small>指定图片可以更直接地控制人物和构图</small></div>`}<div class="reference-actions">${iconButton('选择参考图','pick-reference','image')}${iconButton('上传参考图','upload-reference','upload')}${s.start_image?iconButton('移除指定参考图','clear-reference','close'):''}</div></div></div><div class="field-row">${field(`${base}.seed`,'当前镜头种子',s.seed??p().video.seed+state.selected+1,{type:'number',min:0,max:4294967295})}<div class="field"><label>镜头时段</label><input value="${time(state.selected*duration())} — ${time((state.selected+1)*duration())}" readonly aria-label="镜头时段"><small class="field-hint">每段 ${duration().toFixed(2)} 秒</small></div></div><div class="section-label">对白</div>${(s.dialogue||[]).map((line,index)=>dialogueItem(line,index)).join('') || '<p class="field-hint">这个镜头还没有对白。添加角色后可填写对白。</p>'}<div class="dialogue-tools">${button('添加对白','add-dialogue','plus','small',names().length?'':'disabled')}${button('试听对白','job-audition','volume','small',!s.dialogue?.length?'disabled':busy())}</div></div><div class="editor-footer"><label class="check-label"><input id="new-seed" type="checkbox" ${state.randomizeSeed?'checked':''}>重做时使用新的随机种子</label><div class="editor-actions">${button(shotMedia(state.selected).clip?'重做这个镜头':'生成这个镜头','job-shot','refresh','primary',visualBusy())}${button('从这里往后重做','job-from_shot','arrow','',visualBusy())}</div><small class="field-hint">单镜头重做会保留后面的已完成镜头；向后重做会让后续画面接续新的结果。</small></div></section>${previewPanel()}</div>${timeline()}<div id="job-banner"></div>`;
}

function previewPanel(final=false) {
  return `<aside class="panel preview-panel ${final?'export-preview':''}"><div class="preview-head"><h3>${final?'成片预览':'画面预览'}</h3>${final?'<span class="pill green">已生成版本</span>':`<div class="preview-tabs">${button('视频','preview-video','',state.previewMode==='video'?'active':'')}${button('参考图','preview-image','',state.previewMode==='image'?'active':'')}</div>`}</div><div class="preview-stage"><div class="preview-screen" id="preview-screen"></div></div><div class="preview-meta"><span id="preview-specs"></span><span id="preview-time"></span></div>${!final?`<div class="preview-actions">${button('播放','preview-play','play','small')}${button('取当前帧作参考','capture-frame','camera','small')}</div><div class="panel-body" style="padding-top:0"><input id="preview-seek" type="range" min="0" max="${duration()}" step="0.01" value="0" aria-label="画面播放进度"><label class="check-label"><input id="caption-toggle" type="checkbox" ${state.captions?'checked':''}>叠加当前草稿的字幕预览</label></div><p class="preview-note" id="preview-note"></p>`:''}</aside>`;
}

function bindPreview() {
  state.previewObserver?.disconnect();
  const screen=$('#preview-screen');
  if(!screen)return;
  const final=state.view==='export',clip=final?state.run?.final:shotMedia(state.selected).clip;
  const source=shot().reference_shots?.[0];
  const image=shot().start_image || shotMedia(state.selected).image || (source?shotMedia(source-1).image:null);
  const showVideo=clip&&(final||state.previewMode==='video');
  screen.style.aspectRatio=`${p().video.width}/${p().video.height}`;
  screen.innerHTML=showVideo?`<video id="preview-video" src="${media(clip)}" ${final?'controls':''} playsinline preload="metadata" poster="${image?media(image):''}"></video>`:image?`<img src="${media(image)}" alt="镜头参考图">`:`<div class="preview-empty">${icon('film')}<strong>这个镜头的第一帧，等你来创作</strong><span>选择参考图或编辑提示词，<br>然后生成当前镜头。</span></div>`;
  const video=$('#preview-video');
  if(video){
    video.addEventListener('timeupdate',()=>{if($('#preview-time'))$('#preview-time').textContent=`${time(video.currentTime)} / ${time(video.duration||duration())}`;if($('#preview-seek'))$('#preview-seek').value=video.currentTime;updateCaption(video.currentTime);});
    video.addEventListener('play',()=>{const b=$('[data-action="preview-play"]');if(b)b.innerHTML=icon('pause')+'暂停';});
    video.addEventListener('pause',()=>{const b=$('[data-action="preview-play"]');if(b)b.innerHTML=icon('play')+'播放';});
  }
  if(!final && state.captions){screen.insertAdjacentHTML('beforeend','<div class="subtitle-preview" id="subtitle-preview"><div class="caption-title"></div><div class="caption-line"></div></div>');updateCaption();}
  $('#preview-specs').textContent=final&&state.run?.specs?`${state.run.specs.width}×${state.run.specs.height} · ${state.run.specs.fps}fps`:`${p().video.width}×${p().video.height} · ${p().video.fps}fps · 镜头 ${String(state.selected+1).padStart(2,'0')}`;
  $('#preview-time').textContent=final&&state.run?.specs?`${state.run.specs.duration_seconds.toFixed(2)}s`:`${duration().toFixed(2)}s`;
  if($('#preview-note'))$('#preview-note').textContent=clip?(needsVisual(state.selected)?'当前显示上一次生成的画面。草稿已变化，重做后可查看新结果。':'预览已生成画面。勾选字幕预览可即时查看当前对白排版。'):'参考图用于控制起始构图；生成后可在这里播放视频。';
  const play=$('[data-action="preview-play"]'),capture=$('[data-action="capture-frame"]');
  if(play)play.disabled=!showVideo;
  if(capture)capture.disabled=!showVideo;
  state.previewObserver=new ResizeObserver(()=>updateCaption(video?.currentTime));
  state.previewObserver.observe(screen);
}

function updateCaption(currentTime) {
  const overlay=$('#subtitle-preview');if(!overlay)return;
  const lines=shot().dialogue||[];let line=lines[0];
  if(currentTime!==undefined&&lines.length){
    const cues=state.run?.cues.filter(cue=>cue.shot===state.selected+1)||[];
    const offset=state.selected*duration();
    const cue=cues.find(c=>c.start-offset<=currentTime&&currentTime<c.subtitle_end-offset);
    line=cue?lines.find(item=>item.speaker===cue.speaker&&item.text===cue.text)||lines[0]:null;
    if(!cues.length)line=p().video.generation_mode==='h3'?(currentTime>=.25&&currentTime<duration()-.2?lines[0]:null):(currentTime>=p().tts.dialogue_start_offset_seconds?lines[0]:null);
  }
  const native=p().video.generation_mode==='h3';
  overlay.classList.toggle('native-subtitle',native);
  overlay.style.height=`${(native?52:p().tts.subtitle_band_height)/p().video.height*100}%`;
  overlay.style.setProperty('--scale',$('#preview-screen').clientWidth/p().video.width);
  overlay.style.setProperty('--font-size',native?Math.min(26,p().tts.subtitle_font_size):p().tts.subtitle_font_size);
  overlay.style.setProperty('--title-size',p().tts.subtitle_title_font_size);
  overlay.querySelector('.caption-title').textContent=p().story.title;
  overlay.querySelector('.caption-line').textContent=line?`${line.speaker}：${line.text}`:'';
  overlay.querySelector('.caption-line').style.visibility=line?'visible':'hidden';
}

function timeline() {
  return `<section class="panel timeline-panel"><div class="timeline-head"><div class="panel-title">${icon('film')}<h3>故事时间线</h3></div><small>${p().story.shots.length} 段 · ${(duration()*p().story.shots.length).toFixed(2)} 秒</small></div><div class="timeline-track">${p().story.shots.map((s,index)=>`<button class="timeline-shot ${index===state.selected?'active':''}" data-action="select-shot" data-index="${index}" aria-label="切换到镜头 ${index+1}">${imageFor(index)?`<img src="${media(imageFor(index))}" alt="" loading="lazy">`:`<div class="timeline-empty">${icon('image')}</div>`}<span class="time">${time(index*duration())}</span><span>${String(index+1).padStart(2,'0')} · ${h(s.title)}</span></button>`).join('')}</div><div class="timeline-caption">在分镜列表拖动调整顺序，或使用镜头标题旁的上下按钮。调整顺序后需要重新生成受影响的画面。</div></section>`;
}

function audioPage() {
  return pageHeader('VOICE & SUBTITLES','让角色开口，让对白清楚',p().video.generation_mode==='h3'?'H3 随画面生成原生对白和音效。修改对白需重做镜头；下方 MiMo 试听是独立的备用配音。':'修改对白、试听音色、调整字幕。已完成的配音会自动复用。',button(p().video.generation_mode==='h3'?'生成备用 MiMo 配音':'生成配音与字幕','job-voice','mic','primary',busy()))+tabs()+`<div class="wide-grid"><div class="stack"><section class="panel"><div class="panel-head"><h3>${p().video.generation_mode==='h3'?'备用 MiMo 音色':'角色音色'}</h3><span class="pill ${state.health?.mimo_configured?'green':'orange'}">${state.health?.mimo_configured?'MiMo 已配置':'MiMo 未配置'}</span></div><div class="panel-body"><div class="role-grid">${roleCards()}</div></div></section><section class="panel"><div class="panel-head"><h3>对白脚本</h3><small>每段 ${duration().toFixed(2)} 秒</small></div>${p().story.shots.map((s,index)=>`<div class="audio-row"><span class="shot-no">${String(index+1).padStart(2,'0')}</span><div><h3 style="margin-bottom:10px">${h(s.title)}</h3>${(s.dialogue||[]).map((line,n)=>dialogueItem(line,n,index)).join('')||'<p class="field-hint">暂无对白</p>'}</div><div class="audio-controls">${button('试听','audition-shot','volume','small',`data-index="${index}" ${!s.dialogue?.length?'disabled':busy()}`)}${button('编辑','select-shot','board','small',`data-index="${index}"`)}</div></div>`).join('')}</section></div><div class="stack">${previewPanel()}<section class="panel subtitle-style"><div class="panel-head"><h3>字幕排版</h3><small>预览实时更新</small></div><div class="panel-body">${field('tts.subtitle_font_size','对白字号',p().tts.subtitle_font_size,{type:'number',min:16,max:56})}${field('tts.subtitle_band_height','底部字幕栏高度',p().tts.subtitle_band_height,{type:'number',min:80,max:Math.floor(p().video.height/2)})}${field('tts.subtitle_title_font_size','标题字号',p().tts.subtitle_title_font_size,{type:'number',min:14,max:36})}${selectField('tts.subtitle_font','中文字幕字体',p().tts.subtitle_font,[['C:/Windows/Fonts/msyhbd.ttc','微软雅黑 · 粗体'],['C:/Windows/Fonts/msyh.ttc','微软雅黑 · 常规']])}${field('tts.dialogue_start_offset_seconds','镜头开始后多久说话（秒）',p().tts.dialogue_start_offset_seconds,{type:'number',min:0,max:duration(),step:'0.1'})}<p class="field-hint">${p().video.generation_mode==='h3'?'H3 成片保留模型原生声音，备用 MiMo 配音不会替换它。原生字幕使用底部白字描边，字号最大 26；字幕时间按镜头估算，字幕栏、标题字号和对白起始偏移只用于 MiMo 版本。':'修改对白只需重配相应句子。字幕样式修改后，点击合成成片即可应用。当前未做严格嘴型同步。'}</p></div></section></div></div><div id="job-banner"></div>`;
}

function exportPage() {
  const run=state.run,specs=run?.specs;
  const downloads=[['film','最终 MP4','配音与烧录字幕',run?.final],['book','独立 SRT 字幕','可导入剪辑软件',run?.subtitles],['volume','完整配音 WAV','24kHz · 单声道',run?.audio]].filter(item=>item[0]!=='volume'||run?.video?.generation_mode!=='h3'||item[3]);
  return pageHeader('ASSEMBLE & EXPORT','把镜头，变成完整作品','复用已完成的画面，合成当前对白和字幕，再导出新版本。',button('合成当前草稿','job-compose','film','primary',busy()))+tabs()+`<div class="wide-grid"><div class="stack"><section class="panel"><div class="panel-head"><h3>导出文件</h3><span class="pill ${run?.final?'green':'orange'}">${run?.final?'成片已就绪':'等待合成'}</span></div><div class="panel-body"><div class="export-links">${downloads.map(([name,label,desc,path])=>`<a class="download-card ${path?'':'disabled'}" href="${media(path,true)}" download ${path?'':'aria-disabled="true"'}>${icon(name)}<div><h3>${label}</h3><small>${desc}</small></div></a>`).join('')}<button class="download-card" data-action="export-json">${icon('download')}<div><h3>剧本与参数 JSON</h3><small>可再次导入操作台</small></div></button></div></div></section><section class="panel"><div class="panel-head"><h3>当前生成版本</h3></div><div class="panel-body export-detail"><div class="detail-line"><span>成片时长</span><strong>${specs?specs.duration_seconds.toFixed(3)+' 秒':'—'}</strong></div><div class="detail-line"><span>画面规格</span><span>${specs?`${specs.width} × ${specs.height} · ${specs.fps}fps`:'—'}</span></div><div class="detail-line"><span>音轨</span><span>${run?.voiced?(specs?.audio_source==='H3 native'?'H3 原生对白 · 32kHz 立体声 · AAC':'双角色或多角色配音 · AAC'):run?.audio?'配音已就绪，尚未合成':'尚未生成'}</span></div><div class="detail-line"><span>画面完成</span><span>${run?.shots.filter(s=>s.status==='success').length||0} / ${p().story.shots.length}</span></div><div class="detail-line"><span>项目草稿版本</span><span>v${p().revision}</span></div><div><p class="field-hint">批次目录</p><p class="mono">${run?'runs/'+h(run.id):'首次生成后创建'}</p></div></div></section><div class="info-box">导出的成片对应已生成版本。编辑剧本、提示词或字幕后，点击生成成片会补齐需要更新的镜头并保存一个新版本。</div><div class="button-row">${button('只生成画面','job-generate','film','',visualBusy())}${button('只生成配音字幕','job-voice','mic','',busy())}${button('查看全部版本','navigate','archive','', 'data-view="runs"')}</div></div>${previewPanel(true)}</div><div id="job-banner"></div>`;
}

function assetsPage() {
  return pageHeader('SHARED ASSET LIBRARY','共享素材库','所有作品共用的角色、场景和构图参考。预览图片后，可以指定使用它的作品和分镜。',button('上传参考图片','upload-asset','upload','primary'))+`<div class="asset-grid">${state.assets.map(asset=>`<button class="asset-card" data-action="view-asset" data-path="${h(asset.path)}"><img src="${media(asset.path)}" alt="${h(asset.name)}" loading="lazy"><div class="asset-name">${h(asset.name)}<small>${asset.path.startsWith('prompts/')?'项目参考素材':'你上传的素材'}</small></div></button>`).join('') || '<div class="empty-state">还没有参考图，请上传第一张图片。</div>'}</div>`;
}

function jobCard(job) {
  const isActive=['queued','running','stopping'].includes(job.status),stopped=['interrupted','failed','stopped'].includes(job.status);
  const project=state.projects.find(item=>item.id===job.project_id);
  return `<article class="panel job-card"><div class="panel-head"><div class="job-card-title"><h3>${h(project?.title||job.project_id)} · ${actionText(job.action)} <span class="pill ${job.status==='complete'?'green':job.status==='failed'?'red':'orange'}">${statusText(job.status)}</span></h3><small>${h(job.run_id)} · ${date(job.created_at)}</small></div><div class="job-card-actions">${button('进入作品','open-project','arrow','small',`data-project="${job.project_id}"`)}${isActive||job.status==='interrupted'?button('停止','stop-job','stop','small',`data-job="${job.id}"`):''}${stopped?button('继续任务','resume-job','play','small',`data-job="${job.id}" ${busy()}`):''}${job.status==='complete'?button(job.action==='audition'?'播放试听':'查看结果','job-result','play','small',`data-job="${job.id}"`):''}</div></div><div class="panel-body">${job.error?`<p class="job-error">${h(job.error)}</p>`:''}<p class="field-hint" style="margin-bottom:12px">${h(job.stage)}${job.shot?' · 镜头 '+job.shot:''}${job.sampling?` · 采样 ${job.sampling.value}/${job.sampling.max}`:''}</p><div class="job-logs">${(job.logs||[]).slice(-20).map(log=>`<div><time>${new Date(log.time).toLocaleTimeString('zh-CN',{hour12:false})}</time>${h(log.message)}</div>`).join('') || '等待任务日志…'}</div></div></article>`;
}

function jobsPage() {
  return pageHeader('RENDER QUEUE','任务中心','查看实际执行状态；停止只作用于操作台提交的任务。',button('刷新','refresh-jobs','refresh','small'))+`<div id="jobs-list">${state.jobs.map(jobCard).join('')||`<div class="panel empty-state">${icon('queue')}<strong>还没有新的生成任务</strong><span>在分镜中生成一个镜头，或点击右上角生成成片。</span></div>`}</div>`;
}

function runsPage() {
  return pageHeader('OUTPUT LIBRARY','成片与制作版本','汇总所有作品的输出。成片可以预览下载，历史批次可以作为新作品的起点。',button('刷新','refresh-runs','refresh','small'))+`<div class="run-grid">${state.runs.map(run=>`<article class="panel run-card"><div class="panel-body"><div class="spaced" style="margin-bottom:13px">${icon('film')}<span class="pill ${run.final?'green':'orange'}">${run.final?'成片就绪':statusText(run.status)}</span></div><h3>${h(run.title)}</h3><small class="mono">${h(run.id)}</small><div class="run-stats"><span>${run.shots} 个镜头</span><span>${run.specs?run.specs.duration_seconds.toFixed(2)+' 秒':'尚未合成'}</span><span>${run.specs?run.specs.fps+'fps':''}</span></div><div class="run-card-actions">${button('预览','view-run','play','small',`data-run="${run.id}"`)}${run.final?`<a class="pill" href="${media(run.final,true)}" download>${icon('download')}下载</a>`:''}${button('作为新作品','import-run','copy','small',`data-run="${run.id}"`)}</div></div></article>`).join('')||'<div class="empty-state">还没有生成批次。</div>'}</div>`;
}

function enginePage() {
  const connected=state.health?.connected,url=state.health?.comfyui_url||'http://127.0.0.1:8189';
  return pageHeader('COMFYUI ENGINE','ComfyUI 高级工作区','日常创作在操作台完成；需要检查节点时，在这里使用原生 ComfyUI。',`<a class="pill" href="${h(url)}" target="_blank" rel="noopener">${icon('external')}独立打开</a>`)+`<div class="info-box" style="margin-bottom:20px">${connected?'已连接本机引擎 '+h(url)+'。操作台提交的任务会自动归档到项目。此处直接运行的自定义节点工作流仍保存到 ComfyUI/output/，不会改写操作台草稿。':'本地引擎未就绪，可以直接启动已安装的 GPU 服务。'} ${button('检查连接','health','refresh','small')}</div>${connected?`<iframe class="comfy-frame" src="${h(url)}" title="ComfyUI 节点编辑器"></iframe>`:`<div class="panel empty-state">${icon('nodes')}<strong>等待 ComfyUI 服务启动</strong>${button('启动本地 GPU 引擎','start-engine','play','primary')}</div>`}`;
}

function settingsPage() {
  const cfg=p().video, h3=cfg.generation_mode==='h3';
  return pageHeader('GENERATION SETTINGS','生成设置','H3 在本机生成画面、对白和音效；MiMo 用于自动编剧与分镜审查。')+`<div class="settings-grid"><section class="panel"><div class="panel-head"><h3>画面规格</h3><small>当前作品</small></div><div class="panel-body">${generationControls()}<div class="field"><label for="resolution">分辨率</label><select id="resolution">${[[768,448],[640,384],[384,640],[832,480],[1024,576]].map(([w,ht])=>`<option value="${w},${ht}" ${cfg.width===w&&cfg.height===ht?'selected':''}>${w} × ${ht}</option>`).join('')}${!['768,448','640,384','384,640','832,480','1024,576'].includes([cfg.width,cfg.height].join(','))?`<option selected value="${cfg.width},${cfg.height}">${cfg.width} × ${cfg.height}</option>`:''}</select></div><div class="field-row">${selectField('video.fps','生成帧率',cfg.fps,h3?[[24,'24 fps · H3 原生']]:[16,24,30].map(f=>[f,f+' fps']))}<div class="field"><label for="shot-duration">每段时长（秒）</label><input id="shot-duration" type="number" min="5" max="15" step="0.5" value="${duration()}"></div></div><div class="info-box" id="frame-summary">${frameSummary()}</div><div class="field-row mt">${field('video.width','宽度',cfg.width,{type:'number',min:128,max:1280,step:'32'})}${field('video.height','高度',cfg.height,{type:'number',min:128,max:1280,step:'32'})}</div></div></section><section class="panel"><div class="panel-head"><h3>模型与采样</h3><small>${h3?'MiniMax H3 INT8':'历史配置'}</small></div><div class="panel-body">${field('video.diffusion_model','视频主模型',cfg.diffusion_model)}${field('video.text_encoder','文本编码器',cfg.text_encoder)}${h3?selectField('video.text_encoder_device','文本编码执行',cfg.text_encoder_device,[['default','自动 GPU 卸载'],['cpu','CPU 回退']]):''}${field('video.vae','视频 VAE',cfg.vae)}${h3?field('video.audio_vae','音频 VAE',cfg.audio_vae):''}<div class="field-row">${field('video.steps','采样步数',cfg.steps,{type:'number',min:1,max:60})}${field('video.seed','基础种子',cfg.seed,{type:'number',min:0,max:4294967195})}</div><p class="field-hint">H3 使用单次引导与 res_multistep 采样器。修改对白也需要重做对应镜头。</p><label class="check-label"><input type="checkbox" data-bind="video.use_previous_frame" ${cfg.use_previous_frame?'checked':''}>无指定人物参考时使用上一镜头末帧</label></div></section><section class="panel"><div class="panel-head"><h3>服务连接</h3>${button('检查连接','health','refresh','small')}</div><div class="panel-body">${field('video.comfyui_url','本机 ComfyUI 地址',cfg.comfyui_url)}<div class="info-box">${state.health?.mimo_configured?'MiMo 已配置 · 密钥仅由后端读取':'请配置 MIMO_API_KEY'}<br>${state.health?.h3?.ready?'H3 模型已就绪':'H3 模型待检查'}<br>Script-Weaver：${state.health?.planning?.script_weaver?'已接入':'未安装'} · VideoClaw：${state.health?.planning?.video_claw?'已接入':'未安装'}</div></div></section></div>`;
}

function generatedFrames(frames) {return p().video.generation_mode==='h3'?Math.max(124,Math.ceil((frames+1-5)/17)*17+5):Math.ceil(frames/4)*4+1;}

function frameSummary() {return `每段生成 <strong>${p().video.frames}</strong> 帧，保留 <strong>${p().video.output_frames_per_clip}</strong> 帧。<br>${p().story.shots.length} 个镜头，计划总时长 <strong>${(duration()*p().story.shots.length).toFixed(2)} 秒</strong>。`;}

function updateJobBanner() {
  const container=$('#job-banner');if(!container)return;
  const job=activeJob();
  if(!job){container.innerHTML='';return;}
  const sameRun=state.run?.id===job.run_id,done=state.run?.shots.filter(s=>s.status==='success').length||0,total=state.run?.shots.length||1;
  const detail=job.sampling?`采样 ${job.sampling.value}/${job.sampling.max}`:['film','generate','shot','from_shot'].includes(job.action)?'首次执行需要加载模型；耗时随分辨率与采样步数变化':'复用已完成素材，处理音轨与字幕';
  container.innerHTML=`<div class="job-banner"><div class="job-info"><h3>${actionText(job.action)} · ${h(job.stage)}</h3><small>${job.shot?'镜头 '+String(job.shot).padStart(2,'0')+' · ':''}${detail}${job.project_id!==p().id?' · 其他作品的任务':''}</small>${sameRun?`<div class="progress"><div style="width:${Math.min(100,done/total*100)}%"></div></div>`:''}</div>${sameRun?`<span class="job-count">${done} / ${total}</span>`:''}${button('查看','navigate','queue','small','data-view="jobs"')}${button('停止','stop-job','stop','small',`data-job="${job.id}"`)}</div>`;
}

function updateSaveState() {
  const el=$('#save-state');if(!el)return;
  el.classList.toggle('error',!!state.saveError);
  el.textContent=state.saveError?'保存失败，请检查输入':state.saving?'正在保存…':state.dirty?'草稿待保存':'已保存 · v'+p().revision;
  el.title=state.saveError||'';
}

function updateHealth() {
  const health=state.health;
  const el=$('#engine-status');if(el)el.innerHTML=`<span class="status-dot ${health?.connected?'online':'offline'}"></span>${health?.connected?'ComfyUI 已连接':'ComfyUI 未连接'}`;
  const mimo=$('#mimo-status');if(mimo){mimo.classList.toggle('green',!!health?.mimo_configured);mimo.textContent=health?.mimo_configured?'MiMo 已配置':'MiMo 未配置';}
  const engineState=$('#overview-engine-state');if(engineState)engineState.textContent=health?.connected?'已连接':'未连接';
  const mimoState=$('#overview-mimo-state');if(mimoState)mimoState.textContent=health?.mimo_configured?'已配置':'未配置';
  const dot=$('#overview-engine-dot');if(dot){dot.classList.toggle('online',!!health?.connected);dot.classList.toggle('offline',!health?.connected);}
  const device=$('#overview-device');if(device)device.textContent=health?.devices?.[0]?.name||'本机画面生成 · 配音按需调用';
}

function markDirty() {
  state.dirty=true;state.saveError='';updateSaveState();
  localStorage.setItem('aimedia:draft:'+p().id,JSON.stringify({story:p().story,video:p().video,tts:p().tts,revision:p().revision}));
  clearTimeout(state.autosave);
  state.autosave=setTimeout(()=>saveProject(false).catch(()=>{}),3500);
  updateCaption();
}

async function saveProject(showToast=true) {
  clearTimeout(state.autosave);
  if(state.saving){await new Promise(resolve=>setTimeout(resolve,100));return saveProject(showToast);}
  if(!state.dirty){if(showToast)toast('草稿已保存');return;}
  const id=p().id,snapshot=clone({story:p().story,video:p().video,tts:p().tts,revision:p().revision});
  state.saving=true;updateSaveState();
  try{
    const saved=await api('/api/projects/'+id,'PUT',snapshot);
    if(p().id!==id)return;
    p().revision=saved.revision;p().updated_at=saved.updated_at;p().latest_run=saved.latest_run;
    state.dirty=JSON.stringify([p().story,p().video,p().tts])!==JSON.stringify([snapshot.story,snapshot.video,snapshot.tts]);
    if(!state.dirty)localStorage.removeItem('aimedia:draft:'+id);
    state.projects=state.projects.map(project=>project.id===id?{...project,title:p().story.title,shots:p().story.shots.length}:project);
    const option=$(`#project-picker option[value="${id}"]`);if(option)option.textContent=p().story.title;
    if(showToast)toast('草稿已保存，历史版本已保留');
  }catch(error){state.saveError=error.message;if(showToast)toast(error.message,true);throw error;}
  finally{state.saving=false;updateSaveState();if(state.dirty&&!state.saveError)state.autosave=setTimeout(()=>saveProject(false).catch(()=>{}),3500);}
}

function snapshotUndo() {state.undo.push(clone({story:p().story,video:p().video,tts:p().tts}));if(state.undo.length>20)state.undo.shift();}
function changed(message) {markDirty();renderPage();if(message)toast(message,false,true);}

async function loadProject(id,push=false) {
  const data=await api('/api/projects/'+id);
  state.project=data.project;state.run=data.run;state.selected=0;state.dirty=false;state.saving=false;state.saveError='';state.undo=[];
  const cached=localStorage.getItem('aimedia:draft:'+id);
  if(cached){try{const draft=JSON.parse(cached);if(draft.revision===p().revision){Object.assign(p(),draft);state.dirty=true;toast('已恢复上次未保存的本地草稿');}}catch{}}
  localStorage.setItem('aimedia:last-project',id);
  shell();syncHash(push);await health(true);
}

function syncHash(push=false) {
  const hash=inWork()?`#project=${p().id}&view=${state.view}`:`#view=${state.view}`;
  if(location.hash!==hash)history[push?'pushState':'replaceState'](null,'',hash);
}
async function navigate(view) {
  if(view==='editor')view='storyboard';
  await saveProject(false);
  if(globalViews.includes(view))await refreshWorkspace(false);
  state.view=view;syncHash(true);
  await health(false);
  shell();$('#main').focus({preventScroll:true});
}

async function health(refresh=false) {
  try{state.health=await api('/api/status'+(inWork()?'?project='+p().id:''));updateHealth();if($('#camera-model-status'))$('#camera-model-status').textContent=cameraStatusText();if(refresh&&['settings','engine','overview'].includes(state.view))renderPage();}
  catch(error){state.health={connected:false,mimo_configured:false};updateHealth();}
}

async function startJob(action,selected=state.selected) {
  if(activeJob())return toast('已有任务正在运行，请稍候',true);
  if(['shot','from_shot'].includes(action)&&$('#new-seed')?.checked){shot().seed=crypto.getRandomValues(new Uint32Array(1))[0];markDirty();}
  await saveProject(false);
  const job=await api('/api/projects/'+p().id+'/jobs','POST',{action,selected:selected+1});
  state.jobs.unshift(job);
  if(action!=='audition'){const data=await api('/api/projects/'+p().id);p().latest_run=data.project.latest_run;state.run=data.run;}
  renderPage();toast(action==='audition'?'正在准备试听音频…':'任务已提交，完成后素材会自动更新');
}

function openModal(title,content,footer='') {
  const modal=$('#modal');modal.innerHTML=`<div class="modal-header"><h2 id="modal-title">${h(title)}</h2>${iconButton('关闭','close-modal','close')}</div><div class="modal-content">${content}</div>${footer?`<div class="modal-footer">${footer}</div>`:''}`;
  if(!modal.open)modal.showModal();
}
function closeModal() {$('#modal').close();}

async function newProject(source) {
  await saveProject(false);
  const created=await api('/api/projects','POST',source);
  state.projects=(await api('/api/projects')).projects;
  closeModal();state.view='story';await loadProject(created.id,true);toast('新作品已创建');
}

async function uploadImage(file,reference) {
  if(!file)return;
  const form=new FormData();form.append('image',file);
  const asset=await api('/api/assets','POST',form);state.assets.push(asset);
  if(reference){snapshotUndo();shot().start_image=asset.path;changed('已替换起始参考图');}
  else{renderPage();toast('参考图片已上传');}
}

async function captureFrame() {
  const video=$('#preview-video');if(!video||video.readyState<2)throw new Error('请先播放或定位到需要的画面');
  const canvas=document.createElement('canvas');canvas.width=video.videoWidth;canvas.height=video.videoHeight;canvas.getContext('2d').drawImage(video,0,0);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
  await uploadImage(new File([blob],'captured-frame.png',{type:'image/png'}),true);
}

function downloadJSON(value,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}

async function showRun(id) {
  const run=await api('/api/runs/'+id);
  openModal(run.story.title,run.final?`<video class="modal-video" src="${media(run.final)}" controls playsinline></video><p class="mono mt">runs/${h(id)}</p>`:`<div class="empty-state">这个版本尚未合成成片。已完成 ${run.shots.filter(s=>s.status==='success').length}/${run.shots.length} 个镜头。</div>`,run.final?`<a class="pill green" href="${media(run.final,true)}" download>${icon('download')}下载 MP4</a>`:'');
}

async function handleAction(action,el) {
  if(action==='navigate')return navigate(el.dataset.view);
  if(action==='open-project')return openProject(el.dataset.project);
  if(action==='refresh-workspace'){await saveProject(false);await refreshWorkspace();await health(true);return toast('工作空间已更新');}
  if(action==='filter-projects'){state.projectFilter=el.dataset.filter;state.projectQuery='';return navigate('projects');}
  if(action==='films-prev'||action==='films-next'){const rail=$('#film-carousel');rail.scrollBy({left:rail.clientWidth*.85*(action==='films-next'?1:-1),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});return;}
  if(action==='clear-project-filter'){state.projectQuery='';state.projectFilter='all';return renderPage();}
  if(action==='assign-asset')return assignAsset(el.dataset.path);
  if(action==='save-asset-target'){
    const target=state.assetTarget;if(!target||target.id!==$('#asset-target-project').value)throw new Error('目标作品正在载入，请稍候');
    const index=Number($('#asset-target-shot').value);target.story.shots[index].start_image=el.dataset.path;
    const saved=await api('/api/projects/'+target.id,'PUT',{story:target.story,video:target.video,tts:target.tts,revision:target.revision});
    if(p().id===saved.id)state.project=saved;
    closeModal();await refreshWorkspace();return toast(`已用于「${saved.story.title}」第 ${index+1} 个分镜`);
  }
  if(action==='plan-open')return openModal('自动编剧与分镜',`<p class="field-hint">Script-Weaver 编写大纲、人物、剧本与运镜；VideoClaw 检查站位连续性。成功后生成新的草稿版本。</p><div class="field"><label for="plan-brief">创作要求</label><textarea id="plan-brief" rows="8" placeholder="题材、人物、时长、风格、反转和面部细节要求">${h(p().story.synopsis)}</textarea></div><div class="field"><label for="plan-seconds">成片时长（秒）</label><input id="plan-seconds" type="number" min="10" max="500" step="5" value="60"></div><label class="check-label"><input id="plan-auto-generate" type="checkbox">剧本完成后自动用 H3 生成成片</label>`,button('开始自动创作','plan-start','play','primary'));
  if(action==='plan-start'){
    const brief=$('#plan-brief').value,seconds=Number($('#plan-seconds').value),auto_generate=$('#plan-auto-generate').checked;
    await saveProject(false);
    const job=await api('/api/projects/'+p().id+'/plan','POST',{brief,seconds,auto_generate,revision:p().revision});
    state.jobs.unshift(job);closeModal();toast('自动创作已开始，可在任务中心查看进度');renderPage();return;
  }
  if(action==='save')return saveProject();
  if(action.startsWith('job-')&&action!=='job-result')return startJob(action.slice(4));
  if(action==='select-shot'){state.selected=Number(el.dataset.index);if(state.view!=='storyboard')state.view='storyboard';syncHash();renderPage();return;}
  if(action==='new-project')return openModal('新建作品',`<div class="field"><label for="new-title">作品标题</label><input id="new-title" placeholder="为你的故事取个名字" value=""></div><div class="field"><label for="new-template">创作起点</label><select id="new-template"><option value="blank">空白作品 · 自己编写</option><option value="cat">猫咪漫画模板 · 12 个镜头</option><option value="copy">复制已有作品 · 复用素材</option></select></div><div class="field" id="copy-project-field" hidden><label for="copy-project-source">复制哪部作品</label><select id="copy-project-source">${state.projects.map(project=>`<option value="${project.id}" ${inWork()&&project.id===p().id?'selected':''}>${h(project.title)}</option>`).join('')}</select></div>`,button('创建作品','create-project','plus','primary'));
  if(action==='create-project'){const type=$('#new-template').value;return newProject({title:$('#new-title').value||'未命名作品',blank:type==='blank',copy_from:type==='copy'?$('#copy-project-source').value:undefined});}
  if(action==='copy-project')return newProject({title:p().story.title+' · 副本',copy_from:p().id});
  if(action==='close-modal')return closeModal();
  if(action==='add-role'){snapshotUndo();let name='新角色',n=1;while(p().story.speakers[name])name='新角色 '+n++;p().story.speakers[name]={voice:'茉莉',style:'用自然、清楚的普通话朗读，只朗读给定对白。',appearance:''};return changed('已添加角色');}
  if(action==='remove-role'){const name=el.dataset.role;if(p().story.shots.some(s=>s.dialogue?.some(line=>line.speaker===name)))throw new Error('这个角色仍有对白，请先更换对白角色或移除相关对白');snapshotUndo();delete p().story.speakers[name];return changed('已移除角色');}
  if(action==='add-shot'){snapshotUndo();p().story.shots.splice(state.selected+1,0,{title:'新的分镜',description:'',camera:'固定中景',prompt:'Describe the scene and character action here.',dialogue:[]});state.selected++;return changed('已添加分镜');}
  if(action==='duplicate-shot'){snapshotUndo();const duplicate=clone(shot());duplicate.title+=' · 副本';p().story.shots.splice(state.selected+1,0,duplicate);state.selected++;return changed('已复制分镜');}
  if(action==='remove-shot'){if(p().story.shots.length===1)throw new Error('作品至少保留一个分镜');snapshotUndo();p().story.shots.splice(state.selected,1);state.selected=Math.min(state.selected,p().story.shots.length-1);return changed('已移除分镜');}
  if(action==='move-up'||action==='move-down'){snapshotUndo();const target=state.selected+(action==='move-up'?-1:1);[p().story.shots[state.selected],p().story.shots[target]]=[p().story.shots[target],p().story.shots[state.selected]];state.selected=target;return changed('分镜顺序已调整');}
  if(action==='add-dialogue'){snapshotUndo();shot().dialogue||=[];shot().dialogue.push({speaker:names()[0],text:'在这里填写对白。'});return changed('已添加对白');}
  if(action==='remove-dialogue'){snapshotUndo();p().story.shots[Number(el.dataset.index)].dialogue.splice(Number(el.dataset.line),1);return changed('已移除对白');}
  if(action==='clear-reference'){snapshotUndo();delete shot().start_image;return changed('已恢复默认参考方式');}
  if(action==='pick-reference')return openModal('选择起始参考图',`<p class="field-hint" style="margin-bottom:16px">选中的图片将作为当前镜头的第一帧参考。</p><div class="asset-grid">${state.assets.map(asset=>`<button class="asset-card" data-action="use-reference" data-path="${h(asset.path)}"><img src="${media(asset.path)}" alt="${h(asset.name)}" loading="lazy"><div class="asset-name">${h(asset.name)}</div></button>`).join('')}</div>`,button('上传图片','upload-reference','upload'));
  if(action==='use-reference'){snapshotUndo();shot().start_image=el.dataset.path;closeModal();return changed('已指定参考图');}
  if(action==='upload-reference'||action==='upload-asset'){const input=$('#upload-image');input.dataset.reference=action==='upload-reference'?'1':'';input.click();return;}
  if(action==='capture-frame')return captureFrame();
  if(action==='preview-video'||action==='preview-image'){state.previewMode=action==='preview-video'?'video':'image';renderPage();return;}
  if(action==='preview-play'){const video=$('#preview-video');if(video)video.paused?await video.play():video.pause();return;}
  if(action==='audition-shot')return startJob('audition',Number(el.dataset.index));
  if(action==='export-json')return downloadJSON({story:p().story,video:p().video,tts:p().tts},p().story.title+'-草稿.json');
  if(action==='import')return $('#import-json').click();
  if(action==='undo'){const previous=state.undo.pop();if(!previous)return toast('没有可撤销的结构操作');Object.assign(p(),previous);state.selected=Math.min(state.selected,p().story.shots.length-1);return changed('已撤销');}
  if(action==='revisions'){const revisions=await api('/api/projects/'+p().id+'/revisions');return openModal('草稿修改历史',revisions.length?revisions.map(rev=>`<div class="revision-row"><div><strong>v${rev.revision} · ${h(rev.title)}</strong><small>${date(rev.updated_at)}</small></div>${button('恢复到草稿','restore-revision','undo','small',`data-revision="${rev.revision}"`)}</div>`).join(''):'<p class="field-hint">编辑并保存后，这里会保留之前的草稿版本。</p>');}
  if(action==='restore-revision'){const old=await api('/api/projects/'+p().id+'/revisions/'+el.dataset.revision);snapshotUndo();Object.assign(p(),{story:old.story,video:old.video,tts:old.tts});state.selected=0;closeModal();return changed('已恢复历史内容，可撤销或继续编辑');}
  if(action==='stop-job'){await api('/api/jobs/'+el.dataset.job+'/stop','POST',{});return poll();}
  if(action==='resume-job'){await api('/api/jobs/'+el.dataset.job+'/resume','POST',{});toast('开始恢复原任务');return poll();}
  if(action==='job-result'){const job=state.jobs.find(j=>j.id===el.dataset.job);const run=await api('/api/runs/'+job.run_id);if(job.action==='audition'&&run.audio){$('#audio-player').src=media(run.audio);return $('#audio-player').play();}return showRun(job.run_id);}
  if(action==='refresh-jobs'){state.jobs=await api('/api/jobs');renderPage();return;}
  if(action==='refresh-runs'){state.runs=await api('/api/runs');renderPage();return;}
  if(action==='view-run')return showRun(el.dataset.run);
  if(action==='import-run')return newProject({run_id:el.dataset.run});
  if(action==='view-asset')return openModal('共享参考素材',`<img src="${media(el.dataset.path)}" alt="参考素材" style="width:100%;max-height:60dvh;object-fit:contain"><p class="mono mt">${h(el.dataset.path)}</p>`,button('用于作品分镜','assign-asset','image','primary',`data-path="${h(el.dataset.path)}"`));
  if(action==='health'){await saveProject(false);return health(true);}
  if(action==='start-engine'){const result=await api('/api/engine/start','POST',{});toast(result.status==='ready'?'GPU 引擎已经就绪':'GPU 引擎正在启动，请稍候');await health(true);if(result.status==='starting')setTimeout(()=>health(true),8000);return;}
  if(action==='help')return openModal('AIMedia Studio 使用说明',`<div class="help-list"><div><strong>一级总控台</strong>总览查看全部作品、制作进程、生产任务与引擎状态。作品管理支持搜索和筛选，任务中心、共享素材和成片库面向整个工作空间。</div><div><strong>二级制作台</strong>在作品卡片点击进入制作台，编辑该作品的剧本、角色、分镜、配音和生成参数。返回作品管理或总控台前会保存草稿。</div><div><strong>共享素材</strong>从素材库预览图片后，选择目标作品与分镜再保存。也可以在制作台直接上传参考图。</div><div><strong>1. 剧本与角色</strong>编辑故事梗概、角色外观和音色，以及全局画风。</div><div><strong>2. 分镜与画面</strong>逐镜头修改场景、镜头运动、提示词、参考图和对白。生成当前镜头后可以直接预览。</div><div><strong>3. 配音与字幕</strong>点击试听生成所选镜头的配音。修改对白或音色后，只会重新生成需要更新的音频。</div><div><strong>4. 合成与导出</strong>点击生成成片，会补齐变化的画面、处理配音与字幕，导出一个新版本。已有素材自动复用。</div><div><strong>重做与恢复</strong>单镜头重做保留后续镜头；从这里往后重做可以让后续接续新画面。任务意外中断后，在任务中心继续原任务。</div><div><strong>目录</strong>草稿、历史和上传素材位于 workspace/；每次生成的分镜、任务记录、逐段视频和成片位于 runs/。原有样片始终保留。</div><div><strong>本机服务</strong>操作台：http://127.0.0.1:8190<br>GPU 引擎：http://127.0.0.1:8189<br>MiMo 密钥由后端读取，不进入浏览器。Ctrl+S 保存草稿。</div></div>`);
}

document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');
  if(target&&!target.disabled){event.preventDefault();handleAction(target.dataset.action,target).catch(error=>toast(error.message,true));return;}
  const card=event.target.closest('[data-shot]');if(card){state.selected=Number(card.dataset.shot);renderPage();}
});

document.addEventListener('input',event=>{
  const input=event.target;
  if(input.id==='project-search'){state.projectQuery=input.value;$('#project-results').innerHTML=projectResults();return;}
  if(input.id==='preview-seek'){const video=$('#preview-video');if(video)video.currentTime=Number(input.value);return;}
  if(input.dataset.bind){
    const parts=input.dataset.bind.split('.'),last=parts.pop();let object=p();for(const key of parts)object=object[key];
    const oldDuration=duration();object[last]=input.type==='checkbox'?input.checked:input.dataset.number?Number(input.value):input.value;
    if(input.dataset.bind==='video.fps'){p().video.output_frames_per_clip=Math.round(oldDuration*p().video.fps);p().video.frames=generatedFrames(p().video.output_frames_per_clip);}
    markDirty();if($('#frame-summary'))$('#frame-summary').innerHTML=frameSummary();return;
  }
  if(input.dataset.roleField){p().story.speakers[input.dataset.role][input.dataset.roleField]=input.value;markDirty();return;}
  if(input.id==='shot-duration'){const frames=Math.round(Number(input.value)*p().video.fps);p().video.output_frames_per_clip=frames;p().video.frames=generatedFrames(frames);markDirty();if($('#frame-summary'))$('#frame-summary').innerHTML=frameSummary();}
});

document.addEventListener('change',event=>{
  const input=event.target;
  if(input.id==='new-seed'){state.randomizeSeed=input.checked;return;}
  if(input.id==='generation-mode'){
    const profile=state.health?.generation_profiles?.[input.value];
    if(!profile){input.value=p().video.generation_mode||'wan22';toast('请先检查服务连接，再切换模式',true);return;}
    snapshotUndo();const connection=p().video.comfyui_url,seed=p().video.seed;
    p().video={...clone(profile),comfyui_url:connection,seed};
    changed('已切换生成模式，画面需重新生成；可撤销或从历史版本恢复');return;
  }
  if(input.id==='project-filter'||input.id==='project-sort'){state[input.id==='project-filter'?'projectFilter':'projectSort']=input.value;$('#project-results').innerHTML=projectResults();return;}
  if(input.id==='asset-target-project'){state.assetTarget=null;assetTargetOptions(input.value).catch(error=>toast(error.message,true));return;}
  if(input.id==='new-template'){$('#copy-project-field').hidden=input.value!=='copy';return;}
  if(input.id==='project-picker'){saveProject(false).then(()=>loadProject(input.value,true)).catch(error=>{input.value=p().id;toast(error.message,true);});return;}
  if(input.id==='caption-toggle'){state.captions=input.checked;bindPreview();return;}
  if(input.id==='resolution'){[p().video.width,p().video.height]=input.value.split(',').map(Number);markDirty();renderPage();return;}
  if(input.dataset.roleName){
    const old=input.dataset.roleName,name=input.value.trim();if(!name||['__proto__','constructor','prototype'].includes(name)||name!==old&&p().story.speakers[name]){input.value=old;toast('角色名称为空、重复或属于保留名称',true);return;}
    if(name!==old){snapshotUndo();p().story.speakers[name]=p().story.speakers[old];delete p().story.speakers[old];for(const s of p().story.shots)for(const line of s.dialogue||[])if(line.speaker===old)line.speaker=name;changed('角色名称与对白已同步更新');}
  }
});

$('#upload-image').addEventListener('change',async event=>{try{await uploadImage(event.target.files[0],event.target.dataset.reference==='1');closeModal();}catch(error){toast(error.message,true);}finally{event.target.value='';}});
$('#import-json').addEventListener('change',async event=>{try{const value=JSON.parse(await event.target.files[0].text());snapshotUndo();if(value.story){p().story=value.story;if(value.video)p().video=value.video;if(value.tts)p().tts=value.tts;}else p().story=value;if(!p().story.shots?.length)throw new Error('文件缺少分镜列表');state.selected=0;changed('分镜已导入草稿，请检查后保存');}catch(error){const previous=state.undo.pop();if(previous)Object.assign(p(),previous);toast('导入失败：'+error.message,true);}finally{event.target.value='';}});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveProject().catch(()=>{});}if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-shot]')){event.preventDefault();state.selected=Number(event.target.dataset.shot);renderPage();}});
document.addEventListener('dragstart',event=>{const card=event.target.closest('[data-shot]');if(card){state.drag=Number(card.dataset.shot);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',state.drag);}});
document.addEventListener('dragover',event=>{const card=event.target.closest('[data-shot]');if(card){event.preventDefault();card.classList.add('dragover');}});
document.addEventListener('dragleave',event=>event.target.closest('[data-shot]')?.classList.remove('dragover'));
document.addEventListener('drop',event=>{const card=event.target.closest('[data-shot]');if(card&&state.drag!==null){event.preventDefault();const target=Number(card.dataset.shot);snapshotUndo();const moved=p().story.shots.splice(state.drag,1)[0];p().story.shots.splice(target,0,moved);state.selected=target;state.drag=null;changed('分镜顺序已调整');}});
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});

async function poll() {
  if(state.polling||!p())return;
  state.polling=true;
  try{
    const previous=state.jobs;state.jobs=await api('/api/jobs');
    const related=state.jobs.filter(job=>job.project_id===p().id);
    if(related.some(job=>['queued','running','stopping'].includes(job.status))||related.some(job=>previous.find(old=>old.id===job.id)?.status!==job.status)){
      const data=await api('/api/projects/'+p().id),oldSource=state.run?.shots[state.selected]?.clip;
      state.run=data.run;p().latest_run=data.project.latest_run;
      if(data.project.revision!==p().revision&&!state.dirty){state.project=data.project;state.selected=Math.min(state.selected,p().story.shots.length-1);renderPage();}
      if(oldSource!==state.run?.shots[state.selected]?.clip)bindPreview();
      for(const job of related){
        const old=previous.find(j=>j.id===job.id);
        if(old&&old.status!==job.status&&job.status==='complete'){
          if(job.action==='audition'){const run=await api('/api/runs/'+job.run_id);$('#audio-player').src=media(run.audio);$('#audio-player').play().catch(()=>toast('试听已就绪，在任务中心点击播放'));}
          else{toast('任务完成，新的素材已就绪');if(['storyboard','export'].includes(state.view))renderPage();}
        }
        if(old&&old.status!==job.status&&job.status==='failed')toast(job.error||'任务失败，请查看任务中心',true);
      }
    }
    updateJobBanner();if(state.view==='jobs')$('#jobs-list').innerHTML=state.jobs.map(jobCard).join('');
    if(globalViews.includes(state.view)&&Date.now()-state.workspaceUpdated>10000){
      const before=JSON.stringify([state.projects,state.assets,state.runs,previous,state.health]);
      await refreshWorkspace(false);
      const updated=before!==JSON.stringify([state.projects,state.assets,state.runs,state.jobs,state.health]);
      if(updated&&!$('#modal').open){
        if(state.view==='projects')$('#project-results').innerHTML=projectResults();
        else if(state.view==='overview')renderPage(false);
      }
    }
    document.querySelectorAll('[data-action^="job-"],[data-action="audition-shot"]').forEach(el=>{if(el.dataset.action==='job-result')return;const hasDialogue=el.dataset.action==='job-audition'?shot().dialogue?.length:el.dataset.action==='audition-shot'?p().story.shots[Number(el.dataset.index)]?.dialogue?.length:true;const visual=['job-film','job-generate','job-shot','job-from_shot'].includes(el.dataset.action);el.disabled=!!activeJob()||!hasDialogue||visual&&cameraMode()&&!state.health?.fun_camera?.ready;});
  }catch{/* The saved draft stays editable if the local service briefly reconnects. */}
  finally{state.polling=false;}
}

async function boot() {
  try{
    const params=new URLSearchParams(location.hash.slice(1));state.view=params.get('view')||(params.has('project')?'storyboard':'overview');
    if(![...workViews,...globalViews].includes(state.view))state.view='overview';
    await refreshWorkspace(false);
    const preferred=params.get('project')||localStorage.getItem('aimedia:last-project');const project=state.projects.find(p=>p.id===preferred)||state.projects.find(p=>p.title==='小鱼饼失踪案')||state.projects[0];
    await loadProject(project.id);setInterval(poll,2500);setInterval(()=>health(false),30000);
  }catch(error){$('#app').innerHTML=`<div class="empty-state">${icon('refresh')}<h2>操作台暂时无法载入</h2><p>${h(error.message)}</p><button onclick="location.reload()">重新载入</button></div>`;}
}
window.addEventListener('popstate',async()=>{
  try{
    await saveProject(false);
    const params=new URLSearchParams(location.hash.slice(1)),view=params.get('view')||'overview';
    state.view=[...workViews,...globalViews].includes(view)?view:'overview';
    const id=params.get('project');
    if(inWork()&&id&&id!==p().id)await loadProject(id);
    else{if(!inWork())await refreshWorkspace(false);shell();syncHash();await health(true);}
  }catch(error){toast(error.message,true);}
});
boot();
