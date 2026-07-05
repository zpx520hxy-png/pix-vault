function renderHistory() {
  if (state.history.length === 0) { $('historyArea').style.display = 'none'; return; }
  $('historyArea').style.display = 'block';
  $('historyGrid').innerHTML = state.history.map(v => `
    <div class="hist-card" onclick="showFromHistory('${v.code}')">
      <div class="img-wrap">
        <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
          onerror="if(this.dataset.fallback){this.parentElement.style.background='var(--border)';this.style.display='none';}else{this.dataset.fallback='1';this.src='${p(v.cover || "")}';}">
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
