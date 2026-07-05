const IMG_PROXY = '/img/';

const $ = (id) => document.getElementById(id);
let DATA = null;
function p(u){if(!u)return u;return u&&IMG_PROXY?IMG_PROXY+u.replace('https://',''):u;}
new MutationObserver(function(ms){for(var i=0;i<ms.length;i++)for(var j=0;j<ms[i].addedNodes.length;j++){var n=ms[i].addedNodes[j];if(n.nodeType!==1)continue;if(n.tagName==='IMG'||n.tagName==='VIDEO'||n.tagName==='SOURCE')rw(n);if(n.querySelectorAll)n.querySelectorAll('img,video,source').forEach(rw)}}).observe(document.body,{childList:true,subtree:true});
function rw(el){if(el.getAttribute && el.getAttribute('data-no-proxy')==='1')return;['src','poster'].forEach(function(a){var v=el.getAttribute(a);if(v&&v.indexOf('/img/')===-1&&(v.indexOf('fourhoi.com')!==-1||v.indexOf('jable.tv')!==-1||v.indexOf('assets-cdn.jable')!==-1))el.setAttribute(a,IMG_PROXY+v.replace('https://',''))})}

// 自动代理所有动态插入的 fourhoi 图片

// 状态
const state = {
  source: 'missav', // missav / jable
  type: 'all',      // all / solo / multi / saved
  tags: new Set(),  // 包含
  excludeTags: new Set(),
  actresses: new Set(),
  current: null,
  history: [],
  shortlist: [],
  favoritesMissav: [],
  favoritesJable: [],
};

function currentSourceOf(v) {
  return (v && (v.source || (DATA && DATA.source) || state.source)) || 'missav';
}
function coverUrl(v) {
  // MissAV 封面直连，避免所有封面都绕本地 /img/ 代理导致加载慢。
  // Jable 仍走代理，因为很多线路需要代理访问其 CDN。
  return currentSourceOf(v) === 'jable' ? p(v.cover) : (v.cover || '');
}
function previewUrl(v) {
  return p(v.preview || '');
}
function favListForSource(src) {
  return src === 'jable' ? state.favoritesJable : state.favoritesMissav;
}
function favStorageKey(src) {
  return src === 'jable' ? 'missav_picker_favorites_jable_v1' : 'missav_picker_favorites_missav_v1';
}
function favKey(v, src) {
  const source = src || currentSourceOf(v);
  return source + ':' + v.code;
}
function isFavorite(v) {
  if (!v) return false;
  if (v.is_saved && currentSourceOf(v) === 'missav') return true;
  const src = currentSourceOf(v);
  return favListForSource(src).some(f => f.code === v.code);
}
function normFavorite(v, src) {
  return {
    code: v.code,
    title: v.title || '',
    url: v.url,
    cover: v.cover,
    preview: v.preview || '',
    date: v.date || '',
    actresses: Array.isArray(v.actresses) ? v.actresses.slice() : [],
    is_multi: !!v.is_multi,
    tags: Array.isArray(v.tags) ? v.tags.slice() : [],
    is_saved: !!v.is_saved,
    source: src || currentSourceOf(v)
  };
}

let SYNC_LAST_UPDATED = 0;
let SYNC_SUPPRESS_SAVE = false;
let syncSaveTimer = null;

function slimVideoRef(v) {
  if (!v) return null;
  return { code: v.code, source: currentSourceOf(v) };
}

function exportSyncState() {
  return {
    version: 1,
    source: state.source,
    type: state.type,
    tags: [...state.tags],
    excludeTags: [...state.excludeTags],
    actresses: [...state.actresses],
    current: slimVideoRef(state.current),
    shortlist: state.shortlist.map(slimVideoRef).filter(Boolean),
    history: state.history.map(slimVideoRef).filter(Boolean),
    favoritesMissav: state.favoritesMissav,
    favoritesJable: state.favoritesJable,
    browsePage,
    browseOpen: $('browseArea').style.display !== 'none'
  };
}

function findVideoByRef(ref) {
  if (!ref || !ref.code) return null;
  const pool = ref.source === 'jable' ? state.favoritesJable.concat((DATA && DATA.videos) || []) : state.favoritesMissav.concat((DATA && DATA.videos) || []);
  return pool.find(v => v.code === ref.code) || null;
}

async function loadSourceData(src) {
  if (src === 'jable') {
    if (DATA && DATA.source === 'jable') return;
    const d = await (await fetch('jable_data.json?_=' + Date.now())).json();
    DATA = d;
    var uniq = {};
    DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
    DATA.actresses = Object.keys(uniq);
    $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
  } else {
    if (DATA && (!DATA.source || DATA.source === 'missav')) return;
    const d = await (await fetch('picker_data.json?_=' + Date.now())).json();
    DATA = d;
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${(DATA.actresses||[]).length} 位女优 · 按空格快速抽`;
  }
  renderTagChips();
  renderActressGrid();
  renderFavorites();
  updateCount();
}

async function applySyncState(payload) {
  if (!payload || !payload.version) return;
  SYNC_SUPPRESS_SAVE = true;
  try {
    const src = payload.source || 'missav';
    await loadSourceData(src);
    document.querySelectorAll('#sourceChips .chip').forEach(c => c.classList.remove('active'));
    const chip = document.querySelector(`#sourceChips .chip[data-source="${src}"]`);
    if (chip) chip.classList.add('active');
    state.source = src;
    state.type = payload.type || 'all';
    state.tags = new Set(payload.tags || []);
    state.excludeTags = new Set(payload.excludeTags || []);
    state.actresses = new Set(payload.actresses || []);
    state.favoritesMissav = Array.isArray(payload.favoritesMissav) ? payload.favoritesMissav : [];
    state.favoritesJable = Array.isArray(payload.favoritesJable) ? payload.favoritesJable : [];
    state.shortlist = (payload.shortlist || []).map(findVideoByRef).filter(Boolean);
    state.history = (payload.history || []).map(findVideoByRef).filter(Boolean);
    browsePage = payload.browsePage || 0;

    document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.remove('active'));
    const typeChip = document.querySelector(`#typeChips .chip[data-type="${state.type}"]`);
    if (typeChip) typeChip.classList.add('active');

    renderFavorites();
    renderTagChips();
    renderActressGrid();
    updateCount();

    state.current = findVideoByRef(payload.current);
    if (state.current) renderResult(); else $('resultArea').innerHTML = `<div class="empty"><div class="emoji">🎰</div><div>设置筛选条件，点上面的按钮开始随机</div></div>`;
    renderShortlist();
    renderHistory();
    if (payload.browseOpen) {
      renderBrowse();
      $('browseArea').style.display = 'block';
    } else {
      $('browseArea').style.display = 'none';
    }
    SYNC_LAST_UPDATED = payload.updatedAt || 0;
  } finally {
    SYNC_SUPPRESS_SAVE = false;
  }
}

