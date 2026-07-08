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
  favoriteActresses: new Set(),
  removedFavorites: {},
  removedVideos: {},
  removedVideoSnapshots: {},
};

function currentSourceOf(v) {
  return (v && (v.source || (DATA && DATA.source) || state.source)) || 'missav';
}
function coverUrl(v) {
  // v2 统一走本地 /img/ 代理。
  // jable 封面当前 CDN 在本机不可达，所以同时试 fourhoi 的 cover-t.jpg，
  // 失败时再回退到 jable 自带 cover。
  const code = (v.code || '').toLowerCase();
  if (currentSourceOf(v) === 'jable' && (v.cover || code)) {
    const lowConfidence = (!v.preview && !(v.date || '').trim() && (!Array.isArray(v.actresses) || v.actresses.length === 0) && ((v.title || '').trim().toUpperCase() === (v.code || '').trim().toUpperCase()));
    if (lowConfidence && code) {
      return p(`fourhoi.com/${code}/cover-t.jpg`);
    }
    return p(v.cover || `fourhoi.com/${code}/cover-t.jpg`);
  }
  if (currentSourceOf(v) === 'missav' && code) {
    return p(`fourhoi.com/${code}/cover-t.jpg`);
  }
  return p(v.cover || '');
}
function fallbackCoverUrl(v) {
  const code = (v && v.code || '').toLowerCase();
  return code ? p(`fourhoi.com/${code}/cover-t.jpg`) : '';
}
function handleCoverLoad(img) {
  if (!img || img.naturalWidth !== 1 || img.naturalHeight !== 1 || img.dataset.placeholderChecked) return;
  img.dataset.placeholderChecked = '1';
  const fallback = img.dataset.fallbackCover;
  if (fallback && img.src !== fallback) img.src = fallback;
}
const _coverPrewarmSeen = new Set();
function prewarmCover(url) {
  if (!url || _coverPrewarmSeen.has(url)) return;
  _coverPrewarmSeen.add(url);
  const img = new Image();
  img.decoding = 'async';
  img.loading = 'eager';
  img.referrerPolicy = 'no-referrer';
  img.src = url;
}
function prewarmCoverBatch(items, limit) {
  (items || []).slice(0, limit || 20).forEach(v => {
    prewarmCover(coverUrl(v));
    prewarmCover(fallbackCoverUrl(v));
  });
}
function previewUrl(v) {
  const code = (v && v.code || '').toLowerCase();
  if (currentSourceOf(v) === 'jable' && code) {
    return p(`fourhoi.com/${code}/preview.mp4`);
  }
  return p(v.preview || '');
}
function escHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));
}
function jsArg(value) {
  return escHtml(JSON.stringify(String(value == null ? '' : value)));
}
function normalizeActressToken(s) {
  return String(s == null ? '' : s).toLowerCase().replace(/\s+/g, '').trim();
}
function actressNameTokens(name) {
  const raw = String(name == null ? '' : name).trim();
  if (!raw) return [];
  const parts = raw
    .split(/[()（）,，/｜|]+/)
    .map(s => normalizeActressToken(s))
    .filter(Boolean);
  const all = [normalizeActressToken(raw)].concat(parts);
  return [...new Set(all.filter(Boolean))];
}
function resolveActressName(name) {
  const meta = IDX || DATA || {};
  const actresses = Array.isArray(meta.actresses) ? meta.actresses : [];
  if (!name || !actresses.length) return name;
  if (actresses.includes(name)) return name;
  const wanted = actressNameTokens(name);
  for (const actress of actresses) {
    const tokens = actressNameTokens(actress);
    if (wanted.some(t => tokens.includes(t))) return actress;
  }
  return name;
}
function cssIdent(value) {
  const s = String(value == null ? '' : value);
  if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(s);
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}
function favListForSource(src) {
  return src === 'jable' ? state.favoritesJable : state.favoritesMissav;
}
function favStorageKey(src) {
  return src === 'jable' ? 'missav_picker_favorites_jable_v1' : 'missav_picker_favorites_missav_v1';
}
function readStoredFavorites(src) {
  try {
    const raw = JSON.parse(localStorage.getItem(favStorageKey(src)) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch (e) {
    return [];
  }
}
function favoriteActressesStorageKey() {
  return 'missav_picker_favorite_actresses_v1';
}
function loadFavoriteActresses() {
  try {
    const raw = JSON.parse(localStorage.getItem(favoriteActressesStorageKey()) || '[]');
    state.favoriteActresses = new Set(Array.isArray(raw) ? raw : []);
  } catch (e) { state.favoriteActresses = new Set(); }
}
function saveFavoriteActresses() {
  try { localStorage.setItem(favoriteActressesStorageKey(), JSON.stringify([...state.favoriteActresses])); } catch (e) {}
}
function primaryActress(v) {
  return Array.isArray(v && v.actresses) && v.actresses.length ? resolveActressName(v.actresses[0]) : '';
}
function isFavoriteActress(name) {
  const resolved = resolveActressName(name);
  return !!(resolved && state.favoriteActresses && state.favoriteActresses.has(resolved));
}
function favoriteActressSet() {
  const out = new Set(state.favoriteActresses || []);
  (state.favoritesMissav || []).forEach(v => {
    (Array.isArray(v.actresses) ? v.actresses : []).forEach(a => {
      const resolved = resolveActressName(a);
      if (resolved) out.add(resolved);
    });
  });
  return out;
}
function toggleFavoriteActress(name) {
  const resolved = resolveActressName(name);
  if (!resolved) return;
  if (state.favoriteActresses.has(resolved)) state.favoriteActresses.delete(resolved);
  else state.favoriteActresses.add(resolved);
  saveFavoriteActresses();
  renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
  renderResult();
}
function removedFavoritesStorageKey() {
  return 'missav_picker_removed_favorites_v1';
}
function readRemovedFavorites() {
  try {
    const raw = JSON.parse(localStorage.getItem(removedFavoritesStorageKey()) || '{}');
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  } catch (e) {
    return {};
  }
}
function saveRemovedFavorites() {
  try { localStorage.setItem(removedFavoritesStorageKey(), JSON.stringify(state.removedFavorites || {})); } catch (e) {}
}
function removedVideosStorageKey() {
  return 'missav_picker_removed_videos_v1';
}
function removedVideoSnapshotsStorageKey() {
  return 'missav_picker_removed_video_snapshots_v1';
}
function loadRemovedVideos() {
  try {
    const raw = JSON.parse(localStorage.getItem(removedVideosStorageKey()) || '{}');
    state.removedVideos = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  } catch (e) { state.removedVideos = {}; }
  try {
    const raw = JSON.parse(localStorage.getItem(removedVideoSnapshotsStorageKey()) || '{}');
    state.removedVideoSnapshots = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  } catch (e) { state.removedVideoSnapshots = {}; }
  renderTrash();
}
function saveRemovedVideos() {
  try { localStorage.setItem(removedVideosStorageKey(), JSON.stringify(state.removedVideos || {})); } catch (e) {}
  try { localStorage.setItem(removedVideoSnapshotsStorageKey(), JSON.stringify(state.removedVideoSnapshots || {})); } catch (e) {}
}
function isVideoRemoved(code, src) {
  const key = (src || state.source) + ':' + (code || '').toUpperCase();
  return !!(state.removedVideos && state.removedVideos[key]);
}
function removeVideo(code, src) {
  const source = src || state.source;
  const key = source + ':' + (code || '').toUpperCase();
  state.removedVideos[key] = Date.now();
  const current = state.current && (state.current.code || '').toUpperCase() === (code || '').toUpperCase() ? state.current : null;
  const fromData = DATA && DATA.videos ? DATA.videos.find(v => (v.code || '').toUpperCase() === (code || '').toUpperCase()) : null;
  const snapshot = current || fromData;
  if (snapshot) state.removedVideoSnapshots[key] = Object.assign({}, snapshot, { source: source, removedAt: state.removedVideos[key] });
  saveRemovedVideos();
  fetch('/remove_video', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code, source: source })
  }).catch(e => console.error('remove_video server error:', e));
  updateCount();
  renderTrash();
  scheduleSyncSave();
}
function removeCurrentVideo() {
  if (!state.current) return;
  const v = state.current;
  removeVideo(v.code, currentSourceOf(v));
  // 从 history 和 shortlist 中也移除
  state.history = state.history.filter(h => h.code !== v.code);
  state.shortlist = state.shortlist.filter(s => s.code !== v.code);
  saveHistory();
  renderHistory();
  // 抽下一部
  rollOne();
}
function recentRemovedVideos() {
  const removed = state.removedVideos || {};
  const snaps = state.removedVideoSnapshots || {};
  return Object.keys(removed).map(key => {
    const snap = snaps[key] || {};
    const parts = key.split(':');
    return Object.assign({ source: parts[0] || 'missav', code: parts.slice(1).join(':') }, snap, { key, removedAt: Number(removed[key]) || 0 });
  }).sort((a, b) => b.removedAt - a.removedAt).slice(0, 10);
}
function renderTrash() {
  const grid = $('trashGrid');
  if (!grid) return;
  const items = recentRemovedVideos();
  if (!items.length) {
    grid.innerHTML = '<div class="trending-empty">回收站为空</div>';
    return;
  }
  grid.innerHTML = items.map(v => `
    <div class="trash-card" onclick="openRemovedVideo(${jsArg(v.key)})">
      <div class="thumb"><img src="${escHtml(coverUrl(v))}" alt="${escHtml(v.code)}" loading="lazy" onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else{this.style.display='none';}"></div>
      <div>
        <div class="code">${escHtml(v.code)}</div>
        <div class="title">${escHtml(v.title || v.code)}</div>
        <button class="restore" type="button" onclick="event.stopPropagation(); restoreVideo(${jsArg(v.source)},${jsArg(v.code)})">取消移除</button>
      </div>
    </div>
  `).join('');
}
function openRemovedVideo(key) {
  const v = state.removedVideoSnapshots && state.removedVideoSnapshots[key];
  if (!v) return;
  state.source = v.source || (key || '').split(':')[0] || state.source;
  state.current = v;
  renderResult();
  closeSidebar();
  $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function restoreVideo(src, code) {
  const key = src + ':' + (code || '').toUpperCase();
  const snapshot = state.removedVideoSnapshots[key];
  delete state.removedVideos[key];
  delete state.removedVideoSnapshots[key];
  saveRemovedVideos();
  fetch('/restore_video', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code, source: src, video: snapshot || null })
  }).catch(e => console.error('restore_video server error:', e));
  renderTrash();
  updateCount();
  scheduleSyncSave();
}
function mergeRemovedFavoriteMaps() {
  const merged = {};
  for (const map of arguments) {
    if (!map || typeof map !== 'object' || Array.isArray(map)) continue;
    Object.keys(map).forEach(key => {
      const ts = Number(map[key]) || 0;
      if (ts > (Number(merged[key]) || 0)) merged[key] = ts;
    });
  }
  return merged;
}
function dedupeFavorites(list, src) {
  const seen = new Set();
  return (Array.isArray(list) ? list : []).filter(v => {
    if (!v || !v.code) return false;
    const key = favKey(v, src || currentSourceOf(v));
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
function favoriteUpdatedAt(v) {
  return Number(v && v.favoritedAt) || 0;
}
function mergeRemovedFavorites() {
  state.removedFavorites = mergeRemovedFavoriteMaps(
    readRemovedFavorites(),
    state.removedFavorites || {}
  );
}
function applyRemovedFavorites(list, src) {
  const removed = state.removedFavorites || {};
  return dedupeFavorites(list, src).filter(v => {
    const removedAt = Number(removed[favKey(v, src)]) || 0;
    return !removedAt || favoriteUpdatedAt(v) > removedAt;
  });
}
function mergeFavoriteLists() {
  mergeRemovedFavorites();
  const localMissav = applyRemovedFavorites(readStoredFavorites('missav').concat(state.favoritesMissav), 'missav');
  const localJable = applyRemovedFavorites(readStoredFavorites('jable').concat(state.favoritesJable), 'jable');
  state.favoritesMissav = localMissav;
  state.favoritesJable = localJable;
  saveRemovedFavorites();
}
function favKey(v, src) {
  const source = src || currentSourceOf(v);
  return source + ':' + v.code;
}
function isManualFavorite(v) {
  if (!v) return false;
  const src = currentSourceOf(v);
  return favListForSource(src).some(f => f.code === v.code);
}
function isScrapedFavorite(v) {
  return !!(v && v.is_saved && currentSourceOf(v) === 'missav');
}
function isFavorite(v) {
  return isManualFavorite(v) || isScrapedFavorite(v);
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
    source: src || currentSourceOf(v),
    favoritedAt: Date.now()
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
    removedFavorites: state.removedFavorites || {},
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
    const src = window._SOURCE_SYNC_DISABLED ? state.source : (payload.source || 'missav');
    await loadSourceData(src);
    document.querySelectorAll('#sourceChips .chip').forEach(c => c.classList.remove('active'));
    const chip = document.querySelector(`#sourceChips .chip[data-source="${src}"]`);
    if (chip) chip.classList.add('active');
    state.source = src;
    state.type = payload.type || 'all';
    state.tags = new Set(payload.tags || []);
    state.excludeTags = new Set(payload.excludeTags || []);
    state.actresses = new Set(payload.actresses || []);
    state.removedFavorites = mergeRemovedFavoriteMaps(
      readRemovedFavorites(),
      payload.removedFavorites || {},
      state.removedFavorites || {}
    );
    state.favoritesMissav = applyRemovedFavorites(
      state.favoritesMissav
        .concat(readStoredFavorites('missav'))
        .concat(Array.isArray(payload.favoritesMissav) ? payload.favoritesMissav : []),
      'missav'
    );
    state.favoritesJable = applyRemovedFavorites(
      state.favoritesJable
        .concat(readStoredFavorites('jable'))
        .concat(Array.isArray(payload.favoritesJable) ? payload.favoritesJable : []),
      'jable'
    );
    try {
      localStorage.setItem(favStorageKey('missav'), JSON.stringify(state.favoritesMissav));
      localStorage.setItem(favStorageKey('jable'), JSON.stringify(state.favoritesJable));
      localStorage.setItem(removedFavoritesStorageKey(), JSON.stringify(state.removedFavorites));
    } catch (e) {}
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

    state.current = window._SOURCE_SYNC_DISABLED ? state.current : findVideoByRef(payload.current);
    if (state.current) renderResult(); else $('resultArea').innerHTML = `<div class="empty"><div class="emoji">🎰</div><div>设置筛选条件，点上面的按钮开始随机</div></div>`;
    renderShortlist();
    renderHistory();
    // source 可能在 pullSyncState 后从 missav 切到 jable,需要同步刷新热门区
    if (typeof renderTrending === 'function') renderTrending();
    if (typeof loadTrending === 'function') {
      loadTrending();
      // 如果初始 missav 请求仍在飞,loadTrending() 会因为 trendLoading 直接 return,
      // 延迟补打一枪,确保切到 jable 后一定能真正拉到 jable 热门。
      setTimeout(() => {
        try {
          const srcNow = state.source;
          const cached = trendCache[srcNow] && trendCache[srcNow][trendPeriod];
          if (!cached) loadTrending(true);
        } catch (e) {}
      }, 1200);
    }
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
      mergeFavoriteLists();
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
