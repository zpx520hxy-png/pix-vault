// 局域网多端同步: 手机/电脑共享当前片源、当前结果和抽过记录
window._SOURCE_SYNC_DISABLED = false;

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
      setInterval(pullSyncState, 1000);
      // 启动后异步拉一次缓存计划
      refreshCacheStatus();
      setInterval(refreshCacheStatus, 30000);
    })
    .catch(e => $('stats').textContent = '加载失败,请刷新');
}

async function refreshCacheStatus() {
  const el = $('cacheStatus');
  if (!el) return;
  try {
    const r = await fetch('cache_plan?_=' + Date.now());
    if (!r.ok) return;
    const d = await r.json();
      if (!d.ok || !d.plan) { el.textContent = '播放缓存: 暂无'; return; }
      const cc = d.plan.current_cache || {};
      el.innerHTML =
        '<b>播放缓存</b> ' + (cc.play_mb || 0) + 'MB · 图片缓存 ' + (cc.image_mb || 0) + 'MB';
  } catch (e) {
    el.textContent = '缓存预热: 获取失败';
  }
}

// ---- 回到顶部按钮 ----
(function() {
  const btn = document.getElementById('backToTop');
  if (!btn) return;
  const THRESHOLD = 400; // 滚动 > 400px 才显示
  let ticking = false;
  function update() {
    // 兼容: 页面可能用 documentElement / body 滚动而非 window
    const y = window.scrollY || window.pageYOffset
      || document.documentElement.scrollTop || document.body.scrollTop;
    if (y > THRESHOLD) btn.classList.add('visible');
    else btn.classList.remove('visible');
    ticking = false;
  }
  function onScroll() {
    if (!ticking) { requestAnimationFrame(update); ticking = true; }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  document.addEventListener('scroll', onScroll, { passive: true });
  // 初次检查 (用户可能刷新页面时已滚到中段)
  update();
  btn.addEventListener('click', function() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  });
})();