function scheduleSyncSave() {
  if (SYNC_SUPPRESS_SAVE) return;
  clearTimeout(syncSaveTimer);
  syncSaveTimer = setTimeout(async () => {
    try {
      const payload = exportSyncState();
      const r = await fetch('/sync_state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (r.ok) SYNC_LAST_UPDATED = Date.now();
    } catch(e) {}
  }, 350);
}

async function pullSyncState() {
  try {
    const r = await fetch('/sync_state.json?_=' + Date.now());
    const payload = await r.json();
    if ((payload.updatedAt || 0) > (SYNC_LAST_UPDATED || 0)) {
      await applySyncState(payload);
    }
  } catch(e) {}
}

// ---- 渲染筛选 UI ----
const EXCLUDE_PRESET = ['BEST', '强奸', '调教', '春药'];

// 按类型过滤的视频池(不包含标签/女优过滤,因为标签本身就是筛选条件)
function getTypePool() {
  if (!DATA || !DATA.videos) return [];
  return DATA.videos.filter(v => {
    if (state.type === 'solo' && v.is_multi) return false;
    if (state.type === 'multi' && !v.is_multi) return false;
    if (state.type === 'saved' && !isFavorite(v)) return false;
    return true;
  });
}

function renderTagChips() {
  if (!DATA) {
    // 初始渲染:用索引数据
    $('tagChips').innerHTML = IDX.tags.slice(0, 24).map(t =>
      `<span class="chip" data-tag="${t}" style="opacity:0.5">${t}<span class="count">${IDX.tag_counts[t]}</span></span>`
    ).join('');
    $('excludeChips').innerHTML = EXCLUDE_PRESET.map(t =>
      `<span class="chip" data-extag="${t}" style="opacity:0.5">🚫 ${t}</span>`
    ).join('');
    return;
  }
  const pool = getTypePool();
  const tc = {};
  for (const v of pool) for (const t of v.tags) tc[t] = (tc[t] || 0) + 1;
  // 按频次排序,取 top 24
  const sorted = Object.entries(tc).sort((a, b) => b[1] - a[1]).slice(0, 24);
  const topSet = new Set(sorted.map(e => e[0]));
  // 如果当前选中的标签不在 top24 里,也保留
  for (const t of state.tags) if (!topSet.has(t) && tc[t]) topSet.add(t);
  // 如果排除的标签不在 top24,也保留
  for (const t of state.excludeTags) if (!topSet.has(t) && tc[t]) topSet.add(t);

  $('tagChips').innerHTML = [...topSet].map(t => {
    const n = tc[t] || 0;
    const dim = n === 0 ? ' style="opacity:0.35"' : '';
    return `<span class="chip" data-tag="${t}"${dim}>${t}<span class="count">${n}</span></span>`;
  }).join('');

  // 恢复 active 态
  for (const t of state.tags) {
    const chip = document.querySelector(`#tagChips .chip[data-tag="${t}"]`);
    if (chip) chip.classList.add('active');
  }
  for (const t of state.excludeTags) {
    const chip = document.querySelector(`#excludeChips .chip[data-extag="${t}"]`);
    if (chip) chip.classList.add('active');
  }

  $('excludeChips').innerHTML = EXCLUDE_PRESET.map(t => {
    const n = tc[t] || 0;
    const dim = n === 0 ? ' style="opacity:0.35"' : '';
    return `<span class="chip" data-extag="${t}"${dim}>🚫 ${t}</span>`;
  }).join('');
  // 恢复 exclude active
  for (const t of state.excludeTags) {
    const chip = document.querySelector(`#excludeChips .chip[data-extag="${t}"]`);
    if (chip) chip.classList.add('active');
  }
}

function chipHTML(a) {
  const sel = state.actresses.has(a) ? ' active' : '';
  const D = DATA || IDX;
  const avatar = (D.actress_avatars || {})[a];
  const dispName = (D.actress_display || {})[a] || a;
  const initial = a.replace(/[（(].*[）)]/g,'').charAt(0);
  const fallback = `<span class="avatar-fallback">${initial}</span>`;
  const imgHtml = avatar
    ? `<img src="${avatar}" alt="${a}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`
    : '';
  return `<div class="actress-chip${sel}" data-actress="${a}" title="${dispName}">
            <div class="blob">${fallback}${imgHtml}</div>
            <span class="name">${dispName}</span>
          </div>`;
}

function renderActressGrid(filter='') {
  const D = DATA || IDX;
  const groups = D.actress_groups || {};
  const display = D.actress_display || {};

  // classify
  const saved = [], rookie = [], other = [];
  const allActresses = (DATA || IDX).actresses;
  for (const a of allActresses) {
    if (filter && !a.toLowerCase().includes(filter.toLowerCase())) continue;
    const g = groups[a] || 'other';
    if (g === 'saved') saved.push(a);
    else if (g === 'rookie') rookie.push(a);
    else other.push(a);
  }

  function fillGrid(id, list) { $(id).innerHTML = list.map(chipHTML).join(''); }

  fillGrid('savedGrid', saved);
  fillGrid('rookieGrid', rookie);
  fillGrid('otherGrid', other);

  // show/hide headers
  for (const [headerId, gridId, countId, list] of [
    ['savedHeader','savedGrid','savedCount',saved],
    ['rookieHeader','rookieGrid','rookieCount',rookie],
    ['otherHeader','otherGrid','otherCount',other]
  ]) {
    const hdr = $(headerId), cnt = $(countId);
    hdr.style.display = list.length > 0 ? 'flex' : 'none';
    cnt.textContent = list.length;
    // auto-collapse ONLY when truly empty; auto-expand when items arrive
    const section = hdr.parentElement;
    if (list.length === 0) {
      if (!section.classList.contains('collapsed')) section.classList.add('collapsed');
    } else {
      section.classList.remove('collapsed');
    }
  }
}

// ---- 候选过滤 ----
function getCandidates() {
  return DATA.videos.filter(v => {
    // 类型
    if (state.type === 'solo' && v.is_multi) return false;
    if (state.type === 'multi' && !v.is_multi) return false;
    if (state.type === 'saved' && !isFavorite(v)) return false;
    // 包含标签(任一命中)
    if (state.tags.size > 0) {
      const hit = v.tags.some(t => state.tags.has(t));
      if (!hit) return false;
    }
    // 排除标签
    if (state.excludeTags.size > 0) {
      const exHit = v.tags.some(t => state.excludeTags.has(t));
      if (exHit) return false;
    }
    // 女优
    if (state.actresses.size > 0) {
      const hit = v.actresses.some(a => state.actresses.has(a));
      if (!hit) return false;
    }
    return true;
  });
}

function deselectTag(t) {
  state.tags.delete(t);
  const chip = document.querySelector('#tagChips .chip[data-tag="'+t+'"]');
  if (chip) chip.classList.remove('active');
  renderTagChips(); updateCount();
}
function deselectActress(a) {
  state.actresses.delete(a);
  document.querySelectorAll('.actress-chip').forEach(function(c) {
    if (c.dataset.actress === a) c.classList.remove('active');
  });
  updateCount();
}

function renderSelBar() {
  const sb = $('selectedBar');
  if (!state.actresses.size && !state.tags.size && state.type === 'all') {
    sb.innerHTML = ''; return;
  }
  const D = DATA || IDX;
  const parts = [];
  if (state.type !== 'all') {
    const tl = {all:'',solo:'👤 单人',multi:'👥 多人',saved:'⭐ 仅收藏'}[state.type];
    parts.push('<span class="sel-chip type" data-click="clearType">'+tl+' ×</span>');
  }
  state.tags.forEach(t => parts.push('<span class="sel-chip tag" data-click="dropTag" data-tag="'+t.replace(/"/g,'&quot;')+'">'+t+' ×</span>'));
  state.actresses.forEach(a => {
    const av = (D.actress_avatars || {})[a];
    const disp = (D.actress_display||{})[a] || a;
    const initial = a.replace(/[（(].*[）)]/g,'').charAt(0);
    const img = '<span class="avatar-fallback">'+initial+'</span>' + (av ? '<img src="'+av+'" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : '');
    parts.push('<span class="sel-item" data-click="dropActress" data-actress="'+a.replace(/"/g,'&quot;')+'" title="'+disp.replace(/"/g,'&quot;')+'"><span class="sel-blob">'+img+'</span><span class="sel-name">'+disp+'</span></span>');
  });
  sb.innerHTML = parts.join('');
}

$('selectedBar').addEventListener('click', function(e) {
  const el = e.target.closest('[data-click]'); if (!el) return;
  const action = el.dataset.click;
  if (action === 'clearType') { clearType(); }
  else if (action === 'dropTag') { dropTag(el.dataset.tag); }
  else if (action === 'dropActress') { dropActress(el.dataset.actress); }
});

function dropTag(t) { state.tags.delete(t); renderTagChips(); updateCount(); }
function dropActress(a) {
  state.actresses.delete(a);
  document.querySelectorAll('.actress-chip').forEach(c => { if (c.dataset.actress === a) c.classList.remove('active'); });
  updateCount();
}
function clearType() {
  state.type = 'all';
  document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.remove('active'));
  document.querySelector('#typeChips .chip[data-type="all"]').classList.add('active');
  renderTagChips(); updateCount();
}

function updateCount() {
  const n = getCandidates().length;
  $('candidateCount').textContent = n;
  $('rollBtn').disabled = n === 0;
  $('shortlistBtn').disabled = n === 0;
  renderSelBar();
}

// ---- 随机抽 ----
function rollOne() {
  const cands = getCandidates();
  if (cands.length === 0) return;
  // 排除历史上已随机过的
  let pool = cands.filter(v => !state.history.some(h => h.code === v.code));
  if (pool.length === 0) {
    // 全部抽过了,清空历史重新来
    state.history = [];
    pool = cands;
  }
  const v = pool[Math.floor(Math.random() * pool.length)];
  state.current = v;
  // 历史(去重,前置)
  state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
  saveHistory();
  renderResult();
  renderHistory();
  scheduleSyncSave();
}

function sampleUnique(list, count) {
  const pool = list.slice();
  const picked = [];
  while (pool.length && picked.length < count) {
    const idx = Math.floor(Math.random() * pool.length);
    picked.push(pool.splice(idx, 1)[0]);
  }
  return picked;
}

function rollShortlist() {
  const cands = getCandidates();
  if (cands.length === 0) return;
  const fresh = cands.filter(v => !state.history.some(h => h.code === v.code));
  const pool = fresh.length >= 6 ? fresh : cands;
  state.shortlist = sampleUnique(pool, Math.min(6, pool.length));
  renderShortlist();
  $('shortlistArea').style.display = 'block';
  $('shortlistArea').scrollIntoView({behavior:'smooth', block:'center'});
  scheduleSyncSave();
}

function pickShortlist(code) {
  const v = state.shortlist.find(x => x.code === code);
  if (!v) return;
  state.current = v;
  state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
  saveHistory();
  renderResult();
  renderHistory();
  scheduleSyncSave();
}

function clearShortlist() {
  state.shortlist = [];
  renderShortlist();
  scheduleSyncSave();
}

function renderShortlist() {
  const area = $('shortlistArea');
  const grid = $('shortlistGrid');
  if (!state.shortlist.length) {
    area.style.display = 'none';
    grid.innerHTML = '';
    return;
  }
  area.style.display = 'block';
  $('shortlistTitle').textContent = `🎰 本轮候选 · ${state.shortlist.length} 部（点卡片选中）`;
  grid.innerHTML = state.shortlist.map(v => {
    const src = currentSourceOf(v);
    const actress = (v.actresses || []).slice(0, 2).join('、') || '未知女优';
    return `
      <div class="short-card" onclick="pickShortlist('${v.code}')" title="点选 ${v.code}">
        <div class="img-wrap">
          <img src="${src === 'jable' ? p(v.cover) : (v.cover || '')}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" ${src === 'jable' ? '' : 'data-no-proxy="1"'}
            onerror="this.parentElement.style.background='var(--border)';this.style.display='none'">
        </div>
        <div class="info">
          <div class="code">${v.code}</div>
          <div class="title">${v.title || '（无标题）'}</div>
          <div class="meta">${actress}${v.date ? ' · ' + v.date : ''}</div>
        </div>
      </div>`;
  }).join('');
}

// ---- 渲染结果 ----
function renderResult() {
  const v = state.current;
  if (!v) return;
  const badges = [];
  badges.push(v.is_multi
    ? `<span class="badge multi">👥 多人 · ${v.actresses.length} 位</span>`
    : `<span class="badge solo">👤 单人</span>`);
  if (isFavorite(v)) badges.push('<span class="badge saved">⭐ 已收藏</span>');
  if (v.date) badges.push(`<span class="badge">📅 ${v.date}</span>`);
  v.tags.forEach(t => badges.push(`<span class="badge tag">${t}</span>`));

  const actressText = v.actresses.length > 0
    ? v.actresses.map(a => `<strong>${a}</strong>`).join('、')
    : '<span style="color:var(--text-mute)">未知</span>';

  const isJable = currentSourceOf(v) === 'jable';
  const coverBlock = isJable
    ? `<div class="media-col">
         <div class="jplayer" id="jp" data-state="cover">
         <div class="jp-cover" id="jpCover">
           <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" ${isJable ? '' : 'data-no-proxy="1"'}
             onerror="this.style.display='none'">
           <div class="jp-play-icon">▶</div>
         </div>
         <video id="jpVideo" playsinline preload="auto" poster="${p(v.cover)}"></video>
         <div class="jp-loading" id="jpLoading">⏳ 加载中...</div>
         <div class="jp-progress" id="jpProgress">
           <div class="jp-buffered" id="jpBuffered"></div>
           <div class="jp-played" id="jpPlayed"></div>
         </div>
         <div class="jp-bar">
           <button class="jp-btn" id="jpPlay" title="播放/暂停">▶️</button>
           <div class="jp-volume">
             <button class="jp-btn" id="jpMute" title="静音/取消">🔊</button>
             <div class="jp-vol-slider"><input type="range" id="jpVol" min="0" max="1" step="0.05" value="1"></div>
           </div>
           <span class="jp-time" id="jpCur">0:00</span>
           <span class="jp-time" style="opacity:0.6">/</span>
           <span class="jp-time" id="jpDur">0:00</span>
           <span class="jp-spacer"></span>
           <div class="jp-speed">
             <button class="jp-btn" id="jpSpeedBtn" title="倍速">1x</button>
             <div class="jp-menu" id="jpSpeedMenu"></div>
           </div>
           <div class="jp-quality">
             <button class="jp-btn" id="jpQualBtn" title="画质">自动</button>
             <div class="jp-menu" id="jpQualMenu"></div>
           </div>
             <button class="jp-btn" id="jpFs" title="全屏">⛶</button>
           </div>
         </div>
         <div class="jp-seekbar">
           <button class="jp-seek-btn" data-sec="-600" title="后退10分钟">⏪10m</button>
          <button class="jp-seek-btn" data-sec="-60" title="后退1分钟">⏪1m</button>
          <button class="jp-seek-btn" data-sec="-5" title="后退5秒">⏪5s</button>
           <span class="jp-seek-cur" id="jpSeekCur">0:00</span>
           <button class="jp-seek-btn" data-sec="5" title="快进5秒">5s⏩</button>
           <button class="jp-seek-btn" data-sec="60" title="快进1分钟">1m⏩</button>
           <button class="jp-seek-btn" data-sec="600" title="快进10分钟">10m⏩</button>
         </div>
       </div>`
    : `<div class="media-col"><div class="cover-wrap" onclick="(function(w){w.classList.contains('preview-on')?w.classList.remove('preview-on'):(w.classList.add('preview-on'),w.querySelector('video').play().catch(function(){}))})(this)">
         <video src="${v.preview || ''}" muted loop playsinline disableRemotePlayback preload="auto"
           poster="${p(v.cover)}"
           onerror="this.style.display='none'"></video>
         <div class="cover">
            <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-no-proxy="1"
               onerror="this.parentElement.innerHTML='<div class=placeholder>封面加载失败</div>'">
         </div>
        </div></div>`;

  $('resultArea').innerHTML = `
    <div class="result-card">
      ${coverBlock}
      <div class="info">
        <div class="info-head">
          <div class="code">${v.code}</div>
          <button class="card-collapse" type="button" data-collapse="card">
            <span class="x">×</span><span class="lbl">收起</span><span class="arr">▾</span>
          </button>
        </div>
        <div class="badges">${badges.join('')}</div>
        <div class="title">${v.title || '（无标题）'}</div>
        <div class="meta">
          <strong>女优</strong>：${actressText}<br>
          <strong>发布日期</strong>：${v.date || '—'}
        </div>
        <div class="actions">
          <a class="btn btn-primary" href="${v.url}" target="_blank" rel="noopener">▶️ 去 ${isJable?'Jable':'MissAV'} 观看</a>
          <button class="btn btn-ghost" onclick="rollOne()">🎲 再抽一部</button>
          <button class="btn btn-ghost" onclick="copyCode('${v.code}')">📋 复制番号</button>
          <button class="btn btn-ghost" onclick="toggleFavorite()">${isFavorite(v) ? '⭐ 取消收藏' : '☆ 收藏'}</button>
        </div>
      </div>
    </div>`;
  if (isJable) {
    const cover = $('jpCover');
    if (cover) cover.onclick = () => {
      $('jp').setAttribute('data-state', 'play');
      initJplayer(v);
    };
  }
}

// ── jable 播放器 ──
let _jpHls = null, _jpVideo = null;
function fmtTime(s) {
  if (!s || !isFinite(s)) return '0:00';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return (h > 0 ? h + ':' + String(m).padStart(2,'0') : m) + ':' + String(sec).padStart(2,'0');
}
function initJplayer(v) {
  // 清理旧实例
  if (_jpHls) { try { _jpHls.destroy(); } catch(e){} _jpHls = null; }
  const video = $('jpVideo');
  const jp = $('jp');
  _jpVideo = video;
  const loading = $('jpLoading');
  const playBtn = $('jpPlay');
  const curEl = $('jpCur'), durEl = $('jpDur');
  const progress = $('jpProgress'), played = $('jpPlayed'), buffered = $('jpBuffered');
  const speedBtn = $('jpSpeedBtn'), speedMenu = $('jpSpeedMenu');
  const qualBtn = $('jpQualBtn'), qualMenu = $('jpQualMenu');
  const muteBtn = $('jpMute'), volSlider = $('jpVol');
  const fsBtn = $('jpFs');

  loading.classList.remove('hide');
  video.volume = 1; video.muted = false; // 点击触发,可有声播放

  // 倍速菜单 — click 切换(避免 hover 间隙导致菜单消失)
  const speedWrap = speedBtn.parentElement;   // .jp-speed
  const qualWrap = qualBtn.parentElement;      // .jp-quality
  function closeMenus() { speedWrap.classList.remove('open'); qualWrap.classList.remove('open'); }
  speedBtn.onclick = (e) => { e.stopPropagation(); qualWrap.classList.remove('open'); speedWrap.classList.toggle('open'); };
  qualBtn.onclick = (e) => { e.stopPropagation(); speedWrap.classList.remove('open'); qualWrap.classList.toggle('open'); };
  // 点外部关闭
  jp.addEventListener('click', (e) => { if (!e.target.closest('.jp-speed,.jp-quality')) closeMenus(); });

  const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5];
  speedMenu.innerHTML = speeds.map(s => `<button class="jp-menu-item${s===1?' active':''}" data-s="${s}">${s}x</button>`).join('');
  speedMenu.querySelectorAll('.jp-menu-item').forEach(b => {
    b.onclick = (e) => {
      e.stopPropagation();
      const s = parseFloat(b.dataset.s);
      video.playbackRate = s;
      // 高倍速联动:动态加大 hls.js 缓冲,提前预载分片
      if (_jpHls) {
        _jpHls.config.maxBufferLength = Math.max(120, s * 120);
        _jpHls.config.maxMaxBufferLength = Math.max(600, s * 600);
      }
      speedBtn.textContent = s + 'x';
      speedMenu.querySelectorAll('.jp-menu-item').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      speedWrap.classList.remove('open');
    };
  });

  function buildQualityMenu(levels) {
    if (!levels || levels.length === 0) {
      qualBtn.textContent = '原画';
      qualMenu.innerHTML = '<button class="jp-menu-item active">原画</button>';
      qualMenu.querySelector('.jp-menu-item').onclick = (e) => { e.stopPropagation(); qualWrap.classList.remove('open'); };
      return;
    }
    // 按 bitrate 降序排(最高清在前)
    const sorted = levels.slice().sort((a,b) => (b.bitrate||b.height||0) - (a.bitrate||a.height||0));
    const items = ['<button class="jp-menu-item" data-lvl="-1">自动(最高)</button>'];
    sorted.forEach((lv, i) => {
      const label = lv.height ? lv.height + 'p' : ('L' + (lv.bitrate?Math.round(lv.bitrate/1000)+'k':i));
      items.push(`<button class="jp-menu-item" data-lvl="${lv.index ?? i}">${label}</button>`);
    });
    qualMenu.innerHTML = items.join('');
    qualBtn.textContent = '自动';
    qualMenu.querySelectorAll('.jp-menu-item').forEach(b => {
      b.onclick = (e) => {
        e.stopPropagation();
        const lvl = parseInt(b.dataset.lvl);
        if (_jpHls) { _jpHls.currentLevel = lvl; }
        qualMenu.querySelectorAll('.jp-menu-item').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        qualBtn.textContent = b.textContent;
        qualWrap.classList.remove('open');
      };
    });
    // 默认选最高清(-1 = auto, 但配置里强制 capLevelToPlayerSize=false 已让自动选最高)
  }

  const src = v.preview;
  const isHls = /\.m3u8(\?|#|$)/i.test(src);
  let hlsReady = false;

  if (isHls && window.Hls && Hls.isSupported()) {
    const hls = new Hls({
      capLevelToPlayerSize: false,  // 不根据播放器尺寸降画质 → 始终最高清
      startLevel: -1,               // 自动选最高起步
      maxBufferLength: 120,         // 大缓冲,应对高倍速消耗
      maxMaxBufferLength: 600,
      maxBufferSize: 60 * 1000 * 1000, // 60MB,高倍速预载更多分片
      backBufferLength: 30,
      enableWorker: true,
      lowLatencyMode: false,
      abrEwmaDefaultEstimate: 1000000,
      // 分片 404 时不无限重试,跳过坏分片继续播放
      fragLoadingMaxRetry: 2,
      fragLoadingRetryDelay: 500,
      fragLoadingMaxRetryTimeout: 2000,
      manifestLoadingMaxRetry: 2,
      levelLoadingMaxRetry: 2,
    });
    _jpHls = hls;
    hls.loadSource(src);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, function(_, data) {
      hlsReady = true;
      buildQualityMenu(data.levels);
      // 强制最高画质
      hls.currentLevel = -1;
      loading.classList.add('hide');
      video.play().catch(function(){});
    });
    hls.on(Hls.Events.LEVELS_UPDATED, function(_, data) {
      if (!hlsReady) { hlsReady = true; buildQualityMenu(data.levels); hls.currentLevel = -1; loading.classList.add('hide'); }
    });
    hls.on(Hls.Events.ERROR, function(_, data) {
      // 分片 404:跳过坏分片,不卡死
      if (data.details === Hls.ErrorDetails.FRAG_LOAD_ERROR || data.details === Hls.ErrorDetails.FRAG_PARSING_ERROR) {
        // 非致命,让 hls.js 自动跳过
        return;
      }
      if (data.fatal) {
        // 网络/媒体错误:尝试恢复
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        } else {
          loading.textContent = '⚠️ 加载失败';
          loading.classList.remove('hide');
        }
      }
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Safari 原生 HLS
    video.src = src;
    video.addEventListener('loadedmetadata', () => { loading.classList.add('hide'); buildQualityMenu(null); }, {once:true});
    video.play().catch(function(){});
  } else {
    // 兜底:直接给 src(某些 Chrome 130+ 原生支持)
    video.src = src;
    video.addEventListener('loadedmetadata', () => { loading.classList.add('hide'); buildQualityMenu(null); }, {once:true});
    video.addEventListener('error', () => { loading.textContent = '⚠️ 不支持 HLS'; loading.classList.remove('hide'); });
    video.play().catch(function(){});
  }

  // 播放/暂停
  playBtn.onclick = () => {
    if (video.paused) video.play(); else video.pause();
  };
  video.addEventListener('play', () => { playBtn.textContent = '⏸'; jp.classList.remove('jp-paused'); });
  video.addEventListener('pause', () => { playBtn.textContent = '▶️'; jp.classList.add('jp-paused'); });

  // 音量
  function updateMuteIcon() {
    if (video.muted || video.volume === 0) muteBtn.textContent = '🔇';
    else if (video.volume < 0.5) muteBtn.textContent = '🔉';
    else muteBtn.textContent = '🔊';
  }
  muteBtn.onclick = () => {
    video.muted = !video.muted;
    if (!video.muted && video.volume === 0) { video.volume = 0.5; volSlider.value = 0.5; }
    volSlider.value = video.muted ? 0 : video.volume;
    updateMuteIcon();
  };
  volSlider.oninput = () => {
    const val = parseFloat(volSlider.value);
    video.volume = val;
    video.muted = val === 0;
    updateMuteIcon();
  };
  updateMuteIcon();
  video.addEventListener('loadedmetadata', () => { durEl.textContent = fmtTime(video.duration); });
  video.addEventListener('timeupdate', () => {
    curEl.textContent = fmtTime(video.currentTime);
    if (video.duration) played.style.width = (video.currentTime / video.duration * 100) + '%';
  });
  video.addEventListener('progress', () => {
    if (video.buffered.length > 0 && video.duration) {
      buffered.style.width = (video.buffered.end(video.buffered.length-1) / video.duration * 100) + '%';
    }
  });
  video.addEventListener('waiting', () => loading.classList.remove('hide'));
  video.addEventListener('playing', () => loading.classList.add('hide'));

  // 进度条拖动跳转
  let dragging = false;
  function seekAt(e) {
    const rect = progress.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    if (video.duration) video.currentTime = ratio * video.duration;
  }
  progress.onmousedown = (e) => { dragging = true; seekAt(e); e.preventDefault(); };
  document.addEventListener('mousemove', (e) => { if (dragging) seekAt(e); });
  document.addEventListener('mouseup', () => { dragging = false; });
  progress.onclick = null; // mousedown 已处理,避免拖动末尾 click 跳回

  // 跳转按钮组(seekbar 在 jplayer 外层)
  const seekbar = document.querySelector('.jp-seekbar');
  const seekCur = document.getElementById('jpSeekCur');
  if (seekbar) {
    seekbar.querySelectorAll('.jp-seek-btn').forEach(btn => {
      btn.onclick = () => {
        const sec = parseInt(btn.dataset.sec);
        if (video.duration) video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + sec));
      };
    });
  }
  video.addEventListener('timeupdate', () => { if (seekCur) seekCur.textContent = fmtTime(video.currentTime); });

  // 全屏(Fullscreen API)
  fsBtn.onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else jp.requestFullscreen().catch(()=>{});
  };
  document.addEventListener('fullscreenchange', () => {
    fsBtn.textContent = document.fullscreenElement ? '🗙' : '⛶';
  });

  // 销毁旧监听:重建时清理(简单做法 — 给 video 加标记)
  video._jpBound = true;
}

function renderHistory() {
  if (state.history.length === 0) { $('historyArea').style.display = 'none'; return; }
  $('historyArea').style.display = 'block';
  $('historyGrid').innerHTML = state.history.map(v => `
    <div class="hist-card" onclick="showFromHistory('${v.code}')">
      <div class="img-wrap">
        <img src="${currentSourceOf(v) === 'jable' ? p(v.cover) : (v.cover || '')}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" ${currentSourceOf(v) === 'jable' ? '' : 'data-no-proxy="1"'}
          onerror="this.parentElement.style.background='var(--border)';this.style.display='none'">
      </div>
      <div class="hist-code">${v.code}</div>
      <div class="hist-title">${v.title.slice(0, 30) || '—'}</div>
    </div>
  `).join('');
}

// hover 触发后挂载 hls.js(避免一次挂 218 个实例)
function mountHls(video, src) {
  if (!src || !video) return;
  if (video.dataset.hlsMounted === '1') {
    video.play().catch(() => {});
    return;
  }
  video.dataset.hlsMounted = '1';
  video.muted = true;
  // MP4 / WebM / 其他原生支持的视频格式:直接给 src
  var isHls = /\.m3u8(\?|#|$)/i.test(src) || src.indexOf('application/vnd.apple.mpegurl') > -1;
  if (!isHls) {
    video.src = src;
    video.addEventListener('error', function() {
      // mp4 404 之类:仅隐藏视频元素本身,保留封面
      video.style.display = 'none';
      video.classList.add('hls-failed');
    });
    video.play().catch(function(){});
    return;
  }
  // M3U8: Safari 原生支持
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = src;
    video.play().catch(() => {});
    return;
  }
  // 其他浏览器用 hls.js
  if (window.Hls && Hls.isSupported()) {
    var hls = new Hls();
    hls.loadSource(src);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, function(_, data) {
      if (data.fatal) {
        video.style.display = 'none';
        video.classList.add('hls-failed');
      }
    });
    video.play().catch(function(){});
  } else {
    video.src = src;
    video.play().catch(function(){});
  }
}

