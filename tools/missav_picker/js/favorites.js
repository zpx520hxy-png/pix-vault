function renderFavorites() {
  const pairs = [
    ['missav', $('missavFavArea'), $('missavFavGrid'), state.favoritesMissav],
    ['jable', $('jableFavArea'), $('jableFavGrid'), state.favoritesJable],
  ];
  pairs.forEach(([src, area, grid, list]) => {
    if (!list.length) { area.style.display = 'none'; grid.innerHTML = ''; return; }
    area.style.display = 'block';
    const isJableFav = (src === 'jable');
    grid.innerHTML = list.map(v => {
      const externalUrl = v.url || '';
      const extBtn = externalUrl
        ? `<a class="ext-link" href="${externalUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗 打开 ${isJableFav ? 'Jable' : 'MissAV'}</a>`
        : '';
      return `
      <div class="fav-card" onclick="openFavorite('${src}','${v.code}')">
        <div class="img-wrap">
          <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
               onerror="if(this.dataset.fallback){this.style.display='none';}else{this.dataset.fallback='1';this.src='${p(v.cover || "")}';}">
        </div>
        <div class="info">
          <div class="code">${v.code}</div>
          <div class="title">${v.title || '（无标题）'}</div>
          <div class="meta">
            ${extBtn}
            <button class="remove" onclick="event.stopPropagation(); removeFavorite('${src}','${v.code}')">移除</button>
          </div>
        </div>
      </div>`;
    }).join('');
  });
}

function saveFavorites(src) {
  try { localStorage.setItem(favStorageKey(src), JSON.stringify(favListForSource(src))); } catch(e) {}
}
function loadFavorites() {
  try {
    const a = JSON.parse(localStorage.getItem(favStorageKey('missav')) || '[]');
    const b = JSON.parse(localStorage.getItem(favStorageKey('jable')) || '[]');
    state.favoritesMissav = Array.isArray(a) ? a : [];
    state.favoritesJable = Array.isArray(b) ? b : [];
  } catch(e) {
    state.favoritesMissav = []; state.favoritesJable = [];
  }
  renderFavorites();
}
function toggleFavorite() {
  if (!state.current) return;
  const src = currentSourceOf(state.current);
  const list = favListForSource(src);
  const idx = list.findIndex(v => v.code === state.current.code);
  if (idx >= 0) list.splice(idx, 1);
  else list.unshift(normFavorite(state.current, src));
  if (src === 'jable') state.favoritesJable = list.filter((v,i,a) => a.findIndex(x => x.code === v.code) === i);
  else state.favoritesMissav = list.filter((v,i,a) => a.findIndex(x => x.code === v.code) === i);
  saveFavorites(src);
  renderFavorites();
  // 只更新收藏按钮和徽章,不重建结果卡(避免 Jable 播放器被销毁)
  const favBtn = document.querySelector('.result-card .actions .btn:last-child');
  if (favBtn) favBtn.textContent = isFavorite(state.current) ? '⭐ 取消收藏' : '☆ 收藏';
  const badge = document.querySelector('.result-card .badge.saved');
  if (isFavorite(state.current) && !badge) {
    const badgesEl = document.querySelector('.result-card .badges');
    if (badgesEl) badgesEl.insertAdjacentHTML('beforeend', '<span class="badge saved">⭐ 已收藏</span>');
  } else if (!isFavorite(state.current) && badge) {
    badge.remove();
  }
  updateCount();
  scheduleSyncSave();
}
function removeFavorite(src, code) {
  if (src === 'jable') state.favoritesJable = state.favoritesJable.filter(v => v.code !== code);
  else state.favoritesMissav = state.favoritesMissav.filter(v => v.code !== code);
  saveFavorites(src);
  renderFavorites();
  updateCount();
  if (state.current && currentSourceOf(state.current) === src && state.current.code === code) renderResult();
  scheduleSyncSave();
}
function clearFavorites(src) {
  if (src === 'jable') state.favoritesJable = [];
  else state.favoritesMissav = [];
  localStorage.removeItem(favStorageKey(src));
  renderFavorites();
  updateCount();
  renderResult();
  scheduleSyncSave();
}
function openFavorite(src, code) {
  const list = src === 'jable' ? state.favoritesJable : state.favoritesMissav;
  const fav = list.find(v => v.code === code);
  if (!fav) return;
  function applyFavorite() {
    document.querySelectorAll('#sourceChips .chip').forEach(c => c.classList.remove('active'));
    const chip = document.querySelector(`#sourceChips .chip[data-source="${src}"]`);
    if (chip) chip.classList.add('active');
    state.source = src;
    state.current = fav;
    if ((fav.source || src) !== src) { console.warn('openFavorite: source mismatch', fav, src); return; }
    renderResult();
    scheduleSyncSave();
    // 滚到结果区 (跟 trend-card 点击一致)
    $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  if (src === 'jable') {
    if (DATA && DATA.source === 'jable') { applyFavorite(); return; }
    fetch('jable_data.json?_=' + Date.now()).then(r => r.json()).then(d => {
      DATA = d;
      var uniq = {};
      DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
      DATA.actresses = Object.keys(uniq);
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      applyFavorite();
    });
  } else {
    if (DATA && (!DATA.source || DATA.source === 'missav')) { applyFavorite(); return; }
    fetch('picker_data.json?_=' + Date.now()).then(r => r.json()).then(d => {
      DATA = d;
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + (DATA.actresses||[]).length + ' 位女优 · 按空格快速抽';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      applyFavorite();
    });
  }
}
