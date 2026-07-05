// ---- 渲染筛选 UI ----
const EXCLUDE_PRESET = ['BEST', '强奸', '调教', '春药'];

// 按类型过滤的视频池(不包含标签/女优过滤,因为标签本身就是筛选条件)
function getTypePool() {
  if (!DATA || !DATA.videos) return [];
  return DATA.videos.filter(v => {
    if (state.type === 'solo' && v.is_multi) return false;
    if (state.type === 'multi' && !v.is_multi) return false;
    if (state.type === 'saved' && !isFavorite(v)) return false;
    return true;
  });
}

function renderTagChips() {
  if (!DATA) {
    // 初始渲染:用索引数据
    $('tagChips').innerHTML = IDX.tags.slice(0, 24).map(t =>
      `<span class="chip" data-tag="${t}" style="opacity:0.5">${t}<span class="count">${IDX.tag_counts[t]}</span></span>`
    ).join('');
    $('excludeChips').innerHTML = EXCLUDE_PRESET.map(t =>
      `<span class="chip" data-extag="${t}" style="opacity:0.5">🚫 ${t}</span>`
    ).join('');
    return;
  }
  const pool = getTypePool();
  const tc = {};
  for (const v of pool) for (const t of v.tags) tc[t] = (tc[t] || 0) + 1;
  // 按频次排序,取 top 24
  const sorted = Object.entries(tc).sort((a, b) => b[1] - a[1]).slice(0, 24);
  const topSet = new Set(sorted.map(e => e[0]));
  // 如果当前选中的标签不在 top24 里,也保留
  for (const t of state.tags) if (!topSet.has(t) && tc[t]) topSet.add(t);
  // 如果排除的标签不在 top24,也保留
  for (const t of state.excludeTags) if (!topSet.has(t) && tc[t]) topSet.add(t);

  $('tagChips').innerHTML = [...topSet].map(t => {
    const n = tc[t] || 0;
    const dim = n === 0 ? ' style="opacity:0.35"' : '';
    return `<span class="chip" data-tag="${t}"${dim}>${t}<span class="count">${n}</span></span>`;
  }).join('');

  // 恢复 active 态
  for (const t of state.tags) {
    const chip = document.querySelector(`#tagChips .chip[data-tag="${t}"]`);
    if (chip) chip.classList.add('active');
  }
  for (const t of state.excludeTags) {
    const chip = document.querySelector(`#excludeChips .chip[data-extag="${t}"]`);
    if (chip) chip.classList.add('active');
  }

  $('excludeChips').innerHTML = EXCLUDE_PRESET.map(t => {
    const n = tc[t] || 0;
    const dim = n === 0 ? ' style="opacity:0.35"' : '';
    return `<span class="chip" data-extag="${t}"${dim}>🚫 ${t}</span>`;
  }).join('');
  // 恢复 exclude active
  for (const t of state.excludeTags) {
    const chip = document.querySelector(`#excludeChips .chip[data-extag="${t}"]`);
    if (chip) chip.classList.add('active');
  }
}

function chipHTML(a) {
  const sel = state.actresses.has(a) ? ' active' : '';
  const D = DATA || IDX;
  const avatar = (D.actress_avatars || {})[a];
  const dispName = (D.actress_display || {})[a] || a;
  const initial = a.replace(/[（(].*[）)]/g,'').charAt(0);
  const fallback = `<span class="avatar-fallback">${initial}</span>`;
  const imgHtml = avatar
    ? `<img src="${avatar}" alt="${a}" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`
    : '';
  return `<div class="actress-chip${sel}" data-actress="${a}" title="${dispName}">
            <div class="blob">${fallback}${imgHtml}</div>
            <span class="name">${dispName}</span>
          </div>`;
}

function renderActressGrid(filter='') {
  const D = DATA || IDX;
  const groups = D.actress_groups || {};
  const display = D.actress_display || {};

  // classify
  const saved = [], rookie = [], other = [];
  const allActresses = (DATA || IDX).actresses;
  for (const a of allActresses) {
    if (filter && !a.toLowerCase().includes(filter.toLowerCase())) continue;
    const g = groups[a] || 'other';
    if (g === 'saved') saved.push(a);
    else if (g === 'rookie') rookie.push(a);
    else other.push(a);
  }

  function fillGrid(id, list) { $(id).innerHTML = list.map(chipHTML).join(''); }

  fillGrid('savedGrid', saved);
  fillGrid('rookieGrid', rookie);
  fillGrid('otherGrid', other);

  // show/hide headers
  for (const [headerId, gridId, countId, list] of [
    ['savedHeader','savedGrid','savedCount',saved],
    ['rookieHeader','rookieGrid','rookieCount',rookie],
    ['otherHeader','otherGrid','otherCount',other]
  ]) {
    const hdr = $(headerId), cnt = $(countId);
    hdr.style.display = list.length > 0 ? 'flex' : 'none';
    cnt.textContent = list.length;
    // auto-collapse ONLY when truly empty; auto-expand when items arrive
    const section = hdr.parentElement;
    if (list.length === 0) {
      if (!section.classList.contains('collapsed')) section.classList.add('collapsed');
    } else {
      section.classList.remove('collapsed');
    }
  }
}