document.addEventListener('mouseover', function(e) {
  const card = e.target.closest('.browse-card,.hist-card,.trend-card');
  if (card) {
    const v = card.querySelector('video[data-hls-src]');
    if (v) { mountHls(v, v.dataset.hlsSrc); return; }
  }
  const v = e.target.closest('video[data-hls-src]');
  if (v) mountHls(v, v.dataset.hlsSrc);
});
document.addEventListener('mouseenter', function(e) {
  const card = e.target.closest && e.target.closest('.browse-card,.hist-card,.trend-card');
  if (card) {
    const v = card.querySelector('video[data-hls-src]');
    if (v) { mountHls(v, v.dataset.hlsSrc); return; }
  }
  const v = e.target.closest && e.target.closest('video[data-hls-src]');
  if (v) mountHls(v, v.dataset.hlsSrc);
}, true);

// 热门卡片:离开时暂停预览
document.addEventListener('mouseout', function(e) {
  const card = e.target.closest('.trend-card');
  if (!card) return;
  if (e.relatedTarget && card.contains(e.relatedTarget)) return;
  const v = card.querySelector('video');
  if (v) { try { v.pause(); } catch (e) {} }
});

// 热门卡片点击:jable 在结果区显示(需要本地有数据),missav 打开外链
document.addEventListener('click', function(e) {
  const card = e.target.closest('.trend-card');
  if (!card) return;
  if (e.target.closest('.card-collapse')) return; // 收起按钮不触发
  const code = card.dataset.code;
  if (!code) return;
  if (trendIsJable() && DATA && DATA.videos) {
    const v = DATA.videos.find(x => (x.code || '').toLowerCase() === code);
    if (v) {
      e.preventDefault();
      e.stopPropagation();
      state.current = v;
      state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
      saveHistory();
      renderResult();
      renderHistory();
      scheduleSyncSave();
      // 滚到结果区
      $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
  }
  // missav 或 jable 本地没找到:开新标签
  const url = card.dataset.url;
  if (url) window.open(url, '_blank', 'noopener');
});

function showFromHistory(code) {
  const v = state.history.find(h => h.code === code) || DATA.videos.find(x => x.code === code);
  if (v) { state.current = v; renderResult(); }
}

function copyCode(code) {
  navigator.clipboard.writeText(code).then(() => {
    const btn = event.target;
    const old = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = old, 1000);
  });
}

