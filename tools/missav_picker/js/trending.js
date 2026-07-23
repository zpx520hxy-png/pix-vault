// ---- 每日 / 每周热门 ----
let trendPeriod = 'daily';
let trendCache = { missav: { daily: null, weekly: null }, jable: { daily: null, weekly: null } };
let trendCacheVersion = { missav: { daily: 0, weekly: 0 }, jable: { daily: 0, weekly: 0 } };
let trendLoading = { missav: { daily: false, weekly: false }, jable: { daily: false, weekly: false } };
let trendProgressTimers = { missav: { daily: null, weekly: null }, jable: { daily: null, weekly: null } };
let trendRefreshBatch = null;
let trendLibraryStatus = { missav: null, jable: null };
let trendLibraryStatusTimer = { missav: null, jable: null };
const TREND_SNAPSHOT_KEY = 'missav_picker_trend_snapshots_v1';
const TREND_SNAPSHOT_VERSION = 4;

function isCurrentTrendSnapshot(snapshot) {
  return isTrendSnapshot(snapshot)
    && snapshot.snapshotVersion === TREND_SNAPSHOT_VERSION;
}

function stampTrendSnapshot(snapshot) {
  if (!isTrendSnapshot(snapshot)) return snapshot;
  snapshot.snapshotVersion = TREND_SNAPSHOT_VERSION;
  return snapshot;
}

function restoreTrendSnapshots() {
  try {
    const stored = JSON.parse(localStorage.getItem(TREND_SNAPSHOT_KEY) || '{}');
    ['missav', 'jable'].forEach(source => {
      ['daily', 'weekly'].forEach(period => {
        const snapshot = stored[source] && stored[source][period];
        if (isCurrentTrendSnapshot(snapshot)) trendCache[source][period] = snapshot;
      });
    });
  } catch (e) {}
}

function saveTrendSnapshots() {
  try {
    ['missav', 'jable'].forEach(source => {
      ['daily', 'weekly'].forEach(period => {
        stampTrendSnapshot(trendCache[source] && trendCache[source][period]);
      });
    });
    localStorage.setItem(TREND_SNAPSHOT_KEY, JSON.stringify(trendCache));
  } catch (e) {}
}

function isTrendSnapshot(snapshot) {
  return !!snapshot && Array.isArray(snapshot.items);
}

function trendSnapshotFetchedAt(snapshot) {
  return Number(snapshot && snapshot.fetchedAt) || 0;
}

function getTrendSnapshotsForSync() {
  try {
    return JSON.parse(JSON.stringify(trendCache));
  } catch (e) {
    return null;
  }
}

function applyTrendSnapshotsFromSync(snapshots) {
  if (!snapshots || typeof snapshots !== 'object') return false;
  let changed = false;
  ['missav', 'jable'].forEach(source => {
    ['daily', 'weekly'].forEach(period => {
      const snapshot = snapshots[source] && snapshots[source][period];
      if (!isCurrentTrendSnapshot(snapshot)) return;
      const current = trendCache[source][period];
      if (current && trendSnapshotFetchedAt(snapshot) <= trendSnapshotFetchedAt(current)) return;
      trendCache[source][period] = snapshot;
      changed = true;
    });
  });
  if (changed) {
    saveTrendSnapshots();
    hydrateStoredTrendActresses();
  }
  return changed;
}

async function hydrateStoredTrendActresses() {
  const requests = [];
  ['missav', 'jable'].forEach(source => {
    ['daily', 'weekly'].forEach(period => {
      const snapshot = trendCache[source][period];
      if (!isCurrentTrendSnapshot(snapshot) || !snapshot.items.some(item => !(item.actresses || []).length)) return;
      requests.push({ source, period, snapshot });
    });
  });
  if (!requests.length) return;
  const results = await Promise.all(requests.map(async ({ source, period, snapshot }) => {
    try {
      const response = await fetch('/hydrate_trending_snapshots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, items: snapshot.items })
      });
      const data = await response.json();
      if (!response.ok || !Array.isArray(data.items)) return false;
      const changed = JSON.stringify(snapshot.items) !== JSON.stringify(data.items);
      if (changed) trendCache[source][period] = Object.assign({}, snapshot, { items: data.items });
      return changed;
    } catch (e) {
      return false;
    }
  }));
  if (results.some(Boolean)) {
    saveTrendSnapshots();
    if (typeof scheduleSyncSave === 'function') scheduleSyncSave();
    renderTrending();
  }
}