// ---- 候选过滤 ----
function getCandidates() {
  return DATA.videos.filter(v => {
    // 类型
    if (state.type === 'solo' && v.is_multi) return false;
    if (state.type === 'multi' && !v.is_multi) return false;
    if (state.type === 'saved' && !isFavorite(v)) return false;
    // 包含标签(任一命中)
    if (state.tags.size > 0) {
      const hit = v.tags.some(t => state.tags.has(t));
      if (!hit) return false;
    }
    // 排除标签
    if (state.excludeTags.size > 0) {
      const exHit = v.tags.some(t => state.excludeTags.has(t));
      if (exHit) return false;
    }
    // 女优
    if (state.actresses.size > 0) {
      const hit = v.actresses.some(a => state.actresses.has(a));
      if (!hit) return false;
    }
    return true;
  });
}

function deselectTag(t) {
  state.tags.delete(t);
  const chip = document.querySelector('#tagChips .chip[data-tag="'+t+'"]');
  if (chip) chip.classList.remove('active');
  renderTagChips(); updateCount();
}
function deselectActress(a) {
  state.actresses.delete(a);
  document.querySelectorAll('.actress-chip').forEach(function(c) {
    if (c.dataset.actress === a) c.classList.remove('active');
  });
  updateCount();
}

function renderSelBar() {
  const sb = $('selectedBar');
  if (!state.actresses.size && !state.tags.size && state.type === 'all') {
    sb.innerHTML = ''; return;
  }
  const D = DATA || IDX;
  const parts = [];
  if (state.type !== 'all') {
    const tl = {all:'',solo:'👤 单人',multi:'👥 多人',saved:'⭐ 仅收藏'}[state.type];
    parts.push('<span class="sel-chip type" data-click="clearType">'+tl+' ×</span>');
  }
  state.tags.forEach(t => parts.push('<span class="sel-chip tag" data-click="dropTag" data-tag="'+t.replace(/"/g,'&quot;')+'">'+t+' ×</span>'));
  state.actresses.forEach(a => {
    const av = (D.actress_avatars || {})[a];
    const disp = (D.actress_display||{})[a] || a;
    const initial = a.replace(/[（(].*[）)]/g,'').charAt(0);
    const img = '<span class="avatar-fallback">'+initial+'</span>' + (av ? '<img src="'+av+'" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : '');
    parts.push('<span class="sel-item" data-click="dropActress" data-actress="'+a.replace(/"/g,'&quot;')+'" title="'+disp.replace(/"/g,'&quot;')+'"><span class="sel-blob">'+img+'</span><span class="sel-name">'+disp+'</span></span>');
  });
  sb.innerHTML = parts.join('');
}

$('selectedBar').addEventListener('click', function(e) {
  const el = e.target.closest('[data-click]'); if (!el) return;
  const action = el.dataset.click;
  if (action === 'clearType') { clearType(); }
  else if (action === 'dropTag') { dropTag(el.dataset.tag); }
  else if (action === 'dropActress') { dropActress(el.dataset.actress); }
});

function dropTag(t) { state.tags.delete(t); renderTagChips(); updateCount(); }
function dropActress(a) {
  state.actresses.delete(a);
  document.querySelectorAll('.actress-chip').forEach(c => { if (c.dataset.actress === a) c.classList.remove('active'); });
  updateCount();
}
function clearType() {
  state.type = 'all';
  document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.remove('active'));
  document.querySelector('#typeChips .chip[data-type="all"]').classList.add('active');
  renderTagChips(); updateCount();
}

function updateCount() {
  const n = getCandidates().length;
  $('candidateCount').textContent = n;
  $('rollBtn').disabled = n === 0;
  $('shortlistBtn').disabled = n === 0;
  renderSelBar();
}
