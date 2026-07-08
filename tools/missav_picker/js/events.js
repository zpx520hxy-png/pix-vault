// ---- 事件绑定 ----
// 片源切换
$('sourceChips').addEventListener('click', function(e) {
  var chip = e.target.closest('.chip'); if (!chip) return;
  document.querySelectorAll('#sourceChips .chip').forEach(function(c) { c.classList.remove('active'); });
  chip.classList.add('active');
  var src = chip.dataset.source;
  if (src === state.source) return;
  state.source = src;
  state.current = null;
  state.tags.clear(); state.actresses.clear(); state.type = 'all';
  if (_jpHls) { try { _jpHls.destroy(); } catch(e){} _jpHls = null; }
  if (_jpVideo) { try { _jpVideo.pause(); _jpVideo.removeAttribute('src'); _jpVideo.load(); } catch(e){} _jpVideo = null; }
  $('resultArea').innerHTML = '';
  document.querySelectorAll('#typeChips .chip').forEach(function(c) { c.classList.remove('active'); });
  document.querySelector('#typeChips .chip[data-type="all"]').classList.add('active');
  $('selectedBar').innerHTML = '';
  $('rollBtn').disabled = true;
  $('rollBtn').textContent = '⏳ 加载中...';
  // 切换片源时,刷新热门区
  renderTrending();
  loadTrending();
  if (src === 'jable') {
    DATA = null;
    $('tagChips').innerHTML = '';
    $('excludeChips').innerHTML = '';
    ['savedGrid','rookieGrid','otherGrid'].forEach(function(id) { $(id).innerHTML = ''; });
    fetch('jable_data.json?_=' + Date.now()).then(function(r) { return r.json(); }).then(function(d) {
      DATA = d;
      // jable_data.json schema 是 {source, videos:[...]},顶层没有 actresses
      // 从 videos 提取 unique 女优
      var uniq = {};
      DATA.videos.forEach(function(v){(v.actresses||[]).forEach(function(a){uniq[a]=1});});
      DATA.actresses = Object.keys(uniq);
      $('rollBtn').disabled = false; $('rollBtn').textContent = '🎲 随机抽一部';
      $('stats').textContent = '📊 ' + DATA.videos.length + ' 部作品 · ' + DATA.actresses.length + ' 位女优 · Jable.TV';
      renderTagChips(); renderActressGrid(); renderFavorites(); updateCount();
      scheduleSyncSave();
    });
  } else {
    DATA = null;
    $('tagChips').innerHTML = '';
    ['savedGrid','rookieGrid','otherGrid'].forEach(function(id) { $(id).innerHTML = ''; });
    fetch('picker_index.json?_=' + Date.now()).then(function(r) { return r.json(); }).then(function(d) {
      IDX = d; init('index');
    });
  }
});

$('typeChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  document.querySelectorAll('#typeChips .chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  state.type = chip.dataset.type;
  renderTagChips();
  updateCount();
  scheduleSyncSave();
});

$('tagChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  const tag = chip.dataset.tag;
  if (state.tags.has(tag)) { state.tags.delete(tag); chip.classList.remove('active'); }
  else { state.tags.add(tag); chip.classList.add('active'); }
  updateCount();
  scheduleSyncSave();
});

$('excludeChips').addEventListener('click', (e) => {
  const chip = e.target.closest('.chip'); if (!chip) return;
  const tag = chip.dataset.extag;
  if (state.excludeTags.has(tag)) { state.excludeTags.delete(tag); chip.classList.remove('active'); }
  else { state.excludeTags.add(tag); chip.classList.add('active'); }
  updateCount();
  scheduleSyncSave();
});

for (const gid of ['savedGrid','rookieGrid','otherGrid']) {
  $(gid).addEventListener('click', (e) => {
    const chip = e.target.closest('.actress-chip'); if (!chip) return;
    const name = chip.dataset.actress;
    if (state.actresses.has(name)) {
      state.actresses.delete(name);
      chip.classList.remove('active');
    } else {
      state.actresses.add(name);
      chip.classList.add('active');
    }
    updateCount();
    scheduleSyncSave();
  });
}

$('actressSearch').addEventListener('input', (e) => {
  renderActressGrid(e.target.value);
});

$('rollBtn').addEventListener('click', rollOne);

function openSidebar(tab) {
  const drawer = $('sideDrawer');
  if (!drawer) return;
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  setSidebarTab(tab || 'favorites');
  renderFavorites();
  renderTrash();
}
function closeSidebar() {
  const drawer = $('sideDrawer');
  if (!drawer) return;
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
}
function setSidebarTab(tab) {
  document.querySelectorAll('.side-tab').forEach(b => b.classList.toggle('active', b.dataset.sideTab === tab));
  $('sideFavorites').classList.toggle('active', tab === 'favorites');
  $('sideTrash').classList.toggle('active', tab === 'trash');
}
if ($('sideOpen')) $('sideOpen').addEventListener('click', () => openSidebar('favorites'));
document.querySelectorAll('.side-tab').forEach(b => b.addEventListener('click', () => setSidebarTab(b.dataset.sideTab)));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSidebar(); });

