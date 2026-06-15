const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// ── 状态 ──
const S = {
  history: [],        // [{path, name, size, tags, category}, ...]
  histIdx: -1,
  categories: [],
  activeCats: new Set(),
  activeTags: new Set(),
  allTags: [],
  tagCounts: {},
  isGallery: false,
  fromGallery: false,  // 从网格点进来的，显示关闭按钮
  slideshow: null,
  slideshowSec: 5,
  seqMode: false,     // true=顺序播放, false=随机
  seqPool: [],        // 顺序模式下的全量排序列表
  seqIdx: 0,          // 当前在 seqPool 中的索引
  poolSize: 0,
  favPaths: new Set(),
  favCount: 0,
  dislikePaths: new Set(),
  dislikeCount: 0,
};

// ── API ──
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

function buildQuery() {
  const p = [];
  const cats = [...S.activeCats];
  if (cats.length < S.categories.length) p.push('cats=' + cats.join(','));
  const tags = [...S.activeTags];
  if (tags.length) p.push('tags=' + tags.join(','));
  return p.length ? '?' + p.join('&') : '';
}

// ── 初始化 ──
async function init() {
  showLoading(true);
  try {
    const data = await api('/api/cats');
    S.categories = data.categories;
    S.allTags = data.tags || [];
    S.tagCounts = data.tagCounts || {};
    S.favCount = data.favCount || 0;
    S.activeCats = new Set(data.categories.map(c => c.name));
    S.seqMode = false;
    updateModeUI();
    await loadFavorites();
    await loadDislikes();
    renderCatBar();
    renderTagBar();
    updateFavChip();
    updateCountLabel();
    await randomImage();
  } catch(e) { toast('无法连接服务器'); }
  showLoading(false);
}

async function refresh() {
  await api('/api/rescan');
  const data = await api('/api/cats');
  S.categories = data.categories;
  S.allTags = data.tags || [];
  S.tagCounts = data.tagCounts || {};
  S.favCount = data.favCount || 0;
  const validCats = new Set(data.categories.map(c => c.name));
  for (const c of S.activeCats) { if (!validCats.has(c)) S.activeCats.delete(c); }
  if (S.activeCats.size === 0 && data.categories.length > 0) S.activeCats.add(data.categories[0].name);
  await loadFavorites();
  await loadDislikes();
  renderCatBar();
  renderTagBar();
  updateCountLabel();
}

function updateCountLabel() {
  let total = 0;
  for (const c of S.categories) { if (S.activeCats.has(c.name)) total += c.count; }
  S.poolSize = total;
  $('#count-label').textContent = `${total} 张`;
}

// ── 标签栏 ──
function renderTagBar() {
  const bar = $('#tag-bar');
  bar.innerHTML = '';
  const tagColors = { '写实': 't-写实', '动漫': 't-动漫', '大胸': 't-大胸', '欧美': 't-欧美', '东亚': 't-东亚', 'NSFW': 't-NSFW', '正常': 't-正常' };
  for (const tag of S.allTags) {
    const chip = document.createElement('span');
    const extraCls = tagColors[tag] || '';
    chip.className = 'chip tag-chip ' + extraCls + (S.activeTags.has(tag) ? ' on' : '');
    chip.innerHTML = tag;
    chip.addEventListener('click', () => toggleTag(tag));
    bar.appendChild(chip);
  }
  // 同步侧边栏
  renderSidebarChips();
}

function toggleTag(tag) {
  if (S.activeTags.has(tag)) S.activeTags.delete(tag);
  else S.activeTags.add(tag);
  renderTagBar();
  onFilterChanged();
}

// ── 分类栏 ──
function renderCatBar() {
  const bar = $('#cat-bar');
  bar.innerHTML = '';
  for (const cat of S.categories) {
    const chip = document.createElement('span');
    chip.className = 'chip' + (S.activeCats.has(cat.name) ? ' on' : '');
    chip.innerHTML = `${cat.name.replace(/_/g,' ')}<span class="n">${cat.count}</span>`;
    chip.addEventListener('click', () => toggleCat(cat.name));
    bar.appendChild(chip);
  }
  renderSidebarChips();
}

