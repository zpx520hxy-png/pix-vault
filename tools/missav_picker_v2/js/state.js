import { renderTagChips, renderActressGrid, updateCount } from "./filters.js";
import { renderShortlist } from "./roll.js";
import { renderResult } from "./render.js";
import { renderHistory } from "./history.js";
import { renderFavorites } from "./favorites.js";
import { renderBrowse } from "./browse.js";

const IMG_PROXY = '/img/';

const $ = (id) => document.getElementById(id);
let DATA = window._PICKER_DATA || null;
let IDX = window._PICKER_IDX || null;

// Allow external modules to set DATA/IDX via window
window.__setData = function(d) { window.__setData(d); };
window.__setIdx = function(d) { IDX = d; window._PICKER_IDX = d; };
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
    window.__setData(d);
    var uniq = {};
    DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
    DATA.actresses = Object.keys(uniq);
    $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
  } else {
    if (DATA && (!DATA.source || DATA.source === 'missav')) return;
    const d = await (await fetch('picker_data.json?_=' + Date.now())).json();
    window.__setData(d);
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

export { $, p, rw, currentSourceOf, coverUrl, previewUrl, favListForSource, favStorageKey, favKey, isFavorite, normFavorite, slimVideoRef, exportSyncState, findVideoByRef, loadSourceData, applySyncState, scheduleSyncSave, pullSyncState, state, DATA, IDX };