restoreTrendSnapshots();
hydrateStoredTrendActresses();

function trendSource() {
  // 跟随当前片源;选 missav/jable 与 state.source 一致
  return state && state.source === 'jable' ? 'jable' : 'missav';
}
function trendLabel() { return trendSource() === 'jable' ? 'Jable.TV' : 'MissAV'; }
function trendIsJable() { return trendSource() === 'jable'; }
function isTrendingLoading(source, period) {
  return !!(trendLoading[source] && trendLoading[source][period]);
}
function renderTrendingProgress(progress, source, period) {
  if (trendRefreshBatch && trendRefreshBatch.source === source) {
    trendRefreshBatch.progress[period] = progress || {};
    renderTrendRefreshBatchProgress();
    return;
  }
  if (source !== trendSource() || period !== trendPeriod) return;
  const box = $('trendingProgress');
  const fill = $('trendingProgressFill');
  const label = $('trendingProgressLabel');
  if (!box || !fill || !label) return;
  const attempted = Number(progress && progress.attempted) || 0;
  const total = Number(progress && progress.total) || 0;
  const percent = total ? Math.max(8, Math.min(100, attempted / total * 100)) : 8;
  box.classList.add('active');
  fill.style.width = `${percent}%`;
  label.textContent = '正在同步热门...';
}

function renderTrendRefreshBatchProgress() {
  if (!trendRefreshBatch || trendRefreshBatch.source !== trendSource()) return;
  const box = $('trendingProgress');
  const fill = $('trendingProgressFill');
  const label = $('trendingProgressLabel');
  if (!box || !fill || !label) return;
  const periods = ['daily', 'weekly'];
  const entries = periods.map(period => trendRefreshBatch.progress[period] || {});
  const attempted = entries.reduce((sum, progress) => sum + (Number(progress.attempted) || 0), 0);
  const total = entries.reduce((sum, progress) => sum + (Number(progress.total) || 0), 0);
  const completed = periods.filter(period => trendRefreshBatch.completed.has(period));
  const percent = total ? Math.max(8, Math.min(100, attempted / total * 100)) : (completed.length ? completed.length / periods.length * 100 : 8);
  box.classList.add('active');
  fill.style.width = `${percent}%`;
  label.textContent = completed.length === periods.length
    ? '热门已更新'
    : '正在同步今日和本周热门...';
}

function startTrendRefreshBatch(source) {
  trendRefreshBatch = { source, progress: { daily: {}, weekly: {} }, completed: new Set() };
  renderTrendRefreshBatchProgress();
}

function finishTrendRefreshBatch(source) {
  if (!trendRefreshBatch || trendRefreshBatch.source !== source) return;
  const box = $('trendingProgress');
  const fill = $('trendingProgressFill');
  const label = $('trendingProgressLabel');
  if (box && fill && label && source === trendSource()) {
    box.classList.add('active');
    fill.style.width = '100%';
    label.textContent = '热门已更新';
    setTimeout(() => hideTrendingProgress(source, trendPeriod), 1400);
  }
  trendRefreshBatch = null;
}