function renderFavorites() {
  const pairs = [
    ['missav', $('missavFavArea'), $('missavFavGrid'), state.favoritesMissav],
    ['jable', $('jableFavArea'), $('jableFavGrid'), state.favoritesJable],
  ];
  pairs.forEach(([src, area, grid, list]) => {
    if (!list.length) { area.style.display = 'none'; grid.innerHTML = ''; return; }
    area.style.display = 'block';
    const isJableFav = (src === 'jable');
    grid.innerHTML = list.map(v => {
      const externalUrl = v.url || '';
      const extBtn = externalUrl
        ? `<a class="ext-link" href="${externalUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗 打开 ${isJableFav ? 'Jable' : 'MissAV'}</a>`
        : '';
      return `
      <div class="fav-card" onclick="openFavorite('${src}','${v.code}')">
        <div class="img-wrap">
          <img src="${src === 'jable' ? p(v.cover) : (v.cover || '')}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" ${src === 'jable' ? '' : 'data-no-proxy="1"'}
               onerror="this.style.display='none'">
        </div>
        <div class="info">
          <div class="code">${v.code}</div>
          <div class="title">${v.title || '（无标题）'}</div>
          <div class="meta">
            ${extBtn}
            <button class="remove" onclick="event.stopPropagation(); removeFavorite('${src}','${v.code}')">移除</button>
          </div>
        </div>
      </div>`;
    }).join('');
  });
}

