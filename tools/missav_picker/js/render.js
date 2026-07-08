// ---- 渲染结果 ----
function renderResult() {
  const v = state.current;
  if (!v) return;
  v.tags = Array.isArray(v.tags) ? v.tags : [];
  v.actresses = Array.isArray(v.actresses) ? v.actresses : [];
  const badges = [];
  badges.push(v.is_multi
    ? `<span class="badge multi">👥 多人 · ${v.actresses.length} 位</span>`
    : `<span class="badge solo">👤 单人</span>`);
  if (isManualFavorite(v)) badges.push('<span class="badge saved manual-fav">⭐ 手动收藏</span>');
  if (isScrapedFavorite(v)) badges.push('<span class="badge saved scraped-fav">✅ 站内收藏</span>');
  if (v.date) badges.push(`<span class="badge">📅 ${escHtml(v.date)}</span>`);
  v.tags.forEach(t => badges.push(`<span class="badge tag">${escHtml(t)}</span>`));

  const actressText = v.actresses.length > 0
    ? v.actresses.map(a => `<strong>${escHtml(a)}</strong>`).join('、')
    : '<span style="color:var(--text-mute)">未知</span>';
  const leadActress = primaryActress(v);

  const isJable = currentSourceOf(v) === 'jable';
  const coverBlock = isJable
    ? `<div class="media-col">
          <div class="jplayer" id="jp" data-state="cover">
          <div class="jp-cover" id="jpCover">
             <video class="jp-preview" id="jpPreview" muted loop playsinline disableRemotePlayback preload="none" poster="${escHtml(p(v.cover))}"></video>
             <img src="${escHtml(coverUrl(v))}" data-fallback-cover="${escHtml(fallbackCoverUrl(v))}" onload="handleCoverLoad(this)" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
               onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else if(!this.dataset.fallback2){this.dataset.fallback2='1';this.src='${escHtml(p(v.cover || ""))}';}else{this.parentElement.innerHTML='<div class=placeholder>🎞 ${escHtml(v.code)}</div>';}">
          </div>
          <video id="jpVideo" playsinline preload="auto" poster="${escHtml(p(v.cover))}"></video>
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
         <video src="${escHtml(v.preview || '')}" muted loop playsinline disableRemotePlayback preload="auto"
            poster="${escHtml(p(v.cover))}"
            onerror="this.style.display='none'"></video>
          <div class="cover">
              <img src="${escHtml(coverUrl(v))}" data-fallback-cover="${escHtml(fallbackCoverUrl(v))}" onload="handleCoverLoad(this)" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
                  onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else if(!this.dataset.fallback2){this.dataset.fallback2='1';this.src='${escHtml(p(v.cover || ""))}';}else{this.parentElement.innerHTML='<div class=placeholder>🎞 ${escHtml(v.code)}</div>';}">
          </div>
         </div></div>`;

  $('resultArea').innerHTML = `
    <div class="result-card">
      ${coverBlock}
      <div class="info">
        <div class="info-head">
          <div class="code">${escHtml(v.code)}</div>
          <button class="card-collapse" type="button" data-collapse="card">
            <span class="x">×</span><span class="lbl">收起</span><span class="arr">▾</span>
          </button>
        </div>
        <div class="badges">${badges.join('')}</div>
        <div class="title">${escHtml(v.title || '（无标题）')}</div>
        <div class="meta">
          <strong>女优</strong>：${actressText}<br>
          <strong>发布日期</strong>：${escHtml(v.date || '—')}
        </div>
        <div class="actions">
          <a class="btn btn-primary" href="${escHtml(v.url || '')}" target="_blank" rel="noopener">▶️ 去 ${isJable?'Jable':'MissAV'} 观看</a>
          <button class="btn btn-ghost" onclick="rollOne()">🎲 再抽一部</button>
          <button class="btn btn-ghost" onclick="copyCode(${jsArg(v.code)}, this)">📋 复制番号</button>
          <button class="btn btn-ghost fav-toggle" onclick="toggleFavorite()">${isManualFavorite(v) ? '⭐ 取消手动收藏' : '☆ 手动收藏'}</button>
          <button class="btn btn-ghost" onclick="toggleFavoriteActress(${jsArg(leadActress)})" ${leadActress ? '' : 'disabled'}>${leadActress && isFavoriteActress(leadActress) ? '💖 已收藏女优' : '🤍 收藏女优'}</button>
          <button class="btn btn-ghost" onclick="removeCurrentVideo()" style="color:var(--err)">🗑 移除作品</button>
        </div>
      </div>
    </div>`;
  if (isJable) {
    const cover = $('jpCover');
    if (cover) cover.onclick = () => {
      const preview = $('jpPreview');
      if (!preview) return;
      if (preview.dataset.previewMounted !== '1') {
        preview.dataset.previewMounted = '1';
        mountHls(preview, previewUrl(v));
        cover.classList.add('preview-on');
        return;
      }
      if (preview.paused) {
        preview.play().catch(function(){});
        cover.classList.add('preview-on');
      } else {
        preview.pause();
        cover.classList.remove('preview-on');
      }
    };
  }
}

// ── jable 播放器 ──
let _jpHls = null, _jpVideo = null;

async function ensurePlayReady(code, timeoutMs = 30000) {
  try {
    await fetch(`/play/${code}/request`, { cache: 'no-store' });
  } catch (e) {}
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(`/play/${code}/status?_=${Date.now()}`, { cache: 'no-store' });
      const d = await r.json();
      if (d.status === 'ready') return { ok: true, status: d.status };
      if (d.status === 'failed' || d.status === 'not_found') return { ok: false, status: d.status, error: d.error || '' };
    } catch (e) {}
    await new Promise(r => setTimeout(r, 1200));
  }
  return { ok: false, status: 'timeout', error: 'timeout' };
}

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