// ── 侧边栏（手机）──
function renderSidebarChips() {
  const tagColors = { '写实': 't-写实', '动漫': 't-动漫', '大胸': 't-大胸', '欧美': 't-欧美', '东亚': 't-东亚', 'NSFW': 't-NSFW', '正常': 't-正常' };
  // 标签
  const st = $('#sidebar-tags');
  const allTagsOn = S.allTags.every(t => S.activeTags.has(t));
  st.innerHTML = '<div class="sh">🏷️ 喜好标签 <button class="sh-btn">' + (allTagsOn ? '全取消' : '全选') + '</button></div>';
  st.querySelector('.sh-btn').addEventListener('click', () => {
    if (allTagsOn) { S.activeTags.clear(); }
    else { S.allTags.forEach(t => S.activeTags.add(t)); }
    renderTagBar();
    onFilterChanged();
  });
  const tagChips = document.createElement('div');
  tagChips.className = 'chip-bar';
  for (const tag of S.allTags) {
    const chip = document.createElement('span');
    const cls = tagColors[tag] || '';
    chip.className = 'chip tag-chip ' + cls + (S.activeTags.has(tag) ? ' on' : '');
    chip.innerHTML = tag;
    chip.addEventListener('click', () => { toggleTag(tag); });
    tagChips.appendChild(chip);
  }
  st.appendChild(tagChips);

  // 分类
  const sc = $('#sidebar-cats');
  const allCatsOn = S.categories.every(c => S.activeCats.has(c.name));
  sc.innerHTML = '<div class="sh">📁 文件夹 <button class="sh-btn">' + (allCatsOn ? '全取消' : '全选') + '</button></div>';
  sc.querySelector('.sh-btn').addEventListener('click', () => {
    if (allCatsOn) { S.activeCats.clear(); }
    else { S.categories.forEach(c => S.activeCats.add(c.name)); }
    renderCatBar();
    onFilterChanged();
  });
  const catChips = document.createElement('div');
  catChips.className = 'chip-bar';
  for (const cat of S.categories) {
    const chip = document.createElement('span');
    chip.className = 'chip' + (S.activeCats.has(cat.name) ? ' on' : '');
    chip.innerHTML = `${cat.name.replace(/_/g,' ')}<span class="n">${cat.count}</span>`;
    chip.addEventListener('click', () => { toggleCat(cat.name); });
    catChips.appendChild(chip);
  }
  sc.appendChild(catChips);
}

function toggleSidebar() {
  const open = $('#sidebar').classList.toggle('open');
  $('#sidebar-overlay').classList.toggle('open', open);
}
$('#hamburger').addEventListener('click', toggleSidebar);
$('#sidebar-overlay').addEventListener('click', toggleSidebar);

function toggleCat(name) {
  if (S.activeCats.has(name)) {
    S.activeCats.delete(name);
  } else {
    S.activeCats.add(name);
  }
  renderCatBar();
  updateCountLabel();
  if (S.activeCats.size === 0) {
    showEmpty('未选择分类', '请在上方至少勾选一个文件夹');
    S.poolSize = 0;
  } else {
    onFilterChanged();
  }
}

function onFilterChanged() {
  S.history = [];
  S.histIdx = -1;
  if (S.seqMode) {
    loadSeqPool().then(() => {
      if (S.seqPool.length > 0) {
        S.seqIdx = 0;
        addToHistory(S.seqPool[0]);
      }
    });
  } else {
    randomImage();
  }
}

// ── 模态框（收藏夹/不喜欢 网格浏览）──
let _modalType = ''; // 'fav' or 'dislike'
let _modalSel = new Set(); // 批量选中索引
let _modalMode = ''; // '' or 'batch'

async function openFavModal() {
  const favs = await api('/api/favorites');
  _modalType = 'fav';
  _modalSel.clear();
  _modalMode = '';
  showModalGrid('♥ 收藏夹 (' + favs.count + ')', favs.images);
}

