function renderBrowse() {
  const cands = getCandidates();
  const totalPages = Math.ceil(cands.length / BROWSE_PER);
  const start = browsePage * BROWSE_PER;
  const end = Math.min(start + BROWSE_PER, cands.length);
  const show = cands.slice(start, end);
  $('browseTitle').textContent = cands.length
    ? `🖼 ${cands.length} 部作品 · 第 ${browsePage + 1} / ${totalPages} 页`
    : '🖼 0 部作品';
  $('browseGrid').innerHTML = show.map(v => `
    <div class="browse-card" onclick="showFromBrowse(${jsArg(v.code)})">
      <div class="bc-cover">
        <img src="${escHtml(coverUrl(v))}" data-fallback-cover="${escHtml(fallbackCoverUrl(v))}" onload="handleCoverLoad(this)" alt="${escHtml(v.code)}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
          onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='${escHtml(fallbackCoverUrl(v))}';}else if(!this.dataset.fallback2){this.dataset.fallback2='1';this.src='${escHtml(p(v.cover || ""))}';}else{this.parentElement.style.background='var(--border)';this.style.display='none';}">
        <div class="bc-preview" data-preview-src="${escHtml(previewUrl(v))}" data-poster="${escHtml(p(v.cover))}"></div>
      </div>
      <div class="bc-info">
        <div class="bc-code">${escHtml(v.code)}</div>
        <div class="bc-title">${escHtml(v.title)}</div>
      </div>
    </div>
  `).join('');
  prewarmCoverBatch(show, 30);

  // 渲染分页器
  const pager = $('browsePager');
  if (totalPages <= 1) { pager.innerHTML = ''; return; }
  let html = '';
  html += `<button class="btn btn-ghost" onclick="browseGo(${browsePage - 1})" ${browsePage === 0 ? 'disabled' : ''} style="font-size:11px;padding:4px 10px;">◀ 上一页</button>`;
  // 页码: 最多显示 7 个
  let pStart = Math.max(0, browsePage - 3);
  let pEnd = Math.min(totalPages, pStart + 7);
  if (pEnd - pStart < 7) pStart = Math.max(0, pEnd - 7);
  for (let p = pStart; p < pEnd; p++) {
    const active = p === browsePage ? ' style="background:var(--primary);color:#fff;"' : '';
    html += `<button class="btn btn-ghost" onclick="browseGo(${p})"${active} style="font-size:11px;padding:4px 10px;">${p + 1}</button>`;
  }
  html += `<button class="btn btn-ghost" onclick="browseGo(${browsePage + 1})" ${browsePage >= totalPages - 1 ? 'disabled' : ''} style="font-size:11px;padding:4px 10px;">下一页 ▶</button>`;
  pager.innerHTML = html;
}

function showFromBrowse(code) {
  if (!DATA || !DATA.videos) return;
  const v = DATA.videos.find(x => x.code === code);
  if (!v) return;
  state.current = v;
  state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
  saveHistory();
  renderResult();
  renderHistory();
  scheduleSyncSave();
  focusResultArea();
}

document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && e.target === document.body) {
    e.preventDefault(); rollOne();
  }
});
