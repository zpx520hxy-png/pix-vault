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
    DATA = null; IDX = null;
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
    DATA = null; IDX = null;
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