function saveFavorites(src) {
  try { localStorage.setItem(favStorageKey(src), JSON.stringify(favListForSource(src))); } catch(e) {}
}
function loadFavorites() {
  try {
    const a = JSON.parse(localStorage.getItem(favStorageKey('missav')) || '[]');
    const b = JSON.parse(localStorage.getItem(favStorageKey('jable')) || '[]');
    state.favoritesMissav = Array.isArray(a) ? a : [];
    state.favoritesJable = Array.isArray(b) ? b : [];
  } catch(e) {
    state.favoritesMissav = []; state.favoritesJable = [];
  }
  renderFavorites();
}
function toggleFavorite() {
  if (!state.current) return;
  const src = currentSourceOf(state.current);
  const list = favListForSource(src);
  const idx = list.findIndex(v => v.code === state.current.code);
  if (idx >= 0) list.splice(idx, 1);
  else list.unshift(normFavorite(state.current, src));
  if (src === 'jable') state.favoritesJable = list.filter((v,i,a) => a.findIndex(x => x.code === v.code) === i);
  else state.favoritesMissav = list.filter((v,i,a) => a.findIndex(x => x.code === v.code) === i);
  saveFavorites(src);
  renderFavorites();
  // 只更新收藏按钮和徽章,不重建结果卡(避免 Jable 播放器被销毁)
  const favBtn = document.querySelector('.result-card .actions .btn:last-child');
  if (favBtn) favBtn.textContent = isFavorite(state.current) ? '⭐ 取消收藏' : '☆ 收藏';
  const badge = document.querySelector('.result-card .badge.saved');
  if (isFavorite(state.current) && !badge) {
    const badgesEl = document.querySelector('.result-card .badges');
    if (badgesEl) badgesEl.insertAdjacentHTML('beforeend', '<span class="badge saved">⭐ 已收藏</span>');
  } else if (!isFavorite(state.current) && badge) {
    badge.remove();
  }
  updateCount();
  scheduleSyncSave();
}
function removeFavorite(src, code) {
  if (src === 'jable') state.favoritesJable = state.favoritesJable.filter(v => v.code !== code);
  else state.favoritesMissav = state.favoritesMissav.filter(v => v.code !== code);
  saveFavorites(src);
  renderFavorites();
  updateCount();
  if (state.current && currentSourceOf(state.current) === src && state.current.code === code) renderResult();
  scheduleSyncSave();
}
function clearFavorites(src) {
  if (src === 'jable') state.favoritesJable = [];
  else state.favoritesMissav = [];
  localStorage.removeItem(favStorageKey(src));
  renderFavorites();
  updateCount();
  renderResult();
  scheduleSyncSave();
}
function openFavorite(src, code) {
  const list = src === 'jable' ? state.favoritesJable : state.favoritesMissav;
  const fav = list.find(v => v.code === code);
  if (!fav) return;
  function applyFavorite() {
    document.querySelectorAll('#sourceChips .chip').forEach(c => c.classList.remove('active'));
    const chip = document.querySelector(`#sourceChips .chip[data-source="${src}"]`);
    if (chip) chip.classList.add('active');
    state.source = src;
    state.current = fav;
    if ((fav.source || src) !== src) { console.warn('openFavorite: source mismatch', fav, src); return; }
    renderResult();
    scheduleSyncSave();
  }
  if (src === 'jable') {
    if (DATA && DATA.source === 'jable') { applyFavorite(); return; }
    fetch('jable_data.json?_=' + Date.now()).then(r => r.json()).then(d => {
      DATA = d;
      var uniq = {};
      DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
      DATA.actresses = Object.keys(uniq);
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      applyFavorite();
    });
  } else {
    if (DATA && (!DATA.source || DATA.source === 'missav')) { applyFavorite(); return; }
    fetch('picker_data.json?_=' + Date.now()).then(r => r.json()).then(d => {
      DATA = d;
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + (DATA.actresses||[]).length + ' 位女优 · 按空格快速抽';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      applyFavorite();
    });
  }
}

