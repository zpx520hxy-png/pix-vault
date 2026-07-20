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
  // 切换片源时只切换热门区视图；榜单缓存由 trending.js 在页面加载时读取。
  renderTrending();
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
function bindTap(el, fn) {
  if (!el) return;
  let start = null;
  let lastTouch = 0;
  el.addEventListener('touchstart', e => {
    const t = e.changedTouches && e.changedTouches[0];
    if (t) start = { x: t.clientX, y: t.clientY };
  }, { passive: true });
  el.addEventListener('touchend', e => {
    const t = e.changedTouches && e.changedTouches[0];
    if (start && t && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 12) return;
    lastTouch = Date.now();
    e.preventDefault();
    fn(e);
  }, { passive: false });
  el.addEventListener('click', e => {
    if (Date.now() - lastTouch < 450) return;
    fn(e);
  });
}
if ($('sideOpen')) bindTap($('sideOpen'), () => openSidebar('favorites'));
document.querySelectorAll('.side-tab').forEach(b => b.addEventListener('click', () => setSidebarTab(b.dataset.sideTab)));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSidebar(); });

let cardTouchStart = null;
let lastCardTouch = 0;
const videoCardSelector = '.short-card[data-card-action],.browse-card[data-card-action],.hist-card[data-card-action],.fav-card[data-card-action],.trend-card[data-card-action]';
function interactiveChild(target) {
  return target && target.closest && target.closest('a,button,input,textarea,select,label,.card-collapse');
}
function activateVideoCard(card, e) {
  if (!card || interactiveChild(e.target)) return;
  const action = card.dataset.cardAction;
  const code = card.dataset.code || '';
  if (!action || !code) return;
  if (e) { e.preventDefault(); e.stopPropagation(); }
  if (action === 'shortlist') pickShortlist(code);
  else if (action === 'browse') showFromBrowse(code);
  else if (action === 'history') showFromHistory(code);
  else if (action === 'favorite') openFavorite(card.dataset.source || state.source || 'missav', code);
  else if (action === 'trending') openTrendingCard(card, e);
}
document.addEventListener('touchstart', e => {
  const card = e.target.closest && e.target.closest(videoCardSelector);
  if (!card || interactiveChild(e.target)) return;
  const t = e.changedTouches && e.changedTouches[0];
  if (t) cardTouchStart = { x: t.clientX, y: t.clientY, card };
}, { passive: true });
document.addEventListener('touchend', e => {
  const card = e.target.closest && e.target.closest(videoCardSelector);
  if (!card || interactiveChild(e.target)) return;
  const t = e.changedTouches && e.changedTouches[0];
  if (cardTouchStart && cardTouchStart.card === card && t && Math.hypot(t.clientX - cardTouchStart.x, t.clientY - cardTouchStart.y) > 12) return;
  cardTouchStart = null;
  lastCardTouch = Date.now();
  activateVideoCard(card, e);
}, { passive: false });
document.addEventListener('click', e => {
  if (Date.now() - lastCardTouch < 450) return;
  const card = e.target.closest && e.target.closest(videoCardSelector);
  if (card) activateVideoCard(card, e);
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest && e.target.closest(videoCardSelector);
  if (card) activateVideoCard(card, e);
});

const prefersReducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let motionObserver = null;
function motionStorageKey() { return 'missav_picker_motion_enabled_v1'; }
function getMotionPreference() {
  try {
    const value = localStorage.getItem(motionStorageKey());
    if (value === null) {
      localStorage.setItem(motionStorageKey(), '1');
      return '1';
    }
    return value || '';
  } catch (e) { return '1'; }
}
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
  if (document.documentElement) document.documentElement.classList.toggle('motion-off', !active);
  if (document.body) document.body.classList.toggle('motion-off', !active);
  document.querySelectorAll('.motion-reveal').forEach(node => {
    if (!active) {
      node.classList.add('in-view');
      if (motionObserver) motionObserver.unobserve(node);
    } else if (motionObserver) {
      node.classList.remove('in-view');
      motionObserver.observe(node);
    }
  });
  if (!btn) return;
  btn.classList.toggle('active', active);
  btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  btn.title = active ? '关闭动效' : '开启动效';
}

