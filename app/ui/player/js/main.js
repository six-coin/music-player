/* 启动：绑定事件、拉文案与快照，起计时器。 */
/* ---------- 启动 ---------- */

async function init() {
  bindEvents();
  await loadStrings();
  applyStrings();
  apply(await call("get_state"));
  setPlayingUI(false);
  state.lastTick = performance.now();
  window.setInterval(tick, 250);
}

if (bridge()) {
  init();
} else {
  window.addEventListener("pywebviewready", init, { once: true });
}