async function openDislikeModal() {
  const dl = await api('/api/dislikes');
  const images = [];
  for (const p of dl.paths) {
    const parts = p.split('/');
    images.push({
      path: p,
      name: parts[parts.length - 1],
      size: 0,
      category: parts.length > 1 ? parts[0] : '',
      tags: [],
    });
  }
  _modalType = 'dislike';
  _modalSel.clear();
  _modalMode = '';
  showModalGrid('💔 不喜欢 (' + dl.count + ')', images);
}

function showModalGrid(title, images) {
  $('#modal-title').innerHTML = title
    + ' <button class="sh-btn" id="modal-batch-btn" style="font-size:12px">☐ 批量</button>';
  $('#modal-batch-btn').addEventListener('click', toggleModalBatch);

  const grid = $('#modal-grid');
  grid.innerHTML = '';
  if (images.length === 0) {
    grid.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-dim)">空空如也</div>';
  }
  images.forEach((img, i) => {
    const item = document.createElement('div');
    item.className = 'mg-item';
    item.dataset.idx = i;
    item.innerHTML = `<img src="/img/${img.path}" loading="lazy"
      onerror="this.parentElement.remove()"><div class="mg-name">${img.name}</div>
      <button class="mg-cancel" data-idx="${i}">✕</button>
      <div class="mg-check" data-idx="${i}"></div>`;
    // 点击图片放大
    item.querySelector('img').addEventListener('click', (e) => {
      if (_modalMode === 'batch') return;
      e.stopPropagation();
      $('#mp-img').src = '/img/' + img.path;
      $('#modal-preview').classList.add('open');
    });
    // 点击 x 取消
    item.querySelector('.mg-cancel').addEventListener('click', async (e) => {
      e.stopPropagation();
      if (_modalType === 'fav') {
        await api('/api/unfavorite', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: img.name})
        });
        S.favPaths.delete(img.name);
        S.favCount = Math.max(0, S.favCount - 1);
        updateFavChip();
      } else {
        await api('/api/undislike', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({path: img.path})
        });
        S.dislikePaths.delete(img.path);
        S.dislikeCount = Math.max(0, S.dislikeCount - 1);
        updateDislikeUI();
      }
      item.style.opacity = '0.3';
      item.querySelector('.mg-cancel').remove();
      toast('已取消');
    });
    // 批量模式：点击选中
    item.querySelector('.mg-check').addEventListener('click', (e) => {
      if (_modalMode !== 'batch') return;
      e.stopPropagation();
      if (_modalSel.has(i)) { _modalSel.delete(i); item.classList.remove('sel'); }
      else { _modalSel.add(i); item.classList.add('sel'); }
    });
    grid.appendChild(item);
  });
  $('#modal-overlay').classList.add('open');
}

function toggleModalBatch() {
  _modalMode = _modalMode === 'batch' ? '' : 'batch';
  _modalSel.clear();
  const grid = $('#modal-grid');
  grid.classList.toggle('batch-mode', _modalMode === 'batch');
  $('#modal-batch-btn').textContent = _modalMode === 'batch' ? '☑ 完成' : '☐ 批量';

  if (_modalMode === 'batch') {
    // 添加底部确认栏
    const bar = document.createElement('div');
    bar.id = 'modal-batch-bar';
    bar.innerHTML = `<span>选中 0 项</span><button id="modal-batch-confirm">确认取消</button>`;
    bar.querySelector('#modal-batch-confirm').addEventListener('click', batchCancelModal);
    $('#modal-overlay').appendChild(bar);
  } else {
    const bar = document.getElementById('modal-batch-bar');
    if (bar) bar.remove();
    grid.querySelectorAll('.mg-item').forEach(el => el.classList.remove('sel'));
  }
}