function hideTrendingProgress(source, period) {
  if (trendRefreshBatch && trendRefreshBatch.source === source) return;
  if (source !== trendSource() || period !== trendPeriod) return;
  const box = $('trendingProgress');
  if (box) box.classList.remove('active');
}
function startTrendingProgressPolling(source, period) {
  const timer = trendProgressTimers[source][period];
  if (timer) clearInterval(timer);
  const poll = async () => {
    try {
      const response = await fetch(`/trending_progress?source=${encodeURIComponent(source)}&period=${encodeURIComponent(period)}&_=${Date.now()}`);
      renderTrendingProgress(await response.json(), source, period);
    } catch (e) {}
  };
  poll();
  trendProgressTimers[source][period] = setInterval(poll, 400);
}
function stopTrendingProgressPolling(source, period, keepVisible) {
  const timer = trendProgressTimers[source][period];
  if (timer) clearInterval(timer);
  trendProgressTimers[source][period] = null;
  if (!keepVisible) hideTrendingProgress(source, period);
}
function setTrendingAssetProgress(source, period, done, total) {
  if (source !== trendSource() || period !== trendPeriod) return;
  const box = $('trendingProgress');
  const fill = $('trendingProgressFill');
  const label = $('trendingProgressLabel');
  if (!box || !fill || !label) return;
  box.classList.add('active');
  fill.style.width = `${total ? Math.max(8, Math.min(100, done / total * 100)) : 100}%`;
  label.textContent = `加载封面与预览 · ${done}/${total} 个资源已就绪`;
}
function waitForTrendAsset(element, readyEvents, timeoutMs) {
  return new Promise(resolve => {
    if (element.tagName === 'IMG' && element.complete) {
      resolve();
      return;
    }
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      readyEvents.forEach(event => element.removeEventListener(event, finish));
      resolve();
    };
    const timer = setTimeout(finish, timeoutMs);
    readyEvents.forEach(event => element.addEventListener(event, finish, { once: true }));
    if (element.tagName === 'VIDEO') element.load();
  });
}
async function waitForTrendingAssets(source, period) {
  if (source !== trendSource() || period !== trendPeriod) return;
  const images = [...document.querySelectorAll('#trendingGrid .trend-card img')];
  const videos = [...document.querySelectorAll('#trendingGrid .trend-card video')];
  videos.forEach(video => {
    if (!video.src && video.dataset.hlsSrc) video.src = video.dataset.hlsSrc;
    video.preload = 'metadata';
  });
  const assets = [
    ...images.map(image => () => waitForTrendAsset(image, ['load', 'error'], 12000)),
    ...videos.map(video => () => waitForTrendAsset(video, ['loadedmetadata', 'error'], 12000))
  ];
  let done = 0;
  setTrendingAssetProgress(source, period, done, assets.length);
  await Promise.all(assets.map(async wait => {
    await wait();
    done += 1;
    setTrendingAssetProgress(source, period, done, assets.length);
  }));
}
function isPlaceholderCover(url) {
  return /assets\/images\/placeholder(?:-[a-z]+)?\.jpg/i.test(String(url || ''));
}
function trendCover(item, local, code) {
  const covers = trendIsJable()
    ? [local && local.cover, item && item.cover]
    : [item && item.cover, local && local.cover];
  const usable = covers.find(cover => cover && !isPlaceholderCover(cover));
  return usable || (code ? `fourhoi.com/${code}/cover-t.jpg` : '');
}

function trendTitle(item, local) {
  const remoteTitle = String(item && item.title || '').trim();
  const localTitle = String(local && local.title || '').trim();
  const candidate = localTitle && (!remoteTitle || remoteTitle === '暂无中文简介')
    ? localTitle
    : (remoteTitle || localTitle);
  if (candidate && candidate !== '暂无中文简介') return candidate;
  return String(item && item.code || local && local.code || '').toUpperCase();
}

function trendMediaUrl(url) {
  const proxied = p(url);
  if (!proxied) return '';
  return `${proxied}${proxied.includes('?') ? '&' : '?'}cache=trend`;
}

function formatTrendTime(ms) {
  if (!ms) return '';
  try {
    return new Date(ms).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return '';
  }
}

function renderTrendingMeta(data) {
  const meta = $('trendingMeta');
  if (!meta) return;
  meta.className = 'trending-meta';
  if (isTrendingLoading(trendSource(), trendPeriod)) {
    meta.textContent = '正在抓取片源...';
    return;
  }
  if (!data) {
    meta.textContent = '点击 ↻ 刷新加载榜单';
    return;
  }
  const mode = data.sourceMode || (data.remote ? 'remote' : 'fallback');
  meta.classList.add(data.error ? 'error' : (data.cacheHit ? 'cache' : mode));
  const at = formatTrendTime(data.fetchedAt);
  const age = data.cacheHit && data.cacheAgeSeconds ? ` · 上次抓取${Math.max(1, Math.round(data.cacheAgeSeconds / 60))}分钟前` : '';
  if (data.error) {
    meta.textContent = `片源失败${at ? ' · ' + at : ''}${age}`;
  } else if (mode === 'stale_remote') {
    const staleAt = formatTrendTime(data.staleFetchedAt);
    meta.textContent = `最近同步榜单${staleAt ? ' · ' + staleAt : ''}${age}`;
  } else if (mode === 'fallback') {
    meta.textContent = `本地热度榜单${at ? ' · ' + at : ''}${age}`;
  } else if (mode === 'manual') {
    meta.textContent = `浏览器导入榜单${at ? ' · ' + at : ''}`;
  } else {
    const label = mode === 'homepage' ? '片源首页' : '片源榜单';
    meta.textContent = `${label}${at ? ' · ' + at : ''}${age}`;
  }
  if (data.importMessage) meta.textContent += ` · ${data.importMessage}`;
  if (data.sourceUrl) meta.title = data.sourceUrl;
  else meta.removeAttribute('title');
}

