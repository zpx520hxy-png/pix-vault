// ---- 每日 / 每周热门 ----
let trendPeriod = 'daily';
let trendCache = { missav: { daily: null, weekly: null }, jable: { daily: null, weekly: null } };
let trendLoading = false;
let playableJableCache = null;

function trendSource() {
  // 跟随当前片源;选 missav/jable 与 state.source 一致
  return state && state.source === 'jable' ? 'jable' : 'missav';
}
function trendLabel() { return trendSource() === 'jable' ? 'Jable.TV' : 'MissAV'; }
function trendIsJable() { return trendSource() === 'jable'; }

function renderPlayableJable() {
  const section = $('playableJable');
  const grid = $('playableJableGrid');
  if (!section || !grid) return;
  if (!trendIsJable()) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  if (!playableJableCache) {
    grid.innerHTML = _trendingSkeleton(3);
    return;
  }
  if (!playableJableCache.items || playableJableCache.items.length === 0) {
    grid.innerHTML = '<div class="trending-empty">当前没有可直接播放的 Jable 作品</div>';
    return;
  }
  grid.innerHTML = playableJableCache.items.slice(0, 30).map(v => `
    <div class="playable-card" onclick="showFromPlayableJable(${jsArg(v.code)})">
      <div class="cover">
        <img src="${escHtml(p('fourhoi.com/' + (v.code || '').toLowerCase() + '-uncensored-leak/cover-t.jpg'))}" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
             onerror="if(this.dataset.fallback){this.parentElement.innerHTML='<div class=placeholder>🎞 ${escHtml(v.code)}</div>';}else{this.dataset.fallback='1';this.src='${escHtml(p(v.cover || ''))}';}">
      </div>
      <div class="info">
        <div class="code">${escHtml(v.code)}</div>
        <div class="title">${escHtml((v.title || '（无标题）').slice(0, 60))}</div>
      </div>
    </div>`).join('');
}

async function loadPlayableJable(force) {
  if (!trendIsJable()) return;
  if (playableJableCache && !force) { renderPlayableJable(); return; }
  try {
    const r = await fetch(`/playable_jable${force ? '?_=' + Date.now() : ''}`);
    const d = await r.json();
    playableJableCache = d;
  } catch (e) {
    playableJableCache = { ok: false, items: [] };
  }
  renderPlayableJable();
}

