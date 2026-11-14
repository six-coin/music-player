/* 启动：绑定全部事件、拉文案与快照。 */
function bindEvents() {
  bindShellEvents();
  bindPlaylistEvents();
  bindLibraryEvents();
  bindPanelEvents();
}
async function init() {
  bindEvents();
  initSelects();
  await loadStrings();
  applyStrings();
  setupSortSelect();
  apply(await call("get_state"));
}

if (bridge()) {
  init();
} else {
  window.addEventListener("pywebviewready", init, { once: true });
}