function _trendingSkeleton(n) {
  let html = '';
  for (let i = 0; i < n; i++) {
    html += '<div class="trend-skel"><div class="img-skel"></div>'
      + '<div class="info-skel">'
      + '<div class="line-skel l1"></div>'
      + '<div class="line-skel l2"></div>'
      + '<div class="line-skel l3"></div>'
      + '</div></div>';
  }
  return html;
}

function renderTrending() {
  const src = trendSource();
  const data = trendCache[src] && trendCache[src][trendPeriod];
  const grid = $('trendingGrid');
  const importButton = $('jableTrendImport');
  if (importButton) importButton.hidden = false;
  renderTrendingLibraryStatus(src, trendPeriod);
  $('trendingSource').textContent = trendLabel();
  $('trendingEmoji').textContent = trendIsJable() ? '🪐' : '🔥';
  $('trendingHeading').textContent = (trendPeriod === 'daily' ? '今日热门' : '本周热门');
  renderTrendingMeta(data);
  if (!data) {
    grid.innerHTML = '<div class="trending-empty">榜单未加载<br><span style="opacity:.7">点击 ↻ 刷新后获取最新热门</span></div>';
    return;
  }
  if (!data.items || data.items.length === 0) {
    const err = data.error ? `（${data.error}）` : '';
    grid.innerHTML = `<div class="trending-empty">暂时拉不到 ${escHtml(trendLabel())} 热门 ${escHtml(err)}<br><span style="opacity:.7">先看下方筛选区，或稍后点 ↻ 刷新</span></div>`;
    return;
  }
  const localMap = new Map();
  if (DATA && Array.isArray(DATA.videos)) {
    DATA.videos.forEach(v => {
      if (v && v.code) localMap.set((v.code || '').toLowerCase(), v);
    });
  }
  const visibleItems = data.items.map(it => {
    const code = (it.code || '').toLowerCase();
    const local = localMap.get(code);
    if (isVideoRemoved(code, trendSource())) return null;
    const actresses = Array.isArray(it.actresses) && it.actresses.length
      ? it.actresses
      : (Array.isArray(local && local.actresses) ? local.actresses : []);
    return Object.assign({}, local || {}, it, {
      title: trendTitle(it, local),
      cover: trendCover(it, local, code),
      url: it.url || (local && local.url) || '',
      actresses,
      local: !!local
    });
  }).filter(Boolean).slice(0, 20);
  if (visibleItems.length === 0) {
    grid.innerHTML = '<div class="trending-empty">当前热门都已被移除，稍后点 ↻ 刷新</div>';
    return;
  }
  grid.innerHTML = visibleItems.map((it, i) => {
    const code = (it.code || '').toLowerCase();
    const isJ = trendIsJable();
    const cover = isPlaceholderCover(it.cover) ? (code ? `fourhoi.com/${code}/cover-t.jpg` : '') : it.cover;
    const preview = code ? `/trend_preview/${isJ ? 'jable' : 'missav'}/${code}.mp4` : '';
    const dataKind = code ? 'mp4' : '';
    const safeTitle = escHtml(it.title || it.code || '');
    const safeUrl = it.url || (isJ ? `https://jable.tv/videos/${code}/` : `https://missav.ws/cn/${code}`);
    const actressText = Array.isArray(it.actresses) && it.actresses.length
      ? it.actresses.slice(0, 2).join('、')
      : '女优待补全';
    return `
       <div class="trend-card ${isJ ? 'is-jable' : ''}" data-card-action="trending" data-code="${escHtml(code)}" data-url="${escHtml(safeUrl)}" data-title="${safeTitle}" data-original-title="${escHtml(it.original_title || '')}" data-actresses="${escHtml(JSON.stringify(it.actresses || []))}" data-tags="${escHtml(JSON.stringify(it.tags || []))}" data-cover="${escHtml(cover)}" role="button" tabindex="0" title="${safeTitle}">
         <div class="cover">
            <span class="rank">${i + 1}</span>
            <img src="${escHtml(trendMediaUrl(cover))}" data-fallback-cover="${escHtml(trendMediaUrl('fourhoi.com/' + code + '/cover-t.jpg'))}" onload="handleCoverLoad(this)" alt="${escHtml(it.code || '')}" loading="lazy" referrerpolicy="no-referrer"
                 onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(trendMediaUrl('fourhoi.com/' + code + '/cover-t.jpg'))}';}else{this.parentElement.innerHTML='<span class=rank>${i + 1}</span><div class=placeholder>🎞 ${escHtml(it.code || '')}</div>';}">
           <div class="preview">
               ${preview ? `<video data-hls-src="${escHtml(preview)}" data-kind="${escHtml(dataKind)}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none" poster="${escHtml(trendMediaUrl(cover))}" onloadeddata="this.parentElement.classList.add('is-ready')" onerror="this.parentElement.classList.remove('is-ready');this.removeAttribute('src');"></video>` : ''}
           </div>
         </div>
          <div class="info">
            <div class="code">${escHtml(it.code || '')}</div>
            <div class="title">${escHtml(it.title || '（无标题）')}</div>
            ${actressText ? `<div class="trend-actress">${escHtml(actressText)}</div>` : ''}
          </div>
       </div>`;
  }).join('');
  prewarmCoverBatch(visibleItems, 20);
}