// ---- 持久化 ----
function saveHistory() {
  try {
    localStorage.setItem('missav_picker_history',
      JSON.stringify(state.history.map(v => v.code)));
  } catch(e) {}
}
function loadHistory() {
  try {
    const codes = JSON.parse(localStorage.getItem('missav_picker_history') || '[]');
    state.history = codes
      .map(c => DATA.videos.find(v => v.code === c))
      .filter(Boolean);
    renderHistory();
  } catch(e) {}
}

function clearHistory() {
  state.history = [];
  localStorage.removeItem('missav_picker_history');
  renderHistory();
  scheduleSyncSave();
}

function selectAllActresses() {
  for (const gid of ['savedGrid','rookieGrid','otherGrid']) {
    $(gid).querySelectorAll('.actress-chip').forEach(c => {
      state.actresses.add(c.dataset.actress);
      c.classList.add('active');
    });
  }
  updateCount();
  scheduleSyncSave();
}

function deselectAllActresses() {
  state.actresses.clear();
  document.querySelectorAll('.actress-chip.active').forEach(c => c.classList.remove('active'));
  updateCount();
  scheduleSyncSave();
}

function selectAllTags() {
  document.querySelectorAll('#tagChips .chip').forEach(c => {
    state.tags.add(c.dataset.tag);
    c.classList.add('active');
  });
  updateCount();
  scheduleSyncSave();
}