function markMotionReveal(root) {
  const scope = root && root.querySelectorAll ? root : document;
  const selector = 'header, .trending, .filters, .candidate-info, .selected-bar, .roll-btn, .shortlist, #browseArea, #resultArea, .history, .trend-card, .browse-card, .fav-card, .hist-card, .short-card, .result-card, .trash-card';
  const nodes = [];
  if (scope.matches && scope.matches(selector)) nodes.push(scope);
  scope.querySelectorAll(selector).forEach(node => nodes.push(node));
  nodes.forEach((node, index) => {
    if (node.classList.contains('motion-reveal')) return;
    node.classList.add('motion-reveal');
    node.style.setProperty('--motion-delay', Math.min(index % 8, 7) * 42 + 'ms');
    if (!motionAllowed()) node.classList.add('in-view');
    else if (motionObserver) motionObserver.observe(node);
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

  let pointerFrame = null;
  let pointerX = 0;
  let pointerY = 0;
  const updatePointerGlow = () => {
    pointerFrame = null;
    document.documentElement.style.setProperty('--pointer-x', pointerX + 'px');
    document.documentElement.style.setProperty('--pointer-y', pointerY + 'px');
  };
  const showClickPop = (x, y) => {
    const pop = document.createElement('span');
    let removed = false;
    const remove = () => {
      if (removed) return;
      removed = true;
      pop.remove();
    };
    pop.className = 'rocket-milk-spray';
    pop.setAttribute('aria-hidden', 'true');
    pop.innerHTML = '<svg class="rocket-milk-visual" viewBox="0 0 150 150" focusable="false"><path class="rocket-milk-stream" d="M75 142C74 110 57 73 42 41"/><path class="rocket-milk-stream" d="M75 142C87 108 103 77 111 51"/><circle class="rocket-milk-drop" cx="35" cy="30" r="5"/><circle class="rocket-milk-drop" cx="119" cy="39" r="4"/><circle class="rocket-milk-drop" cx="24" cy="56" r="3.5"/><circle class="rocket-milk-drop" cx="130" cy="65" r="2.8"/></svg><svg class="rocket-boob-mark" viewBox="0 0 220 120" focusable="false"><path class="rocket-boob-arc" d="M28 78C31 50 47 34 68 34C88 34 99 48 110 64C121 48 132 34 152 34C173 34 189 50 192 78"/><circle class="rocket-boob-dot" cx="68" cy="62" r="4.5"/><circle class="rocket-boob-dot" cx="152" cy="62" r="4.5"/></svg>';
    pop.style.left = x + 'px';
    pop.style.top = y + 'px';
    pop.addEventListener('animationend', remove, { once: true });
    document.body.appendChild(pop);
    setTimeout(remove, 760);
  };

  document.addEventListener('pointermove', e => {
    if (!motionAllowed() || (e.pointerType && e.pointerType !== 'mouse')) return;
    pointerX = e.clientX;
    pointerY = e.clientY;
    if (pointerFrame === null) pointerFrame = requestAnimationFrame(updatePointerGlow);
  }, { passive: true });
  document.addEventListener('pointerdown', e => {
    if (!motionAllowed()) return;
    showClickPop(e.clientX, e.clientY);
  }, { passive: true });

}

initPageMotion();

function focusResultArea() {
  const area = $('resultArea');
  if (!area) return;
  const active = motionAllowed();
  area.scrollIntoView({ behavior: active ? 'smooth' : 'auto', block: 'center' });
  if (!active) return;
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
    document.querySelectorAll('.rocket-milk-spray').forEach(node => node.remove());
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
  $('browseArea').scrollIntoView({behavior: motionAllowed() ? 'smooth' : 'auto'});
  scheduleSyncSave();
}

function browseGo(page) {
  browsePage = page;
  renderBrowse();
  $('browseArea').scrollIntoView({behavior: motionAllowed() ? 'smooth' : 'auto'});
  scheduleSyncSave();
}