function renderTrendingLibraryStatus(source, period) {
  const status = $('trendingLibraryStatus');
  if (!status) return;
  const libraryStatus = trendLibraryStatus[source];
  if (!libraryStatus) {
    status.hidden = true;
    status.textContent = '';
    status.className = 'trending-library-status';
    return;
  }
  status.hidden = false;
  status.className = `trending-library-status ${libraryStatus.type || ''}`;
  if (libraryStatus.html) status.innerHTML = libraryStatus.html;
  else status.textContent = libraryStatus.text;
}

function setTrendingLibraryStatus(source, period, type, text, duration = 0, html = '') {
  clearTimeout(trendLibraryStatusTimer[source]);
  trendLibraryStatus[source] = { period, type, text, html };
  renderTrendingLibraryStatus(source, period);
  if (!duration) return;
  trendLibraryStatusTimer[source] = setTimeout(() => {
    trendLibraryStatus[source] = null;
    if (source === trendSource()) renderTrendingLibraryStatus(source, trendPeriod);
  }, duration);
}

async function refreshCurrentLibraryData(source) {
  if (source !== trendSource()) return;
  const dataFile = source === 'jable' ? 'jable_data.json' : 'picker_data.json';
  const response = await fetch(`${dataFile}?_=${Date.now()}`);
  if (!response.ok) throw new Error('作品库刷新失败');
  DATA = await response.json();
  if (source === 'jable') {
    const actresses = {};
    DATA.videos.forEach(video => (video.actresses || []).forEach(actress => { actresses[actress] = true; }));
    DATA.actresses = Object.keys(actresses);
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${DATA.actresses.length} 位女优 · Jable.TV`;
  } else {
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${(DATA.actresses || []).length} 位女优 · 按空格快速抽`;
  }
  renderTagChips();
  renderActressGrid();
  updateCount();
}

function trendingLibraryStatusHtml(source, result) {
  const added = Number(result.added) || 0;
  const total = Number(result.total) || 0;
  const beforeCount = Math.max(0, total - added);
  const libraryName = source === 'jable' ? 'Jable.TV' : 'MissAV';
  return `<span class="trending-library-label">${libraryName} 作品库</span><span class="trending-library-before">${beforeCount} 部</span><span class="trending-library-delta">＋${added} 部</span><span class="trending-library-total">现有 ${total} 部</span>`;
}

async function addTrendingVideosToLibrary(source, period, videos, workingText) {
  const validVideos = Array.isArray(videos) ? videos.filter(video => video && video.code) : [];
  if (!validVideos.length) throw new Error('没有可加入作品库的热门作品');
  setTrendingLibraryStatus(source, period, 'working', workingText, 0);
  const response = await fetch('/add_trending_videos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, videos: validVideos })
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || '作品库入库失败');
  await refreshCurrentLibraryData(source);
  setTrendingLibraryStatus(
    source,
    period,
    Number(result.added) ? 'success' : 'unchanged',
    '',
    0,
    trendingLibraryStatusHtml(source, result)
  );
  return result;
}

