/* 播放执行：把 command 变成 audio 的动作，并统计真实播放时长。 */
/* ---------- 命令 ---------- */

function runCommand(command) {
  if (!command || command.seq === state.commandSeq) return;
  state.commandSeq = command.seq;
  if (command.kind === "stop") {
    stopAudio();
    return;
  }
  loadTrack(command);
}

function loadTrack(command) {
  if (!command.url) {
    stopAudio();
    if (command.reason === "media") showNotice(T("player.notice.media_server"));
    return;
  }
  window.clearTimeout(state.startTimer);
  state.playedMs = 0;
  state.lastTick = performance.now();
  state.failedFor = null;
  state.pendingSeek = Math.max(0, command.position_ms || 0);
  state.autoplay = !!command.autoplay;
  audio.src = command.url;
  audio.load();
  setPlayingUI(state.autoplay);
  if (state.autoplay) {
    state.startTimer = window.setTimeout(function () {
      if (audio.paused && audio.readyState < 3) reportFailed("timeout");
    }, 5000);
  }
}

function stopAudio() {
  window.clearTimeout(state.startTimer);
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  state.playedMs = 0;
  state.pendingSeek = null;
  setPlayingUI(false);
  renderProgress();
}

function playAudio() {
  const result = audio.play();
  if (result && typeof result.catch === "function") {
    result.catch(function (error) {
      if (error && error.name === "NotAllowedError") {
        showNotice(T("player.notice.autoplay_blocked"));
        setPlayingUI(false);
      } else {
        reportFailed("play");
      }
    });
  }
}

function togglePlay() {
  if (!state.data || !state.data.track) return;
  if (audio.paused) playAudio();
  else audio.pause();
}

function reportFailed(reason) {
  const data = state.data;
  const md5 = data && data.track ? data.track.md5 : "";
  if (!md5 || state.failedFor === md5) return;
  state.failedFor = md5;
  window.clearTimeout(state.startTimer);
  call("track_failed", md5, reason).then(apply);
}

function reportPosition() {
  if (!state.data || !state.data.track) return;
  const ms = Math.round((audio.currentTime || 0) * 1000);
  if (!isFinite(ms)) return;
  call("report_position", ms);
}

function callTrack(method) {
  const data = state.data;
  const md5 = data && data.track ? data.track.md5 : "";
  call(method, md5, Math.round(state.playedMs)).then(apply);
}

/* ---------- 进度 ---------- */

function durationMs() {
  if (isFinite(audio.duration) && audio.duration > 0) return audio.duration * 1000;
  return state.data && state.data.track ? state.data.track.duration_ms || 0 : 0;
}

function setFill(slider, ratio) {
  const percent = Math.round(Math.min(1, Math.max(0, ratio)) * 1000) / 10;
  slider.style.setProperty("--fill", percent + "%");
}

function renderProgress() {
  const duration = durationMs();
  const track = state.data && state.data.track ? state.data.track : null;
  let position;
  if (state.draggingSeek) {
    position = (Number(qs("#seek").value) / 1000) * duration;
  } else if (audio.getAttribute("src")) {
    position = Math.max(0, (audio.currentTime || 0) * 1000);
  } else {
    // 还没有载入音频时用快照里的位置，避免恢复时先闪一下 0:00
    position = track ? Math.max(0, track.position_ms || 0) : 0;
  }
  qs("#time-elapsed").textContent = formatDuration(position);
  qs("#time-total").textContent =
    duration > 0 ? formatDuration(duration) : T("player.time_unknown");
  const seek = qs("#seek");
  seek.disabled = duration <= 0;
  const ratio = duration > 0 ? Math.min(1, position / duration) : 0;
  if (!state.draggingSeek) seek.value = String(Math.round(ratio * 1000));
  setFill(seek, ratio);
}

function setPlayingUI(playing) {
  const button = qs("#play");
  button.dataset.playing = playing ? "true" : "false";
  button.setAttribute("aria-label", T(playing ? "player.action.pause" : "player.action.play"));
}

function stepVolume(delta) {
  const slider = qs("#volume");
  const value = Math.min(100, Math.max(0, Number(slider.value) + delta));
  slider.value = String(value);
  audio.volume = value / 100;
  if (state.data) state.data.volume = value / 100;
  setFill(slider, value / 100);
  qs("#volume-value").textContent = value + "%";
  call("set_volume", value / 100);
}

function seekBy(delta) {
  const duration = durationMs();
  if (duration <= 0) return;
  const target = Math.min(duration, Math.max(0, (audio.currentTime || 0) * 1000 + delta));
  audio.currentTime = target / 1000;
  renderProgress();
  reportPosition();
}

function tick() {
  const now = performance.now();
  if (!audio.paused && !audio.ended) {
    state.playedMs += Math.min(now - state.lastTick, 500);
  }
  state.lastTick = now;
  if (!state.draggingSeek) renderProgress();
  state.ticks += 1;
  if (state.ticks % 8 === 0 && !audio.paused) reportPosition();
}