function deselectAllTags() {
  state.tags.clear();
  document.querySelectorAll('#tagChips .chip').forEach(c => c.classList.remove('active'));
  updateCount();
  scheduleSyncSave();
}

// ---- 事件绑定 ----
// 片源切换
$('sourceChips').addEventListener('click', function(e) {
  var chip = e.target.closest('.chip'); if (!chip) return;
  document.querySelectorAll('#sourceChips .chip').forEach(function(c) { c.classList.remove('active'); });
  chip.classList.add('active');
  var src = chip.dataset.source;
  if (src === state.source) return;
  state.source = src;
  state.current = null;
  state.tags.clear(); state.actresses.clear(); state.type = 'all';
  if (_jpHls) { try { _jpHls.destroy(); } catch(e){} _jpHls = null; }
  if (_jpVideo) { try { _jpVideo.pause(); _jpVideo.removeAttribute('src'); _jpVideo.load(); } catch(e){} _jpVideo = null; }
  $('resultArea').innerHTML = '';
  document.querySelectorAll('#typeChips .chip').forEach(function(c) { c.classList.remove('active'); });
  document.querySelector('#typeChips .chip[data-type="all"]').classList.add('active');
  $('selectedBar').innerHTML = '';
  $('rollBtn').disabled = true;
  $('rollBtn').textContent = '⏳ 加载中...';
  // 切换片源时,刷新热门区
  renderTrending();
  loadTrending();
  if (src === 'jable') {
    DATA = null; IDX = null;
    $('tagChips').innerHTML = '';
    $('excludeChips').innerHTML = '';
    ['savedGrid','rookieGrid','otherGrid'].forEach(function(id) { $(id).innerHTML = ''; });
    fetch('jable_data.json?_=' + Date.now()).then(function(r) { return r.json(); }).then(function(d) {
      DATA = d;
      // jable_data.json schema 是 {source, videos:[...]},顶层没有 actresses
      // 从 videos 提取 unique 女优
      var uniq = {};
      DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
      DATA.actresses = Object.keys(uniq);
      $('rollBtn').disabled = false; $('rollBtn').textContent = '🎲 随机抽一部';
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      scheduleSyncSave();
    });
  } else {
    DATA = null; IDX = null;
    $('tagChips').innerHTML = '';
    ['savedGrid','rookieGrid','otherGrid'].forEach(function(id) { $(id).innerHTML = ''; });
    fetch('picker_index.json?_=' + Date.now()).then(function(r) { return r.json(); }).then(function(d) {
      IDX = d; init('index');
    });
  }
});

$('typeChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  state.type = chip.dataset.type;
  renderTagChips();
  updateCount();
  scheduleSyncSave();
});

$('tagChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  const tag = chip.dataset.tag;
  if (state.tags.has(tag)) { state.tags.delete(tag); chip.classList.remove('active'); }
  else { state.tags.add(tag); chip.classList.add('active'); }
  updateCount();
  scheduleSyncSave();
});

$('excludeChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  const tag = chip.dataset.extag;
  if (state.excludeTags.has(tag)) { state.excludeTags.delete(tag); chip.classList.remove('active'); }
  else { state.excludeTags.add(tag); chip.classList.add('active'); }
  updateCount();
  scheduleSyncSave();
});

for (const gid of ['savedGrid','rookieGrid','otherGrid']) {
  $(gid).addEventListener('click', (e) => {
    const chip = e.target.closest('.actress-chip'); if (!chip) return;
    const name = chip.dataset.actress;
    if (state.actresses.has(name)) {
      state.actresses.delete(name);
      chip.classList.remove('active');
    } else {
      state.actresses.add(name);
      chip.classList.add('active');
    }
    updateCount();
    scheduleSyncSave();
  });
}

$('actressSearch').addEventListener('input', (e) => {
  renderActressGrid(e.target.value);
});

$('rollBtn').addEventListener('click', rollOne);

let browsePage = 0;
const BROWSE_PER = 30;

function openBrowse() {
  browsePage = 0;
  renderBrowse();
  $('browseArea').style.display = 'block';
  $('browseArea').scrollIntoView({behavior:'smooth'});
  scheduleSyncSave();
}

function browseGo(page) {
  browsePage = page;
  renderBrowse();
  $('browseArea').scrollIntoView({behavior:'smooth'});
  scheduleSyncSave();
}

function renderBrowse() {
  const cands = getCandidates();
  const totalPages = Math.ceil(cands.length / BROWSE_PER);
  const start = browsePage * BROWSE_PER;
  const end = Math.min(start + BROWSE_PER, cands.length);
  const show = cands.slice(start, end);
  $('browseTitle').textContent = `🖼 ${cands.length} 部作品 · 第 ${browsePage + 1} / ${totalPages} 页`;
  $('browseGrid').innerHTML = show.map(v => `
    <div class="browse-card" onclick="window.open('${v.url}','_blank')">
      <div class="bc-cover">
        <img src="${currentSourceOf(v) === 'jable' ? p(v.cover) : (v.cover || '')}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer" ${currentSourceOf(v) === 'jable' ? '' : 'data-no-proxy="1"'}
          onerror="this.parentElement.style.background='var(--border)';this.style.display='none'">
        <div class="bc-preview">
          <video data-hls-src="${previewUrl(v)}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none"
            poster="${p(v.cover)}"></video>
        </div>
      </div>
      <div class="bc-info">
        <div class="bc-code">${v.code}</div>
        <div class="bc-title">${v.title}</div>
      </div>
    </div>
  `).join('');

  // 渲染分页器
  const pager = $('browsePager');
  if (totalPages <= 1) { pager.innerHTML = ''; return; }
  let html = '';
  html += `<button class="btn btn-ghost" onclick="browseGo(${browsePage - 1})" ${browsePage === 0 ? 'disabled' : ''} style="font-size:11px;padding:4px 10px;">◀ 上一页</button>`;
  // 页码: 最多显示 7 个
  let pStart = Math.max(0, browsePage - 3);
  let pEnd = Math.min(totalPages, pStart + 7);
  if (pEnd - pStart < 7) pStart = Math.max(0, pEnd - 7);
  for (let p = pStart; p < pEnd; p++) {
    const active = p === browsePage ? ' style="background:var(--primary);color:#fff;"' : '';
    html += `<button class="btn btn-ghost" onclick="browseGo(${p})"${active} style="font-size:11px;padding:4px 10px;">${p + 1}</button>`;
  }
  html += `<button class="btn btn-ghost" onclick="browseGo(${browsePage + 1})" ${browsePage >= totalPages - 1 ? 'disabled' : ''} style="font-size:11px;padding:4px 10px;">下一页 ▶</button>`;
  pager.innerHTML = html;
}