async function batchCancelModal() {
  const grid = $('#modal-grid');
  const items = grid.querySelectorAll('.mg-item');
  const imagePaths = [];
  items.forEach(el => {
    if (el.classList.contains('sel')) {
      const img = el.querySelector('img');
      imagePaths.push({ src: img.src.replace('/img/', ''), el });
    }
  });

  let count = 0;
  for (const { src, el } of imagePaths) {
    try {
      if (_modalType === 'fav') {
        const name = src.split('/').pop();
        await api('/api/unfavorite', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({name})});
        S.favPaths.delete(name);
        S.favCount = Math.max(0, S.favCount - 1);
      } else {
        await api('/api/undislike', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({path: src})});
        S.dislikePaths.delete(src);
        S.dislikeCount = Math.max(0, S.dislikeCount - 1);
      }
      el.style.opacity = '0.2';
      el.classList.remove('sel');
      count++;
    } catch(e) {}
  }
  updateFavChip();
  updateDislikeUI();
  _modalSel.clear();
  toast(`已取消 ${count} 项`);
  // 重新刷新模态内容
  if (_modalType === 'fav') openFavModal();
  else openDislikeModal();
}

function closeModal() {
  $('#modal-overlay').classList.remove('open');
  $('#modal-grid').innerHTML = '';
  const bar = document.getElementById('modal-batch-bar');
  if (bar) bar.remove();
  _modalMode = '';
  _modalSel.clear();
}

$('#modal-close').addEventListener('click', closeModal);
$('#modal-overlay').addEventListener('click', (e) => {
  if (e.target === $('#modal-overlay')) closeModal();
});

$('#mp-close').addEventListener('click', () => {
  $('#modal-preview').classList.remove('open');
});
$('#modal-preview').addEventListener('click', (e) => {
  if (e.target === $('#modal-preview')) $('#modal-preview').classList.remove('open');
});
async function loadFavorites() {
  try {
    const favs = await api('/api/favorites');
    S.favPaths = new Set(favs.images.map(f => f.name));
    S.favCount = favs.count;
    updateFavChip();
  } catch(e) {}
}

function updateFavChip() {
  const chip = $('#fav-chip');
  chip.innerHTML = `♥ 收藏夹<span class="n">${S.favCount}</span>`;
}

async function toggleFavorite() {
  if (S.histIdx < 0 || S.histIdx >= S.history.length) return;
  const img = S.history[S.histIdx];
  const name = img.name;

  if (S.favPaths.has(name)) {
    // 取消收藏
    try {
      const res = await api('/api/unfavorite', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: name})
      });
      if (res.ok) {
        S.favPaths.delete(name);
        S.favCount = Math.max(0, S.favCount - 1);
        updateFavChip();
        updateCountLabel();
        updateInfo(img);
        toast('已取消收藏: ' + name);
      } else {
        toast('取消失败: ' + (res.error || ''));
      }
    } catch(e) { toast('取消失败'); }
    return;
  }

  // 添加收藏
  try {
    const res = await api('/api/favorite', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: img.path})
    });
    if (res.ok) {
      S.favPaths.add(name);
      S.favCount++;
      updateFavChip();
      updateCountLabel();
      showFavToast();
      updateInfo(img);
    } else {
      toast('收藏失败: ' + (res.error || ''));
    }
  } catch(e) { toast('收藏失败'); }
}

function showFavToast() {
  const el = $('#favorite-toast');
  el.classList.remove('pop-out');
  el.classList.add('pop');
  clearTimeout(el._t);
  el._t = setTimeout(() => {
    el.classList.add('pop-out');
    el.classList.remove('pop');
  }, 800);
}

// ── 不喜欢 ──
async function loadDislikes() {
  try {
    const res = await api('/api/dislikes');
    S.dislikePaths = new Set(res.paths);
    S.dislikeCount = res.count;
    updateDislikeUI();
  } catch(e) {}
}

function updateDislikeUI() {
  const chip = $('#dislike-chip');
  chip.innerHTML = `💔 不喜欢<span class="n">${S.dislikeCount}</span>`;
  if (S.dislikeCount > 0) {
    chip.classList.add('has-items');
    $('#btn-delete-disliked').classList.add('show');
    $('#btn-clear-dislikes').style.display = 'inline-block';
  } else {
    chip.classList.remove('has-items');
    $('#btn-delete-disliked').classList.remove('show');
    $('#btn-clear-dislikes').style.display = 'none';
  }
}

