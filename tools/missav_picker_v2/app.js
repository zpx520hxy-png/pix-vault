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
    })
    .catch(e => $('stats').textContent = '加载失败,请刷新');
}
