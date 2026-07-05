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
    // missav 预览走本地代理(免 fourhoi 403); jable 不再播放预览
    const preview = !isJ && code ? `/trend_preview/missav/${code}.mp4` : '';
    const dataKind = !isJ && code ? 'mp4' : '';
    const safeTitle = (it.title || it.code || '').replace(/"/g, '&quot;');
    const safeUrl = it.url || '';
    return `
       <div class="trend-card ${isJ ? 'is-jable' : ''}" data-code="${code}" data-url="${safeUrl.replace(/"/g, '&quot;')}" title="${safeTitle}">
         <div class="cover">
           <span class="rank">${i + 1}</span>
           <img src="${p(isJ ? 'fourhoi.com/' + code + '-uncensored-leak/cover-t.jpg' : cover)}" alt="${it.code || ''}" loading="lazy" referrerpolicy="no-referrer"
                onerror="if(this.dataset.fallback){this.parentElement.innerHTML='<span class=rank>${i + 1}</span><div class=placeholder>🎞 ${it.code || ''}</div>';}else{this.dataset.fallback='1';this.src='${p(cover)}';}">
          <div class="preview">
            ${!isJ ? `<video data-hls-src="${preview}" data-kind="${dataKind}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none" poster="${cover}"></video>` : ''}
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