async function clearDislikes() {
  if (S.dislikeCount === 0) return;
  try {
    await api('/api/clear_dislikes', {method: 'POST'});
    S.dislikePaths.clear();
    S.dislikeCount = 0;
    updateDislikeUI();
    toast('已清空不喜欢列表');
  } catch(e) { toast('操作失败'); }
}

async function toggleDislike() {
  if (S.histIdx < 0 || S.histIdx >= S.history.length) return;
  const img = S.history[S.histIdx];

  if (S.dislikePaths.has(img.path)) {
    // 取消不喜欢
    try {
      const res = await api('/api/undislike', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: img.path})
      });
      if (res.ok) {
        S.dislikePaths.delete(img.path);
        S.dislikeCount = Math.max(0, S.dislikeCount - 1);
        updateDislikeUI();
        updateInfo(img);
        toast('已取消不喜欢');
      }
    } catch(e) { toast('操作失败'); }
  } else {
    // 标记不喜欢
    try {
      const res = await api('/api/dislike', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: img.path})
      });
      if (res.ok) {
        S.dislikePaths.add(img.path);
        S.dislikeCount++;
        updateDislikeUI();
        updateInfo(img);
        toast('👎 已标记不喜欢 (' + S.dislikeCount + ' 张)');
      }
    } catch(e) { toast('操作失败'); }
  }
}

async function deleteDisliked() {
  if (S.dislikeCount === 0) return;
  if (!confirm(`确定要永久删除 ${S.dislikeCount} 张不喜欢的图片吗？此操作不可撤销！`)) return;

  try {
    const res = await api('/api/delete_disliked', {method: 'POST'});
    if (res.ok) {
      S.dislikePaths.clear();
      S.dislikeCount = 0;
      updateDislikeUI();
      toast(`已删除 ${res.deleted} 张图片`);
      // 刷新数据
      await refresh();
      S.history = [];
      S.histIdx = -1;
      randomImage();
    }
  } catch(e) { toast('删除失败'); }
}

// ── 图片加载 ──
let _pendingReq = null;   // AbortController for in-flight /api/random
let _preloadImg = null;   // Image() preloader

async function randomImage() {
  // 网格模式下刷新画廊
  if (S.isGallery) { loadGallery(); return; }

  if (_pendingReq) { _pendingReq.abort(); _pendingReq = null; }
  if (S.activeCats.size === 0) {
    showEmpty('未选择分类', '请在上方至少勾选一个文件夹');
    return;
  }

  const ac = new AbortController();
  _pendingReq = ac;
  try {
    const r = await fetch('/api/random' + buildQuery(), { signal: ac.signal });
    if (!r.ok) throw new Error(r.status);
    const img = await r.json();
    _pendingReq = null;
    if (!img) { showEmpty('无匹配图片', '当前筛选条件无结果，请调整标签或分类'); return; }
    addToHistory(img);
  } catch(e) {
    if (e.name !== 'AbortError') { toast('加载失败'); }
    _pendingReq = null;
  }
}

function showEmpty(title, desc) {
  $('#info-name').textContent = title;
  $('#info-meta').textContent = desc;
  $('#info-tags').innerHTML = '';
  $('#info-fav').style.display = 'none';
}

function addToHistory(img) {
  if (S.activeCats.size === 0) return; // 全不选时不追加
  if (S.histIdx < S.history.length - 1) {
    S.history = S.history.slice(0, S.histIdx + 1);
  }
  S.history.push(img);
  S.histIdx = S.history.length - 1;
  showImage(img);
}

function goBack() {
  if (S.histIdx > 0) {
    S.histIdx--;
    showImage(S.history[S.histIdx]);
  }
}

function goForward() {
  if (S.histIdx < S.history.length - 1) {
    S.histIdx++;
    showImage(S.history[S.histIdx]);
  } else {
    // 历史末尾 → 随机一张
    randomImage();
  }
}