function collectRefreshedTrendingVideos(source) {
  const seenCodes = new Set();
  return ['daily', 'weekly'].flatMap(period => {
    const data = trendCache[source] && trendCache[source][period];
    return data && !data.error && Array.isArray(data.items) ? data.items : [];
  }).filter(video => {
    const code = String(video && video.code || '').trim().toUpperCase();
    if (!code || seenCodes.has(code)) return false;
    seenCodes.add(code);
    return true;
  });
}

function openTrendingCard(card, e) {
  if (!card) return;
  if (e && e.target && e.target.closest && e.target.closest('.card-collapse')) return;
  const code = (card.dataset.code || '').toLowerCase();
  if (!code) return;
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const isJableTrend = card.classList.contains('is-jable');
  const readCardList = name => {
    try {
      const values = JSON.parse(card.dataset[name] || '[]');
      return Array.isArray(values) ? values : [];
    } catch (e) {
      return [];
    }
  };
  const finish = (v) => {
    const cardVideo = {
      code: code.toUpperCase(),
      title: card.dataset.title || code.toUpperCase(),
      cover: card.dataset.cover || '',
      preview: isJableTrend ? `https://fourhoi.com/${code}/preview.mp4` : `/trend_preview/missav/${code}.mp4`,
      url: card.dataset.url || (isJableTrend ? `https://jable.tv/videos/${code}/` : `https://missav.ws/cn/${code}`),
      source: isJableTrend ? 'jable' : 'missav',
      is_multi: false,
      original_title: card.dataset.originalTitle || '',
      actresses: readCardList('actresses'),
      tags: readCardList('tags')
    };
    if (!v) {
      v = cardVideo;
    } else if (isJableTrend) {
      v = Object.assign({}, v, {
        title: v.title || cardVideo.title,
        cover: cardVideo.cover || v.cover || '',
        preview: v.preview || cardVideo.preview,
        url: v.url || cardVideo.url,
        source: 'jable',
        original_title: v.original_title || cardVideo.original_title,
        actresses: Array.isArray(v.actresses) ? v.actresses : [],
        tags: Array.isArray(v.tags) ? v.tags : []
      });
    } else {
      v = Object.assign({}, v, {
        title: v.title || cardVideo.title,
        cover: v.cover || cardVideo.cover || '',
        preview: v.preview || cardVideo.preview,
        url: v.url || cardVideo.url,
        source: 'missav',
        actresses: Array.isArray(v.actresses) ? v.actresses : [],
        tags: Array.isArray(v.tags) ? v.tags : []
      });
    }
    state.source = isJableTrend ? 'jable' : 'missav';
    state.current = v;
    state.history = [v, ...state.history.filter(h => (h.code || '').toLowerCase() !== code)];
    saveHistory();
    renderResult();
    renderHistory();
    scheduleSyncSave();
    focusResultArea();
  };
  if (isJableTrend && (!DATA || DATA.source !== 'jable')) {
    fetch('jable_data.json?_=' + Date.now()).then(r => r.json()).then(d => {
      DATA = d;
      var uniq = {};
      DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
      DATA.actresses = Object.keys(uniq);
      finish(DATA.videos.find(x => (x.code || '').toLowerCase() === code));
    }).catch(() => finish(null));
    return;
  }
  const local = DATA && DATA.videos ? DATA.videos.find(x => (x.code || '').toLowerCase() === code) : null;
  finish(local);
}

