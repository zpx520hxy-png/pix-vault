// v2 体验默认: 启动时固定 MissAV 首页,不让共享状态覆盖当前片源/当前结果
window._SOURCE_SYNC_DISABLED = true;

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
    if (!d.ok || !d.plan) { el.textContent = '缓存预热: 初始化中...'; return; }
    const p = d.plan;
    const cc = p.current_cache || {};
    const ready = (p.status || {}).ready || 0;
    const pending = (p.status || {}).pending || 0;
    const failed = (p.status || {}).failed || 0;
    const notFound = (p.status || {}).not_found || 0;
    const total = (p.targets || []).length;
    el.innerHTML =
      '<b>缓存预热</b> ' + ready + '/' + total + ' 已就绪 · ' +
      pending + ' 解析中 · ' + failed + ' 失败 · ' + notFound + ' 不支持 · ' +
      cc.play_mb + 'MB 播放 · ' + cc.image_mb + 'MB 图片';
  } catch (e) {
    el.textContent = '缓存预热: 获取失败';
  }
}