function showImage(img) {
  if (_preloadImg) { _preloadImg.onload = _preloadImg.onerror = null; _preloadImg = null; }

  const el = $('#main-img');
  el.classList.add('fade-out');
  // 等 CSS transition 完成 (200ms) 后换图
  setTimeout(() => {
    el.src = '/img/' + img.path;
    el.onload = () => {
      requestAnimationFrame(() => { el.classList.remove('fade-out'); });
      updateInfo(img);
    };
    el.onerror = () => { el.classList.remove('fade-out'); toast('加载失败: ' + img.name); };
  }, 220);
}

function updateInfo(img) {
  $('#info-name').textContent = img.name;
  const sizeMB = (img.size / 1048576).toFixed(1);
  let meta = img.category + ' · ' + sizeMB + ' MB';
  if (S.history.length > 1) {
    meta += ' · ' + (S.histIdx + 1) + '/' + S.history.length;
  }
  $('#info-meta').textContent = meta;

  // 标签
  const tagsEl = $('#info-tags');
  tagsEl.innerHTML = '';
  if (img.tags && img.tags.length) {
    for (const t of img.tags) {
      const s = document.createElement('span');
      s.textContent = t;
      tagsEl.appendChild(s);
    }
  }

  // 收藏 + 不喜欢状态
  const isFav = S.favPaths.has(img.name);
  const isDisliked = S.dislikePaths.has(img.path);
  let badges = [];
  if (isFav) badges.push('♥ 已收藏 (空格取消)');
  if (isDisliked) badges.push('👎 不喜欢 (D取消)');
  $('#info-fav').style.display = badges.length ? '' : 'none';
  $('#info-fav').textContent = badges.join(' · ');

  // 同步手机栏图标
  $('#mb-fav').innerHTML = isFav ? '♥<span class="mlbl">收藏</span>' : '♡<span class="mlbl">收藏</span>';
  $('#mb-fav').style.color = isFav ? 'var(--rose)' : '';
  $('#mb-dislike').innerHTML = isDisliked ? '👎<span class="mlbl">不喜欢</span>' : '✕<span class="mlbl">不喜欢</span>';
  $('#mb-dislike').style.color = isDisliked ? 'var(--danger)' : '';
}

// ── 随机/顺序模式 & 幻灯片 ──

// 切换随机↔顺序模式
async function toggleSeqMode() {
  S.seqMode = !S.seqMode;
  if (S.seqMode) {
    await loadSeqPool();
  }
  updateModeUI();
  // 载入当前模式的第一张
  S.history = [];
  S.histIdx = -1;
  if (S.seqMode && S.seqPool.length > 0) {
    S.seqIdx = 0;
    addToHistory(S.seqPool[0]);
  } else {
    randomImage();
  }
}

async function loadSeqPool() {
  try {
    S.seqPool = await api('/api/all' + buildQuery());
  } catch(e) {
    S.seqPool = [];
    toast('加载顺序列表失败');
  }
}

// 顺序模式下的下一张
function nextSequential() {
  if (S.seqPool.length === 0) return;
  S.seqIdx = (S.seqIdx + 1) % S.seqPool.length;
  addToHistory(S.seqPool[S.seqIdx]);
}

// 顺序模式下的上一张
function prevSequential() {
  if (S.seqPool.length === 0) return;
  S.seqIdx = (S.seqIdx - 1 + S.seqPool.length) % S.seqPool.length;
  addToHistory(S.seqPool[S.seqIdx]);
}

function updateModeUI() {
  const btn = $('#btn-mode-toggle');
  const mbBtn = $('#mb-random');
  if (S.seqMode) {
    btn.textContent = '📋 顺序';
    btn.classList.add('active');
    mbBtn.innerHTML = '📋<span class="mlbl">顺序</span>';
  } else {
    btn.textContent = '🎲 随机';
    btn.classList.remove('active');
    mbBtn.innerHTML = '🎲<span class="mlbl">随机</span>';
  }
}

function getNextImageFn() {
  return S.seqMode ? nextSequential : randomImage;
}

function toggleSlideshow() {
  if (S.slideshow) {
    stopSlideshow();
  } else {
    startSlideshow();
  }
}

