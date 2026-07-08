function renderFavorites() {
  const pairs = [
    ['missav', $('missavFavArea'), $('missavFavGrid'), state.favoritesMissav],
    ['jable', $('jableFavArea'), $('jableFavGrid'), state.favoritesJable],
  ];
  pairs.forEach(([src, area, grid, list]) => {
    if (!list.length) { area.style.display = 'none'; grid.innerHTML = ''; return; }
    area.style.display = 'block';
    const isJableFav = (src === 'jable');
    grid.innerHTML = list.map(raw => {
      const v = hydrateVideoRef(raw, src) || Object.assign({}, raw, { source: src });
      const externalUrl = v.url || '';
      const extBtn = externalUrl
        ? `<a class="ext-link" href="${escHtml(externalUrl)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗 打开 ${isJableFav ? 'Jable' : 'MissAV'}</a>`
        : '';
      return `
      <div class="fav-card" data-card-action="favorite" data-source="${escHtml(src)}" data-code="${escHtml(v.code)}" role="button" tabindex="0">
        <div class="img-wrap">
          <img src="${escHtml(coverUrl(v))}" data-fallback-cover="${escHtml(fallbackCoverUrl(v))}" onload="handleCoverLoad(this)" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
               onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else if(!this.dataset.fallback2){this.dataset.fallback2='1';this.src='${escHtml(p(v.cover || ""))}';}else{this.style.display='none';}">
        </div>
        <div class="info">
          <div class="code">${escHtml(v.code)}</div>
          <div class="title">${escHtml(v.title || '（无标题）')}</div>
          <div class="meta">
            ${extBtn}
            <button class="remove" onclick="event.stopPropagation(); removeFavorite(${jsArg(src)},${jsArg(v.code)})">移除</button>
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
    state.removedFavorites = readRemovedFavorites();
  } catch(e) {
    state.favoritesMissav = []; state.favoritesJable = [];
    state.removedFavorites = {};
  }
  renderFavorites();
  renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
}
function toggleFavorite() {
  if (!state.current) return;
  const src = currentSourceOf(state.current);
  const list = favListForSource(src);
  const idx = list.findIndex(v => v.code === state.current.code);
  const key = favKey(state.current, src);
  if (idx >= 0) {
    list.splice(idx, 1);
    state.removedFavorites[key] = Date.now();
  } else {
    delete state.removedFavorites[key];
    list.unshift(normFavorite(state.current, src));
  }
  if (src === 'jable') state.favoritesJable = applyRemovedFavorites(list, 'jable');
  else state.favoritesMissav = applyRemovedFavorites(list, 'missav');
  saveFavorites(src);
  saveRemovedFavorites();
  renderFavorites();
  renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
  // 只更新收藏按钮和徽章,不重建结果卡(避免 Jable 播放器被销毁)
  const favBtn = document.querySelector('.result-card .actions .fav-toggle');
  if (favBtn) favBtn.textContent = isManualFavorite(state.current) ? '⭐ 取消手动收藏' : '☆ 手动收藏';
  const manualBadge = document.querySelector('.result-card .badge.manual-fav');
  if (isManualFavorite(state.current) && !manualBadge) {
    const badgesEl = document.querySelector('.result-card .badges');
    if (badgesEl) badgesEl.insertAdjacentHTML('beforeend', '<span class="badge saved manual-fav">⭐ 手动收藏</span>');
  } else if (!isManualFavorite(state.current) && manualBadge) {
    manualBadge.remove();
  }
  updateCount();
  scheduleSyncSave();
}
function removeFavorite(src, code) {
  state.removedFavorites[src + ':' + code] = Date.now();
  if (src === 'jable') state.favoritesJable = state.favoritesJable.filter(v => v.code !== code);
  else state.favoritesMissav = state.favoritesMissav.filter(v => v.code !== code);
  saveFavorites(src);
  saveRemovedFavorites();
  renderFavorites();
  renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
  updateCount();
  if (state.current && currentSourceOf(state.current) === src && state.current.code === code) renderResult();
  scheduleSyncSave();
}
function clearFavorites(src) {
  const list = src === 'jable' ? state.favoritesJable : state.favoritesMissav;
  list.forEach(v => { if (v && v.code) state.removedFavorites[src + ':' + v.code] = Date.now(); });
  if (src === 'jable') state.favoritesJable = [];
  else state.favoritesMissav = [];
  localStorage.removeItem(favStorageKey(src));
  saveRemovedFavorites();
  renderFavorites();
  renderActressGrid(($('actressSearch') && $('actressSearch').value) || '');
  updateCount();
  renderResult();
  scheduleSyncSave();
}
function openFavorite(src, code) {
  const list = src === 'jable' ? state.favoritesJable : state.favoritesMissav;
  const fav = list.find(v => String(v && v.code || '').toUpperCase() === String(code || '').toUpperCase());
  if (!fav) return;
  function applyFavorite() {
    document.querySelectorAll('#sourceChips .chip').forEach(c => c.classList.remove('active'));
    const chip = document.querySelector(`#sourceChips .chip[data-source="${src}"]`);
    if (chip) chip.classList.add('active');
    state.source = src;
    state.current = hydrateVideoRef(fav, src) || mergeVideoSnapshot(null, fav, src);
    renderResult();
    scheduleSyncSave();
    closeSidebar();
    $('resultArea').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  loadSourceData(src).then(applyFavorite).catch(e => {
    console.error('openFavorite load source failed:', e);
    applyFavorite();
  });
}
