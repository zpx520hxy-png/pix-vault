function renderBrowse() {
  const cands = getCandidates();
  const totalPages = Math.ceil(cands.length / BROWSE_PER);
  const start = browsePage * BROWSE_PER;
  const end = Math.min(start + BROWSE_PER, cands.length);
  const show = cands.slice(start, end);
  $('browseTitle').textContent = `🖼 ${cands.length} 部作品 · 第 ${browsePage + 1} / ${totalPages} 页`;
  $('browseGrid').innerHTML = show.map(v => `
    <div class="browse-card" onclick="window.open('${v.url}','_blank')">
      <div class="bc-cover">
        <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
          onerror="if(this.dataset.fallback){this.parentElement.style.background='var(--border)';this.style.display='none';}else{this.dataset.fallback='1';this.src='${p(v.cover || "")}';}">
        <div class="bc-preview">
          <video data-hls-src="${previewUrl(v)}" muted loop playsinline disableRemotePlayback referrerpolicy="no-referrer" preload="none"
            poster="${p(v.cover)}"></video>
        </div>
      </div>
      <div class="bc-info">
        <div class="bc-code">${v.code}</div>
        <div class="bc-title">${v.title}</div>
      </div>
    </div>
  `).join('');

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

document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && e.target === document.body) {
    e.preventDefault(); rollOne();
  }
});