function startSlideshow() {
  stopSlideshow();
  const fn = getNextImageFn();
  const sec = parseInt($('#slide-interval').value) || 5;
  S.slideshow = setInterval(fn, sec * 1000);
  $('#btn-slideshow').classList.add('slideshow-on');
  $('#btn-slideshow').textContent = '⏸ 停止';
  $('#mb-slideshow').innerHTML = '⏸<span class="mlbl">停止</span>';
  const mode = S.seqMode ? '顺序' : '随机';
  toast(mode + '播放 (' + sec + 's)');
}

function stopSlideshow() {
  if (S.slideshow) { clearInterval(S.slideshow); S.slideshow = null; }
  $('#btn-slideshow').classList.remove('slideshow-on');
  $('#btn-slideshow').textContent = '▶ 播放';
  $('#mb-slideshow').innerHTML = '▶<span class="mlbl">播放</span>';
}

// ── 画廊 ──
function toggleGallery() {
  S.isGallery = !S.isGallery;
  S.fromGallery = false;
  $('#gallery-close').classList.remove('show');
  if (S.isGallery) {
    $('#single-mode').style.display = 'none';
    $('#gallery-mode').style.display = 'block';
    $('#main-view').classList.add('gallery');
    $('#btn-mode').classList.add('active');
    // 只在网格为空时才加载
    if (!$('#gallery-grid').children.length) loadGallery();
  } else {
    $('#single-mode').style.display = '';
    $('#gallery-mode').style.display = 'none';
    $('#main-view').classList.remove('gallery');
    $('#btn-mode').classList.remove('active');
  }
}

async function loadGallery() {
  const grid = $('#gallery-grid');
  grid.innerHTML = '';
  showLoading(true);
  try {
    const images = await api('/api/random_batch?n=60' + buildQuery().replace('?','&'));
    for (const img of images) {
      const item = document.createElement('div');
      item.className = 'grid-item';
      item.innerHTML = `<img src="/img/${img.path}" class="lazy" loading="lazy"
        onload="this.classList.replace('lazy','loaded')"
        onerror="this.parentElement.remove()"><div class="g-label">${img.name}</div>`;
      item.addEventListener('click', () => {
        S._galleryScrollY = $('#main-view').scrollTop;
        S.isGallery = false;
        S.fromGallery = true;
        $('#gallery-close').classList.add('show');
        $('#single-mode').style.display = '';
        $('#gallery-mode').style.display = 'none';
        $('#main-view').classList.remove('gallery');
        $('#btn-mode').classList.remove('active');
        if (S.seqMode) {
          const idx = S.seqPool.findIndex(si => si.path === img.path);
          if (idx >= 0) S.seqIdx = idx;
        }
        addToHistory(img);
      });
      grid.appendChild(item);
    }
  } catch(e) { toast('画廊加载失败'); }
  showLoading(false);
}

// ── UI 辅助 ──
function showLoading(on) { $('#loading-indicator').style.display = on ? 'block' : 'none'; }
let toastTimer;
function toast(msg) {
  const el = $('#error-toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
}

// ── 键盘快捷键（带 throttle，防止连点黑屏）──
let _lastNav = 0;
const NAV_COOLDOWN = 180; // ms，快速连点只响应最后一次

function throttledNav(fn) {
  const now = performance.now();
  _lastNav = now;
  setTimeout(() => {
    if (performance.now() - _lastNav >= NAV_COOLDOWN - 10) fn();
  }, NAV_COOLDOWN);
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch (e.key) {
    case 'ArrowLeft':
      e.preventDefault();
      throttledNav(S.seqMode ? prevSequential : goBack);
      break;
    case 'ArrowRight':
      e.preventDefault();
      throttledNav(S.seqMode ? nextSequential : goForward);
      break;
    case ' ':          e.preventDefault(); toggleFavorite(); break;
    case 'q': case 'Q': e.preventDefault(); throttledNav(randomImage); break;
    case 'm': case 'M': e.preventDefault(); toggleSeqMode(); break;
    case 'd': case 'D': e.preventDefault(); toggleDislike(); break;
    case 's': case 'S': toggleSlideshow(); e.preventDefault(); break;
    case 'g': case 'G': toggleGallery(); e.preventDefault(); break;
    case 'r': case 'R': refresh().then(() => randomImage()); e.preventDefault(); break;
    case 'a': case 'A':
      if (S.activeCats.size === S.categories.length) {
        S.activeCats = new Set([S.categories[0]?.name]);
      } else {
        S.activeCats = new Set(S.categories.map(c => c.name));
      }
      renderCatBar();
      updateCountLabel();
      onFilterChanged();
      e.preventDefault();
      break;
    case 'Escape':
      if (S.fromGallery) {
        $('#gallery-close').click();
      } else if ($('#modal-preview').classList.contains('open')) {
        $('#modal-preview').classList.remove('open');
      } else if ($('#modal-overlay').classList.contains('open')) {
        closeModal();
      } else if (S.isGallery) {
        toggleGallery();
      } else {
        stopSlideshow();
      }
      e.preventDefault();
      break;
  }
});

