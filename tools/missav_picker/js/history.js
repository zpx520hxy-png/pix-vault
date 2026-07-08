function renderHistory() {
  if (state.history.length === 0) { $('historyArea').style.display = 'none'; return; }
  $('historyArea').style.display = 'block';
  $('historyGrid').innerHTML = state.history.map(v => `
    <div class="hist-card" onclick="showFromHistory(${jsArg(v.code)})">
      <div class="img-wrap">
        <img src="${escHtml(coverUrl(v))}" data-fallback-cover="${escHtml(fallbackCoverUrl(v))}" onload="handleCoverLoad(this)" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
          onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else if(!this.dataset.fallback2){this.dataset.fallback2='1';this.src='${escHtml(p(v.cover || ""))}';}else{this.parentElement.style.background='var(--border)';this.style.display='none';}">
      </div>
      <div class="hist-code">${escHtml(v.code)}</div>
      <div class="hist-title">${escHtml(v.title || '—')}</div>
    </div>
  `).join('');
}

// hover 触发后挂载 hls.js(避免一次挂 218 个实例)
function mountHls(video, src) {
  if (!src || !video) return;
  if (video.src && !video.src.startsWith('blob:')) {
    video.play().catch(() => {});
    return;
  }
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
    const box = card.querySelector('.bc-preview[data-preview-src]');
    if (box && !box.querySelector('video') && box.dataset.previewSrc) {
      const video = document.createElement('video');
      video.dataset.hlsSrc = box.dataset.previewSrc;
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = 'none';
      video.disableRemotePlayback = true;
      if (box.dataset.poster) video.poster = box.dataset.poster;
      box.appendChild(video);
      mountHls(video, video.dataset.hlsSrc);
      return;
    }
    const v = card.querySelector('video[data-hls-src]');
    if (v) { mountHls(v, v.dataset.hlsSrc); return; }
  }
  const v = e.target.closest('video[data-hls-src]');
  if (v) mountHls(v, v.dataset.hlsSrc);
});
document.addEventListener('mouseenter', function(e) {
  const card = e.target.closest && e.target.closest('.browse-card,.hist-card,.trend-card');
  if (card) {
    const box = card.querySelector('.bc-preview[data-preview-src]');
    if (box && !box.querySelector('video') && box.dataset.previewSrc) {
      const video = document.createElement('video');
      video.dataset.hlsSrc = box.dataset.previewSrc;
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = 'none';
      video.disableRemotePlayback = true;
      if (box.dataset.poster) video.poster = box.dataset.poster;
      box.appendChild(video);
      mountHls(video, video.dataset.hlsSrc);
      return;
    }
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

function showFromHistory(code) {
  const v = state.history.find(h => h.code === code) || (DATA && DATA.videos ? DATA.videos.find(x => x.code === code) : null);
  if (v) { state.current = v; renderResult(); }
}

function copyCode(code, btn) {
  navigator.clipboard.writeText(code).then(() => {
    if (!btn) return;
    const old = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = old, 1000);
  });
}
