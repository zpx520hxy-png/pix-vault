// ---- 启动 ----
function init(stage) {
  if (stage === 'index') {
    // 索引已加载(actresses/groups/avatars/display/tags),立即渲染 UI
    $('stats').textContent = `📊 ${IDX.video_count} 部作品 · ${IDX.actresses.length} 位女优 · ${IDX.tags.length} 个标签 · 按空格快速抽`;
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    // 热门板块(随当前片源)
    loadTrending();
    // 异步加载完整数据
    $('rollBtn').disabled = true;
    $('rollBtn').textContent = '⏳ 加载作品数据...';
    fetch(location.pathname.replace(/[^/]*$/, '') + 'picker_data.json?_=' + Date.now())
      .then(r => r.json())
      .then(d => {
        DATA = d;
        $('rollBtn').disabled = false;
        $('rollBtn').textContent = '🎲 随机抽一部';
        updateCount();
      })
      .catch(e => { $('stats').textContent = '加载失败,请刷新'; });
  } else {
    // file:// 一次性内嵌
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${DATA.actresses.length} 位女优 · ${DATA.tags.length} 个标签 · 按空格快速抽`;
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    updateCount();
  }
}

// 让 getCandidates 能同时工作于 DATA 未加载时(返回空)
const origGetCandidates = getCandidates;
getCandidates = function() {
if (!DATA) return [];
  return origGetCandidates();
};