document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && e.target === document.body) {
    e.preventDefault(); rollOne();
  }
});

// ---- 启动 ----
function init(stage) {
  if (stage === 'index') {
    // 索引已加载(actresses/groups/avatars/display/tags),立即渲染 UI
    $('stats').textContent = `📊 ${IDX.video_count} 部作品 · ${IDX.actresses.length} 位女优 · ${IDX.tags.length} 个标签 · 按空格快速抽`;
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    // 热门板块(随当前片源)
    loadTrending();
    // 异步加载完整数据
    $('rollBtn').disabled = true;
    $('rollBtn').textContent = '⏳ 加载作品数据...';
    fetch(location.pathname.replace(/[^/]*$/, '') + 'picker_data.json?_=' + Date.now())
      .then(r => r.json())
      .then(d => {
        DATA = d;
        $('rollBtn').disabled = false;
        $('rollBtn').textContent = '🎲 随机抽一部';
        updateCount();
      })
      .catch(e => { $('stats').textContent = '加载失败,请刷新'; });
  } else {
    // file:// 一次性内嵌
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${DATA.actresses.length} 位女优 · ${DATA.tags.length} 个标签 · 按空格快速抽`;
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    updateCount();
  }
}

// 让 getCandidates 能同时工作于 DATA 未加载时(返回空)
const origGetCandidates = getCandidates;
getCandidates = function() {
if (!DATA) return [];
  return origGetCandidates();
};

// ---- 每日 / 每周热门 ----
let trendPeriod = 'daily';
let trendCache = { missav: { daily: null, weekly: null }, jable: { daily: null, weekly: null } };
let trendLoading = false;

function trendSource() {
  // 跟随当前片源;选 missav/jable 与 state.source 一致
  return state && state.source === 'jable' ? 'jable' : 'missav';
}
function trendLabel() { return trendSource() === 'jable' ? 'Jable.TV' : 'MissAV'; }
function trendIsJable() { return trendSource() === 'jable'; }

function renderTrending() {
  const src = trendSource();
  const data = trendCache[src] && trendCache[src][trendPeriod];
  const grid = $('trendingGrid');
  $('trendingSource').textContent = trendLabel();
  $('trendingEmoji').textContent = trendIsJable() ? '🪐' : '🔥';
  $('trendingHeading').textContent = (trendPeriod === 'daily' ? '今日热门' : '本周热门');
  if (!data) {
    grid.innerHTML = '<div class="trending-empty">正在拉取…</div>';
    return;
  }
  if (!data.items || data.items.length === 0) {
    const err = data.error ? `（${data.error}）` : '';
    grid.innerHTML = `<div class="trending-empty">暂时拉不到 ${trendLabel()} 热门 ${err}<br><span style="opacity:.7">先看下方筛选区，或稍后点 ↻ 刷新</span></div>`;
    return;
  }
  grid.innerHTML = data.items.slice(0, 20).map((it, i) => {
    const cover = it.cover || '';
    const code = (it.code || '').toLowerCase();
    const isJ = trendIsJable();
    // missav 预览走本地代理(免 fourhoi 403); jable 走本地 /play 代理
    const preview = isJ
      ? (code ? `/play/${code}/playlist.m3u8` : '')
      : (code ? `/trend_preview/missav/${code}.mp4` : '');
    const dataKind = isJ ? 'hls' : (code ? 'mp4' : '');
    const safeTitle = (it.title || it.code || '').replace(/"/g, '&quot;');
    const safeUrl = it.url || '';
    return `
      <div class="trend-card ${isJ ? 'is-jable' : ''}" data-code="${code}" data-url="${safeUrl.replace(/"/g, '&quot;')}" title="${safeTitle}">
        <div class="cover">
          <span class="rank">${i + 1}</span>
          <img src="${cover}" alt="${it.code || ''}" loading="lazy" referrerpolicy="no-referrer" data-no-proxy="1"
               onerror="this.parentElement.style.background='var(--border)';this.style.display='none'">
          <div class="preview">
            <video data-hls-src="${preview}" data-kind="${dataKind}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none" poster="${cover}"></video>
          </div>
        </div>
        <div class="info">
          <div class="code">${it.code || ''}</div>
          <div class="title">${(it.title || '（无标题）').slice(0, 60)}</div>
        </div>
      </div>`;
  }).join('');
}

async function loadTrending(force) {
  if (trendLoading) return;
  trendLoading = true;
  const src = trendSource();
  const period = trendPeriod;
  const url = `/trending?source=${encodeURIComponent(src)}&period=${encodeURIComponent(period)}${force ? '&_=' + Date.now() : ''}`;
  try {
    const r = await fetch(url);
    const data = await r.json();
    trendCache[src] = trendCache[src] || { daily: null, weekly: null };
    trendCache[src][period] = data;
  } catch (e) {
    trendCache[src] = trendCache[src] || { daily: null, weekly: null };
    trendCache[src][period] = { source: src, period, items: [], error: '网络错误' };
  } finally {
    trendLoading = false;
    renderTrending();
  }
}

document.querySelectorAll('.period-chip[data-period]').forEach(b => {
  b.addEventListener('click', () => {
    if (b.classList.contains('active')) return;
    document.querySelectorAll('.period-chip[data-period]').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    trendPeriod = b.dataset.period;
    renderTrending();
    const cached = trendCache[trendSource()] && trendCache[trendSource()][trendPeriod];
    if (!cached) loadTrending();
  });
});
document.getElementById('trendingRefresh').addEventListener('click', () => loadTrending(true));

// 收起 / 展开
(function() {
  var KEY = 'missav_picker_trend_collapsed';
  var section = document.getElementById('trending');
  var btn = document.getElementById('trendingToggle');
  function apply(collapsed) {
    section.classList.toggle('collapsed', collapsed);
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.title = collapsed ? '展开' : '收起';
    btn.querySelector('.lbl').textContent = collapsed ? '展开' : '收起';
    try { localStorage.setItem(KEY, collapsed ? '1' : '0'); } catch (e) {}
  }
  try {
    if (localStorage.getItem(KEY) === '1') apply(true);
  } catch (e) {}
  btn.addEventListener('click', function() {
    apply(!section.classList.contains('collapsed'));
  });
})();

// 单卡收起(热门 + 结果卡 + 筛选区) — 委托 + 阻止默认链接跳转(capture 阶段,先于内层 onclick)
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.card-collapse');
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  const card = btn.closest('.result-card,.filters,.history');
  if (!card) return;
  card.classList.toggle('is-collapsed');
  const collapsed = card.classList.contains('is-collapsed');
  const lbl = btn.querySelector('.lbl');
  if (lbl) lbl.textContent = collapsed ? '展开' : '收起';
}, true);

if (location.protocol === 'file:') {
  DATA = JSON.parse(document.getElementById('DATA').textContent);
  init('full');
  // file:// 模式不做局域网同步
} else {
  IDX = null;
  fetch(location.pathname.replace(/[^/]*$/, '') + 'picker_index.json?_=' + Date.now())
    .then(r => r.json())
    .then(async d => {
      IDX = d;
      init('index');
      // 首次拉取共享状态,之后轮询保持 PC/手机同步
      await pullSyncState();
      setInterval(pullSyncState, 2500);
    })
    .catch(e => $('stats').textContent = '加载失败,请刷新');
}
