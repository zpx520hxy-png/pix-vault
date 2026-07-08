// ---- 持久化 ----
function saveHistory() {
  try {
    localStorage.setItem('missav_picker_history',
      JSON.stringify(state.history.map(v => v.code)));
  } catch(e) {}
}
function loadHistory() {
  try {
    const codes = JSON.parse(localStorage.getItem('missav_picker_history') || '[]');
    state.history = codes
      .map(c => DATA.videos.find(v => v.code === c))
      .filter(Boolean);
    renderHistory();
  } catch(e) {}
}

function clearHistory() {
  state.history = [];
  localStorage.removeItem('missav_picker_history');
  renderHistory();
  scheduleSyncSave();
}

function selectAllActresses() {
  for (const gid of ['savedGrid','rookieGrid','otherGrid']) {
    $(gid).querySelectorAll('.actress-chip').forEach(c => {
      state.actresses.add(c.dataset.actress);
      c.classList.add('active');
    });
  }
  updateCount();
  scheduleSyncSave();
}

function deselectAllActresses() {
  state.actresses.clear();
  document.querySelectorAll('.actress-chip.active').forEach(c => c.classList.remove('active'));
  updateCount();
  scheduleSyncSave();
}

function selectActressSection(gridId) {
  const grid = $(gridId);
  if (!grid) return;
  grid.querySelectorAll('.actress-chip').forEach(c => {
    state.actresses.add(c.dataset.actress);
    c.classList.add('active');
  });
  updateCount();
  scheduleSyncSave();
}

function deselectActressSection(gridId) {
  const grid = $(gridId);
  if (!grid) return;
  grid.querySelectorAll('.actress-chip').forEach(c => {
    state.actresses.delete(c.dataset.actress);
    c.classList.remove('active');
  });
  updateCount();
  scheduleSyncSave();
}

function selectAllTags() {
  document.querySelectorAll('#tagChips .chip').forEach(c => {
    state.tags.add(c.dataset.tag);
    c.classList.add('active');
  });
  updateCount();
  scheduleSyncSave();
}

function deselectAllTags() {
  state.tags.clear();
  document.querySelectorAll('#tagChips .chip').forEach(c => c.classList.remove('active'));
  updateCount();
  scheduleSyncSave();
}
