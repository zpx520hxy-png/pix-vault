// ---- 随机抽 ----
function rollOne() {
  const cands = getCandidates();
  if (cands.length === 0) return;
  // 排除历史上已随机过的
  let pool = cands.filter(v => !state.history.some(h => h.code === v.code));
  if (pool.length === 0) {
    // 全部抽过了,清空历史重新来
    state.history = [];
    pool = cands;
  }
  const v = pool[Math.floor(Math.random() * pool.length)];
  state.current = v;
  // 历史(去重,前置)
  state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
  saveHistory();
  renderResult();
  renderHistory();
  scheduleSyncSave();
}

function sampleUnique(list, count) {
  const pool = list.slice();
  const picked = [];
  while (pool.length && picked.length < count) {
    const idx = Math.floor(Math.random() * pool.length);
    picked.push(pool.splice(idx, 1)[0]);
  }
  return picked;
}

function rollShortlist() {
  const cands = getCandidates();
  if (cands.length === 0) return;
  const fresh = cands.filter(v => !state.history.some(h => h.code === v.code));
  const pool = fresh.length >= 6 ? fresh : cands;
  state.shortlist = sampleUnique(pool, Math.min(6, pool.length));
  renderShortlist();
  $('shortlistArea').style.display = 'block';
  $('shortlistArea').scrollIntoView({behavior:'smooth', block:'center'});
  scheduleSyncSave();
}

function pickShortlist(code) {
  const v = state.shortlist.find(x => x.code === code);
  if (!v) return;
  state.current = v;
  state.history = [v, ...state.history.filter(h => h.code !== v.code)].slice(0, 12);
  saveHistory();
  renderResult();
  renderHistory();
  scheduleSyncSave();
}

function clearShortlist() {
  state.shortlist = [];
  renderShortlist();
  scheduleSyncSave();
}

function renderShortlist() {
  const area = $('shortlistArea');
  const grid = $('shortlistGrid');
  if (!state.shortlist.length) {
    area.style.display = 'none';
    grid.innerHTML = '';
    return;
  }
  area.style.display = 'block';
  $('shortlistTitle').textContent = `🎰 本轮候选 · ${state.shortlist.length} 部（点卡片选中）`;
  grid.innerHTML = state.shortlist.map(v => {
    const src = currentSourceOf(v);
    const actress = (v.actresses || []).slice(0, 2).join('、') || '未知女优';
    return `
      <div class="short-card" onclick="pickShortlist('${v.code}')" title="点选 ${v.code}">
        <div class="img-wrap">
          <img src="${coverUrl(v)}" alt="${v.code}" loading="lazy" decoding="async" referrerpolicy="no-referrer"
            onerror="if(this.dataset.fallback){this.parentElement.style.background='var(--border)';this.style.display='none';}else{this.dataset.fallback='1';this.src='${p(v.cover || "")}';}">
        </div>
        <div class="info">
          <div class="code">${v.code}</div>
          <div class="title">${v.title || '（无标题）'}</div>
          <div class="meta">${actress}${v.date ? ' · ' + v.date : ''}</div>
        </div>
      </div>`;
  }).join('');
}