const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let motionPulseTimer = null;
let motionObserver = null;
function motionStorageKey() { return 'missav_picker_motion_enabled_v1'; }
function getMotionPreference() { try { return localStorage.getItem(motionStorageKey()) || ''; } catch (e) { return ''; } }
function setMotionPreference(on) { try { localStorage.setItem(motionStorageKey(), on ? '1' : '0'); } catch (e) {} }
function motionAllowed() {
  const pref = getMotionPreference();
  if (pref === '1') return true;
  if (pref === '0') return false;
  return !prefersReducedMotion;
}
function syncMotionToggle() {
  const btn = $('motionToggle');
  const active = motionAllowed();
  if (document.body) document.body.classList.toggle('motion-off', !active);
  if (!btn) return;
  btn.classList.toggle('active', active);
  btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  btn.title = active ? '关闭动效' : '开启动效';
}

function markMotionReveal(root) {
  const scope = root && root.querySelectorAll ? root : document;
  const selector = 'header, .trending, .playable-jable, .filters, .candidate-info, .selected-bar, .roll-btn, .shortlist, #browseArea, #resultArea, .history, .trend-card, .playable-card, .browse-card, .fav-card, .hist-card, .short-card, .result-card, .trash-card';
  const nodes = [];
  if (scope.matches && scope.matches(selector)) nodes.push(scope);
  scope.querySelectorAll(selector).forEach(node => nodes.push(node));
  nodes.forEach((node, index) => {
    if (node.classList.contains('motion-reveal')) return;
    node.classList.add('motion-reveal');
    node.style.setProperty('--motion-delay', Math.min(index % 8, 7) * 42 + 'ms');
    if (motionObserver) motionObserver.observe(node);
  });
}

function initPageMotion() {
  syncMotionToggle();
  document.body.classList.toggle('motion-force', getMotionPreference() === '1');
  document.body.classList.add('motion-ready');
  motionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('in-view');
      motionObserver.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.12 });

  markMotionReveal(document);
  new MutationObserver(records => {
    records.forEach(record => {
      record.addedNodes.forEach(node => {
        if (node.nodeType === 1) markMotionReveal(node);
      });
    });
  }).observe(document.body, { childList: true, subtree: true });

  document.addEventListener('pointerdown', e => {
    if (!motionAllowed()) return;
    document.documentElement.style.setProperty('--click-x', e.clientX + 'px');
    document.documentElement.style.setProperty('--click-y', e.clientY + 'px');
    document.body.classList.remove('motion-pulse');
    void document.body.offsetWidth;
    document.body.classList.add('motion-pulse');
    clearTimeout(motionPulseTimer);
    motionPulseTimer = setTimeout(() => document.body.classList.remove('motion-pulse'), 900);
  }, { passive: true });

}

initPageMotion();

function focusResultArea() {
  const area = $('resultArea');
  if (!area) return;
  area.scrollIntoView({ behavior: 'smooth', block: 'center' });
  requestAnimationFrame(() => {
    area.classList.remove('result-focus');
    void area.offsetWidth;
    area.classList.add('result-focus');
    setTimeout(() => area.classList.remove('result-focus'), 820);
  });
}

if ($('motionToggle')) $('motionToggle').addEventListener('click', () => {
  const next = !motionAllowed();
  setMotionPreference(next);
  document.body.classList.toggle('motion-force', next && prefersReducedMotion);
  syncMotionToggle();
  if (!next) {
    document.body.classList.remove('motion-pulse');
    return;
  }
  document.body.classList.add('motion-ready');
  if (!motionObserver) initPageMotion();
  document.querySelectorAll('.motion-reveal').forEach(node => node.classList.remove('in-view'));
  markMotionReveal(document);
  requestAnimationFrame(() => {
    document.querySelectorAll('.motion-reveal').forEach((node, index) => {
      setTimeout(() => node.classList.add('in-view'), Math.min(index % 8, 7) * 42);
    });
  });
});

let browsePage = 0;
const BROWSE_PER = 30;

function openBrowse() {
  browsePage = 0;
  renderBrowse();
  $('browseArea').style.display = 'block';
  $('browseArea').scrollIntoView({behavior:'smooth'});
  scheduleSyncSave();
}

function browseGo(page) {
  browsePage = page;
  renderBrowse();
  $('browseArea').scrollIntoView({behavior:'smooth'});
  scheduleSyncSave();
}