function showFromPlayableJable(code) {
  const v = DATA && DATA.videos ? DATA.videos.find(x => (x.code || '').toLowerCase() === (code || '').toLowerCase()) : null;
  if (!v) return;
  state.current = v;
  renderResult();
  $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
  // 既然这里叫“可播放作品”,点卡片后直接自动起播
  setTimeout(async () => {
    const jp = $('jp');
    const loading = $('jpLoading');
    if (!jp || !loading) return;
    jp.setAttribute('data-state', 'play');
    loading.textContent = '⏳ 正在准备播放链路...';
    loading.classList.remove('hide');
    const result = await ensurePlayReady((v.code || '').toLowerCase());
    if (!result.ok) {
      loading.textContent = result.status === 'not_found' ? '⚠️ 当前未找到可播放链路' : '⚠️ 播放准备失败';
      return;
    }
    initJplayer(v);
  }, 80);
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
  $('trendingSource').textContent = trendLabel();
  $('trendingEmoji').textContent = trendIsJable() ? '🪐' : '🔥';
  $('trendingHeading').textContent = (trendPeriod === 'daily' ? '今日热门' : '本周热门');
  if (!data) {
    grid.innerHTML = _trendingSkeleton(6);
    renderPlayableJable();
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
    return Object.assign({}, local || {}, it, {
      title: it.title || (local && local.title) || '',
      cover: it.cover || (local && local.cover) || '',
      url: it.url || (local && local.url) || '',
      local: !!local
    });
  }).filter(Boolean).slice(0, 20);
  if (visibleItems.length === 0) {
    grid.innerHTML = '<div class="trending-empty">当前热门都已被移除，稍后点 ↻ 刷新</div>';
    renderPlayableJable();
    return;
  }
  grid.innerHTML = visibleItems.map((it, i) => {
    const code = (it.code || '').toLowerCase();
    const isJ = trendIsJable();
    const cover = isJ && code ? (it.cover || `fourhoi.com/${code}/cover-t.jpg`) : (it.cover || (code ? `fourhoi.com/${code}/cover-t.jpg` : ''));
    const preview = code ? (isJ ? `https://fourhoi.com/${code}/preview.mp4` : `/trend_preview/missav/${code}.mp4`) : '';
    const dataKind = code ? 'mp4' : '';
    const safeTitle = escHtml(it.title || it.code || '');
    const safeUrl = it.url || (isJ ? `https://jable.tv/videos/${code}/` : `https://missav.ws/cn/${code}`);
    return `
       <div class="trend-card ${isJ ? 'is-jable' : ''}" onclick="openTrendingCard(this, event)" data-code="${escHtml(code)}" data-url="${escHtml(safeUrl)}" data-title="${safeTitle}" data-cover="${escHtml(cover)}" title="${safeTitle}">
         <div class="cover">
            <span class="rank">${i + 1}</span>
            <img src="${escHtml(p(cover))}" data-fallback-cover="${escHtml(p('fourhoi.com/' + code + '/cover-t.jpg'))}" onload="handleCoverLoad(this)" alt="${escHtml(it.code || '')}" loading="lazy" referrerpolicy="no-referrer"
                 onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(p('fourhoi.com/' + code + '/cover-t.jpg'))}';}else{this.parentElement.innerHTML='<span class=rank>${i + 1}</span><div class=placeholder>🎞 ${escHtml(it.code || '')}</div>';}">
           <div class="preview">
             ${preview ? (isJ
               ? `<video src="${escHtml(preview)}" data-hls-src="${escHtml(preview)}" data-kind="${escHtml(dataKind)}" muted loop playsinline disableRemotePlayback crossorigin="anonymous" preload="metadata" poster="${escHtml(cover)}"></video>`
               : `<video data-hls-src="${escHtml(preview)}" data-kind="${escHtml(dataKind)}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none" poster="${escHtml(cover)}"></video>`
             ) : ''}
           </div>
         </div>
         <div class="info">
           <div class="code">${escHtml(it.code || '')}</div>
           <div class="title">${escHtml((it.title || '（无标题）').slice(0, 60))}</div>
         </div>
       </div>`;
  }).join('');
  prewarmCoverBatch(visibleItems, 20);
  renderPlayableJable();
}

function openTrendingCard(card, e) {
  if (!card) return;
  if (e && e.target && e.target.closest && e.target.closest('.card-collapse')) return;
  const code = (card.dataset.code || '').toLowerCase();
  if (!code) return;
  if (e) { e.preventDefault(); e.stopPropagation(); }
  const isJableTrend = card.classList.contains('is-jable');
  const finish = (v) => {
    const cardVideo = {
      code: code.toUpperCase(),
      title: card.dataset.title || code.toUpperCase(),
      cover: card.dataset.cover || '',
      url: card.dataset.url || (isJableTrend ? `https://jable.tv/videos/${code}/` : `https://missav.ws/cn/${code}`),
      source: isJableTrend ? 'jable' : 'missav',
      is_multi: false,
      actresses: [],
      tags: []
    };
    if (!v) {
      v = cardVideo;
    } else if (isJableTrend) {
      v = Object.assign({}, v, {
        title: v.title || cardVideo.title,
        cover: cardVideo.cover || v.cover || '',
        url: v.url || cardVideo.url,
        source: 'jable',
        actresses: Array.isArray(v.actresses) ? v.actresses : [],
        tags: Array.isArray(v.tags) ? v.tags : []
      });
    }
    state.source = isJableTrend ? 'jable' : 'missav';
    state.current = v;
    state.history = [v, ...state.history.filter(h => (h.code || '').toLowerCase() !== code)].slice(0, 12);
    saveHistory();
    renderResult();
    renderHistory();
    scheduleSyncSave();
    $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
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
  finish(DATA && DATA.videos ? DATA.videos.find(x => (x.code || '').toLowerCase() === code) : null);
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
    if (trendIsJable()) loadPlayableJable(force);
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
  const card = btn.closest('.result-card,.filters,.history,.playable-jable');
  if (!card) return;
  card.classList.toggle('is-collapsed');
  const collapsed = card.classList.contains('is-collapsed');
  const lbl = btn.querySelector('.lbl');
  if (lbl) lbl.textContent = collapsed ? '展开' : '收起';
}, true);