async function loadTrending(force, sourceOverride, periodOverride) {
  const src = sourceOverride || trendSource();
  const period = periodOverride || trendPeriod;
  if (isTrendingLoading(src, period)) return;
  const cacheVersion = trendCacheVersion[src][period];
  trendLoading[src][period] = true;
  renderTrending();
  startTrendingProgressPolling(src, period);
  const url = `/trending?source=${encodeURIComponent(src)}&period=${encodeURIComponent(period)}${force ? '&_=' + Date.now() : ''}`;
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (trendCacheVersion[src][period] !== cacheVersion) return;
    trendCache[src] = trendCache[src] || { daily: null, weekly: null };
    trendCache[src][period] = data;
    saveTrendSnapshots();
    if (typeof scheduleSyncSave === 'function') scheduleSyncSave();
    stopTrendingProgressPolling(src, period, true);
    renderTrending();
  } catch (e) {
    trendCache[src] = trendCache[src] || { daily: null, weekly: null };
    trendCache[src][period] = { source: src, period, items: [], error: '网络错误' };
  } finally {
    trendLoading[src][period] = false;
    stopTrendingProgressPolling(src, period);
    if (trendRefreshBatch && trendRefreshBatch.source === src) {
      trendRefreshBatch.completed.add(period);
      renderTrendRefreshBatchProgress();
    }
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
  });
});
document.getElementById('trendingRefresh').addEventListener('click', async () => {
  const source = trendSource();
  const period = trendPeriod;
  const button = document.getElementById('trendingRefresh');
  button.disabled = true;
  button.textContent = '↻ 刷新中';
  startTrendRefreshBatch(source);
  try {
    await Promise.all(['daily', 'weekly'].map(period => loadTrending(true, source, period)));
    await addTrendingVideosToLibrary(
      source,
      period,
      collectRefreshedTrendingVideos(source),
      '正在同步作品库...'
    );
    scheduleSyncSave();
  } catch (error) {
    setTrendingLibraryStatus(source, period, 'error', error.message || '作品库同步失败');
  } finally {
    finishTrendRefreshBatch(source);
    button.disabled = false;
    button.textContent = '↻ 刷新';
    renderTrending();
  }
});

function openTrendImport() {
  const source = trendSource();
  const dialog = $('jableTrendImportDialog');
  const title = $('jableTrendImportTitle');
  const description = $('jableTrendImportDescription');
  const periodLabel = $('jableTrendImportPeriod');
  const text = $('jableTrendImportText');
  const submit = $('jableTrendImportSubmit');
  if (!dialog || !title || !description || !periodLabel || !text || !submit) return;
  title.firstChild.textContent = `导入 ${trendLabel()} `;
  periodLabel.textContent = trendPeriod === 'daily' ? '今日热门' : '本周热门';
  description.textContent = `在已通过验证的 ${trendLabel()} 榜单页复制作品链接或番号后粘贴。导入内容仅保存为当前周期的本地榜单，不会绕过网站验证。`;
  submit.textContent = '保存当前榜单';
  text.value = '';
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
  text.focus();
}

const jableTrendImportButton = $('jableTrendImport');
if (jableTrendImportButton) jableTrendImportButton.addEventListener('click', openTrendImport);

const jableTrendImportForm = $('jableTrendImportForm');
if (jableTrendImportForm) jableTrendImportForm.addEventListener('submit', async event => {
  event.preventDefault();
  const submit = $('jableTrendImportSubmit');
  const text = $('jableTrendImportText');
  const status = $('jableTrendImportStatus');
  if (!text || !submit || !status) return;
  submit.disabled = true;
  status.textContent = '正在保存榜单...';
  try {
    const source = trendSource();
    const response = await fetch('/import_trending_videos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, period: trendPeriod, text: text.value })
    });
    const result = await response.json();
    if (!response.ok || !result.ok || !result.data) throw new Error(result.error || '导入失败');
    trendCache[source][trendPeriod] = result.data;
    trendCacheVersion[source][trendPeriod] += 1;
    saveTrendSnapshots();
    scheduleSyncSave();
    renderTrending();
    status.textContent = `已保存 ${result.data.items.length} 部作品`;
    setTimeout(() => $('jableTrendImportDialog').close(), 500);
  } catch (error) {
    status.textContent = error.message || `导入失败，请粘贴 ${trendLabel()} 作品链接或番号`;
  } finally {
    submit.disabled = false;
  }
});

window.addEventListener('load', () => {
  renderTrending();
});

// 收起 / 展开
(function() {
  var section = document.getElementById('trending');
  var btn = document.getElementById('trendingToggle');
  function apply(collapsed) {
    section.classList.toggle('collapsed', collapsed);
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.title = collapsed ? '展开' : '收起';
    btn.querySelector('.lbl').textContent = collapsed ? '展开' : '收起';
  }
  // 热门区默认始终展开,避免用户误以为“没加载出来”
  apply(false);
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
