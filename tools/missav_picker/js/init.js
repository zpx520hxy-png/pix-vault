// ---- 启动 ----
function init(stage) {
  if (stage === 'index') {
    // 索引已加载(actresses/groups/avatars/display/tags),立即渲染 UI
    const videoCount = IDX.total_videos ?? IDX.video_count ?? 0;
    $('stats').textContent = `📊 ${videoCount} 部作品 · ${IDX.actresses.length} 位女优 · ${IDX.tags.length} 个标签 · 按空格快速抽`;
    loadFavoriteActresses();
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    loadRemovedVideos();
    // 热门榜单仅由用户点击刷新加载，避免每次打开页面都请求上游片源。
    renderTrending();
    // 异步加载完整数据
    $('rollBtn').disabled = true;
    $('rollBtn').textContent = '⏳ 加载作品数据...';
    fetch(location.pathname.replace(/[^/]*$/, '') + 'picker_data.json?_=' + Date.now())
      .then(r => r.json())
      .then(d => {
        DATA = d;
        $('rollBtn').disabled = false;
        $('rollBtn').textContent = '🎲 随机抽一部';
        renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
        updateCount();
      })
      .catch(e => { $('stats').textContent = '加载失败,请刷新'; });
  } else {
    // file:// 一次性内嵌
    $('stats').textContent = `📊 ${DATA.videos.length} 部作品 · ${DATA.actresses.length} 位女优 · ${DATA.tags.length} 个标签 · 按空格快速抽`;
    loadFavoriteActresses();
    renderTagChips();
    renderActressGrid();
    loadFavorites();
    loadHistory();
    loadRemovedVideos();
    updateCount();
  }
}

// 让 getCandidates 能同时工作于 DATA 未加载时(返回空)
const origGetCandidates = getCandidates;
getCandidates = function() {
if (!DATA) return [];
  return origGetCandidates();
};