// ── 按钮事件 ──
$('#btn-q').addEventListener('click', () => throttledNav(randomImage));
$('#btn-mode-toggle').addEventListener('click', toggleSeqMode);
$('#btn-left').addEventListener('click', () => {
  throttledNav(S.seqMode ? prevSequential : goBack);
});
$('#btn-right').addEventListener('click', () => {
  throttledNav(S.seqMode ? nextSequential : goForward);
});
$('#fav-chip').addEventListener('click', openFavModal);
$('#dislike-chip').addEventListener('click', openDislikeModal);
$('#btn-delete-disliked').addEventListener('click', deleteDisliked);
$('#btn-clear-dislikes').addEventListener('click', clearDislikes);
$('#btn-mode').addEventListener('click', toggleGallery);
$('#gallery-close').addEventListener('click', () => {
  S.fromGallery = false;
  $('#gallery-close').classList.remove('show');
  toggleGallery();
  // 恢复滚动位置
  if (S._galleryScrollY != null) {
    requestAnimationFrame(() => { $('#main-view').scrollTop = S._galleryScrollY; });
  }
});
$('#btn-slideshow').addEventListener('click', toggleSlideshow);

// 手机虚拟按键
$('#mb-left').addEventListener('click', () => { throttledNav(S.seqMode ? prevSequential : goBack); });
$('#mb-right').addEventListener('click', () => { throttledNav(S.seqMode ? nextSequential : goForward); });
$('#mb-fav').addEventListener('click', toggleFavorite);
$('#mb-dislike').addEventListener('click', toggleDislike);
$('#mb-random').addEventListener('click', toggleSeqMode);
$('#mb-slideshow').addEventListener('click', toggleSlideshow);
$('#btn-refresh').addEventListener('click', async () => {
  await refresh();
  if (S.isGallery) { loadGallery(); return; }
  if (S.seqMode) await loadSeqPool();
  onFilterChanged();
});

// 信息叠加层自动隐藏
let hideInfoTimer;
$('#main-view').addEventListener('mousemove', () => {
  $('#info-overlay').classList.remove('hidden');
  clearTimeout(hideInfoTimer);
  hideInfoTimer = setTimeout(() => $('#info-overlay').classList.add('hidden'), 3000);
});

// 触摸滑动（只在图片区域生效，不影响按钮点击）
let touchStartX = 0, touchStartY = 0, touchOnBtn = false;
$('#main-view').addEventListener('touchstart', e => {
  touchStartX = e.touches[0].clientX;
  touchStartY = e.touches[0].clientY;
  touchOnBtn = e.target.closest('button, .chip, #fav-chip, #dislike-chip, select') !== null;
});
$('#main-view').addEventListener('touchend', e => {
  if (touchOnBtn) return;
  const dx = e.changedTouches[0].clientX - touchStartX;
  const dy = e.changedTouches[0].clientY - touchStartY;
  if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
    throttledNav(dx > 0 ? (S.seqMode ? prevSequential() : goBack())
                         : (S.seqMode ? nextSequential() : goForward()));
  }
});

// 页面回来自动刷新
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    refresh().then(() => { if (S.isGallery) loadGallery(); });
  }
});

init();