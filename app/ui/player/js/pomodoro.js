/* 番茄钟计时层：预备、阶段推进、音乐 / 环境音 / 提示音、全屏与完成页。 */
/* ---------- 状态 ---------- */

const pomo = {
  active: false,
  plan: null,
  uid: null,
  phaseIndex: 0,
  phase: "focus",
  running: false,
  paused: false,
  prep: false,
  completed: false,
  deadline: 0,
  prepDeadline: 0,
  remaining: 0,
  lastTick: 0,
  lastReport: 0,
  focusCarry: 0,
  restCarry: 0,
  runFocus: 0,
  runRest: 0,
  tickTimer: null,
  ringPlaying: false,
  pendingAfterRing: null,
  ducking: false,
  holdTrack: false,
  musicActive: false,
  musicVolume: 0.5,
  environmentVolume: 0.35,
  fullscreen: false,
  panelTimer: null,
  trackMd5: null,
  playedMs: 0,
  lastAudioTick: 0,
  pendingAutoplay: false,
  finishSnapshot: null,
};

const POMO_FONTS = {
  system: '"Microsoft YaHei", "Segoe UI", "Helvetica Neue", sans-serif',
  hei: '"Microsoft YaHei", "SimHei", "Segoe UI", sans-serif',
  song: '"SimSun", "Songti SC", "Times New Roman", serif',
  kai: '"KaiTi", "STKaiti", "Kaiti SC", serif',
  round: '"YouYuan", "Microsoft YaHei", sans-serif',
  mono: '"Cascadia Mono", "Consolas", "Courier New", monospace',
  serif: 'Georgia, "Times New Roman", "SimSun", serif',
};

function pomoAudio() {
  return qs("#pomo-audio");
}

function pomoAmbient() {
  return qs("#pomo-ambient");
}

function pomoRing() {
  return qs("#pomo-ring");
}

function pomoBackgroundVideo() {
  return qs("#pomo-bg video");
}

/* ---------- 开始 ---------- */

async function startPomodoro() {
  const uid = pomodoroSelectedUid();
  if (!uid || pomo.active) return;
  const result = await call("pomodoro_start", uid, pomoOverridesPayload());
  if (!result || !result.ok) {
    showNotice(T("pomodoro.start_failed"));
    return;
  }
  const plan = result.plan;
  pomo.plan = plan;
  pomo.uid = uid;
  pomo.phaseIndex = 0;
  pomo.phase = "focus";
  pomo.running = false;
  pomo.paused = false;
  pomo.completed = false;
  pomo.prep = true;
  pomo.deadline = 0;
  pomo.remaining = 0;
  pomo.focusCarry = 0;
  pomo.restCarry = 0;
  pomo.runFocus = 0;
  pomo.runRest = 0;
  pomo.lastTick = Date.now();
  pomo.lastReport = Date.now();
  pomo.ringPlaying = false;
  pomo.pendingAfterRing = null;
  pomo.ducking = false;
  pomo.holdTrack = false;
  pomo.musicActive = false;
  pomo.trackMd5 = null;
  pomo.playedMs = 0;
  pomo.musicVolume = Number(plan.music_volume) || 0.5;
  pomo.environmentVolume = Number(plan.environment_volume) || 0.35;
  pomo.finishSnapshot = null;
  pomo.prepDeadline = Date.now() + (Number(plan.prep_seconds) || 120) * 1000;

  audio.pause();
  call("set_playing", false);
  openPomodoroStage();
  startPomodoroTicker();
  renderPomodoros();
}

function openPomodoroStage() {
  const stage = qs("#pomo-stage");
  stage.hidden = false;
  document.body.classList.add("pomo-mode");
  qs("#pomo-done").hidden = true;
  qs("#pomo-confirm").hidden = true;
  qs("#pomo-prep").hidden = false;
  qs(".pomo-hud").hidden = true;
  qs("#pomo-panel").classList.remove("is-visible");
  qs("#pomo-prep-name").textContent = pomo.plan.name || "";
  qs("#pomo-prep-time").textContent = formatDuration(
    Math.max(0, pomo.prepDeadline - Date.now())
  );
  qs("#pomo-bg").innerHTML = "";
  qs("#pomo-bg").className = "pomo-bg";
  applyPomodoroFont(pomo.plan.font);
  qs("#pomo-stage").style.setProperty(
    "--pomo-hud-scale",
    String(Number(pomo.plan.hud_scale) || 1.5)
  );
  syncPomodoroVolumes();
  pomo.active = true;
}

function startPomodoroTicker() {
  window.clearInterval(pomo.tickTimer);
  pomo.tickTimer = window.setInterval(pomodoroTick, 250);
}

function stopPomodoroTicker() {
  window.clearInterval(pomo.tickTimer);
  pomo.tickTimer = null;
}

/* ---------- 计时 ---------- */

function pomodoroTick() {
  const now = Date.now();
  if (pomo.prep) {
    const remaining = pomo.prepDeadline - now;
    qs("#pomo-prep-time").textContent = formatDuration(Math.max(0, remaining));
    pomo.lastTick = now;
    if (remaining <= 0) beginFormalPomodoro();
    return;
  }
  if (!pomo.running || pomo.paused) {
    pomo.lastTick = now;
    return;
  }

  const remaining = pomo.deadline - now;
  pomo.remaining = Math.max(0, remaining);
  updatePomodoroHud(pomo.remaining);

  const delta = Math.min(Math.max(0, now - pomo.lastTick), 2000);
  pomo.lastTick = now;
  if (pomo.phase === "focus") {
    pomo.focusCarry += delta;
    pomo.runFocus += delta;
  } else {
    pomo.restCarry += delta;
    pomo.runRest += delta;
  }
  const music = pomoAudio();
  if (music && !music.paused && !music.ended) {
    pomo.playedMs += delta;
  }

  if (pomo.plan && pomo.plan.ring && remaining <= 10000 && !pomo.ducking) {
    pomo.ducking = true;
    pomo.holdTrack = true;
  }
  if (pomo.ducking) updateDuckVolume(remaining);

  if (remaining <= 0) {
    advancePomodoroPhase();
    return;
  }
  if (now - pomo.lastReport >= 10000) reportPomodoroStats();
}

function beginFormalPomodoro() {
  if (!pomo.prep) return;
  pomo.prep = false;
  qs("#pomo-prep").hidden = true;
  qs(".pomo-hud").hidden = false;
  setPomodoroFullscreen(true);
  renderPomodoroBackground(pomo.plan);
  startPomodoroAmbient();
  pomo.phaseIndex = 0;
  pomo.phase = "focus";
  pomo.running = true;
  pomo.paused = false;
  pomo.deadline = Date.now() + pomo.plan.segments[0] * 60000;
  pomo.lastTick = Date.now();
  pomo.lastReport = Date.now();
  updatePomodoroHud(pomo.deadline - Date.now());
  playPomodoroRing(function () {
    applyPomodoroPhaseMusic();
  });
}

function advancePomodoroPhase() {
  reportPomodoroStats();
  const segments = (pomo.plan && pomo.plan.segments) || [];
  if (pomo.phaseIndex >= segments.length - 1) {
    finishPomodoro(true);
    return;
  }
  pomo.phaseIndex += 1;
  pomo.phase = pomo.phaseIndex % 2 === 0 ? "focus" : "rest";
  pomo.deadline = Date.now() + segments[pomo.phaseIndex] * 60000;
  pomo.ducking = false;
  pomo.holdTrack = false;
  updatePomodoroHud(pomo.deadline - Date.now());
  playPomodoroRing(function () {
    applyPomodoroPhaseMusic();
  });
}

function updatePomodoroHud(remaining) {
  qs("#pomo-phase").textContent = T("pomodoro.phase." + pomo.phase);
  qs("#pomo-time").textContent = formatDuration(Math.max(0, remaining));
  const segments = (pomo.plan && pomo.plan.segments) || [];
  const next = segments[pomo.phaseIndex + 1];
  qs("#pomo-next").textContent = next
    ? T("pomodoro.next_phase", {
        phase: T("pomodoro.phase." + (pomo.phase === "focus" ? "rest" : "focus")),
        time: formatDuration(next * 60000),
      })
    : T("pomodoro.last_phase");
}

function updateDuckVolume(remaining) {
  const music = pomoAudio();
  if (!music || music.paused) return;
  const ratio = Math.min(1, Math.max(0, remaining / 10000));
  music.dataset.fadeToken = String((Number(music.dataset.fadeToken) || 0) + 1);
  music.volume = Math.min(1, Math.max(0, pomo.musicVolume * (0.12 + 0.88 * ratio)));
}

/* ---------- 阶段音乐 ---------- */

async function applyPomodoroPhaseMusic() {
  if (!pomo.active) return;
  const result = await call("pomodoro_phase", pomo.phaseIndex);
  if (!result || !result.ok) return;
  pomo.musicActive = !!result.play;
  if (!result.play) {
    fadeOutAndPause(pomoAudio());
    return;
  }
  if (result.resume) {
    playAndFade(pomoAudio(), pomo.musicVolume, 800);
    return;
  }
  if (result.command) applyPomodoroCommand(result.command);
}

function applyPomodoroCommand(command) {
  const music = pomoAudio();
  if (!command || command.kind === "stop" || !command.url) {
    fadeOutAndPause(music);
    return;
  }
  music.src = command.url;
  music.volume = 0;
  music.load();
  pomo.trackMd5 = command.md5 || null;
  pomo.playedMs = 0;
  pomo.lastAudioTick = performance.now();
  pomo.pendingAutoplay = !!command.autoplay;
  music.play().catch(function (error) {
    if (error && error.name === "NotAllowedError") {
      showNotice(T("player.notice.autoplay_blocked"));
    } else {
      reportPomodoroAudioFailed("play");
    }
  });
  fadeAudio(music, pomo.musicVolume, 800);
}

function reportPomodoroAudioFailed(reason) {
  if (!pomo.trackMd5) return;
  call("pomodoro_music_failed", pomo.trackMd5, reason).then(function (result) {
    if (result && result.ok) applyPomodoroCommand(result.command);
  });
}

function pomodoroMusicNext() {
  if (!pomo.active || !pomo.trackMd5) return;
  const md5 = pomo.trackMd5;
  const played = Math.round(pomo.playedMs);
  call("pomodoro_music_next", md5, played).then(function (result) {
    if (result && result.ok) applyPomodoroCommand(result.command);
  });
}

function pomodoroMusicEnded() {
  if (!pomo.active || !pomo.trackMd5) return;
  if (pomo.holdTrack) {
    pomoAudio().pause();
    return;
  }
  const md5 = pomo.trackMd5;
  const played = Math.round(pomo.playedMs);
  call("pomodoro_music_ended", md5, played).then(function (result) {
    if (result && result.ok) applyPomodoroCommand(result.command);
  });
}

/* ---------- 提示音 ---------- */

function playPomodoroRing(after) {
  const ring = pomoRing();
  const info = pomo.plan && pomo.plan.ring;
  if (!ring || !info || !info.url) {
    if (after) after();
    return;
  }
  pomo.pendingAfterRing = after || null;
  pomo.ringPlaying = true;
  pomo.holdTrack = true;
  ring.src = info.url;
  ring.volume = 1;
  ring.currentTime = 0;
  ring.play().catch(function () {
    onPomodoroRingEnded();
  });
}

function onPomodoroRingEnded() {
  if (!pomo.ringPlaying) return;
  pomo.ringPlaying = false;
  pomo.holdTrack = false;
  const after = pomo.pendingAfterRing;
  pomo.pendingAfterRing = null;
  if (after) after();
}

/* ---------- 暂停与恢复 ---------- */

function togglePomodoroPause() {
  if (!pomo.active || pomo.prep || pomo.completed) return;
  if (pomo.paused) resumePomodoro();
  else pausePomodoro();
}

function pausePomodoro() {
  if (!pomo.running || pomo.paused) return;
  pomo.paused = true;
  pomo.remaining = Math.max(0, pomo.deadline - Date.now());
  reportPomodoroStats();
  fadeOutAndPause(pomoAudio());
  fadeOutAndPause(pomoAmbient());
  const video = pomoBackgroundVideo();
  if (video) video.pause();
  updatePomodoroPauseButton();
}

function resumePomodoro() {
  if (!pomo.running || !pomo.paused) return;
  pomo.paused = false;
  pomo.deadline = Date.now() + pomo.remaining;
  pomo.lastTick = Date.now();
  if (pomo.musicActive) playAndFade(pomoAudio(), pomo.musicVolume, 600);
  if (pomo.plan && pomo.plan.environment_enabled) {
    playAndFade(pomoAmbient(), pomo.environmentVolume, 600);
  }
  const video = pomoBackgroundVideo();
  if (video) video.play().catch(function () {});
  updatePomodoroPauseButton();
}

function updatePomodoroPauseButton() {
  const button = qs("#pomo-pause");
  if (!button) return;
  button.dataset.paused = pomo.paused ? "true" : "false";
  qs("#pomo-pause-label").textContent = T(
    pomo.paused ? "pomodoro.resume" : "pomodoro.pause"
  );
  const use = button.querySelector("use");
  if (use) use.setAttribute("href", pomo.paused ? "#i-play" : "#i-pause");
}

/* ---------- 背景与环境音 ---------- */

function renderPomodoroBackground(plan) {
  const host = qs("#pomo-bg");
  host.innerHTML = "";
  host.dataset.mode = plan.background_mode || "cover";
  if (!plan.background || !plan.background.url) {
    host.classList.add("is-empty");
    return;
  }
  host.classList.remove("is-empty");
  if (plan.background.kind === "video") {
    const video = document.createElement("video");
    video.className = "pomo-bg-media";
    video.src = plan.background.url;
    video.loop = true;
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    host.appendChild(video);
    video.play().catch(function () {});
  } else {
    const image = document.createElement("img");
    image.className = "pomo-bg-media";
    image.src = plan.background.url;
    image.alt = "";
    host.appendChild(image);
  }
}

function startPomodoroAmbient() {
  const ambient = pomoAmbient();
  const plan = pomo.plan;
  if (!ambient || !plan || !plan.environment_enabled || !plan.environment) return;
  ambient.src = plan.environment.url;
  ambient.loop = true;
  ambient.volume = 0;
  ambient.play().catch(function () {});
  fadeAudio(ambient, pomo.environmentVolume, 1200);
}

function applyPomodoroFont(font) {
  const stage = qs("#pomo-stage");
  stage.style.setProperty("--pomo-font", POMO_FONTS[font] || POMO_FONTS.system);
}

/* ---------- 音量 ---------- */

function syncPomodoroVolumes() {
  const music = Math.round(pomo.musicVolume * 100);
  const environment = Math.round(pomo.environmentVolume * 100);
  qs("#pomo-music-volume").value = String(music);
  qs("#pomo-music-volume-value").textContent = music + "%";
  qs("#pomo-environment-volume").value = String(environment);
  qs("#pomo-environment-volume-value").textContent = environment + "%";
  setFill(qs("#pomo-music-volume"), music / 100);
  setFill(qs("#pomo-environment-volume"), environment / 100);
}

function setPomodoroMusicVolume(value) {
  pomo.musicVolume = Math.min(1, Math.max(0, value));
  const music = pomoAudio();
  if (music && !pomo.ducking) music.volume = pomo.musicVolume;
  qs("#pomo-music-volume-value").textContent = Math.round(pomo.musicVolume * 100) + "%";
  setFill(qs("#pomo-music-volume"), pomo.musicVolume);
}

function setPomodoroEnvironmentVolume(value) {
  pomo.environmentVolume = Math.min(1, Math.max(0, value));
  const ambient = pomoAmbient();
  if (ambient) ambient.volume = pomo.environmentVolume;
  qs("#pomo-environment-volume-value").textContent =
    Math.round(pomo.environmentVolume * 100) + "%";
  setFill(qs("#pomo-environment-volume"), pomo.environmentVolume);
}

/* ---------- 全屏与面板 ---------- */

async function setPomodoroFullscreen(on) {
  const result = await call("set_fullscreen", !!on);
  if (result && result.ok) pomo.fullscreen = !!result.fullscreen;
  const button = qs("#pomo-fullscreen");
  if (button) {
    button.textContent = T(pomo.fullscreen ? "pomodoro.windowed" : "pomodoro.fullscreen");
  }
}

function togglePomodoroFullscreen() {
  setPomodoroFullscreen(!pomo.fullscreen);
}

function showPomodoroPanel() {
  window.clearTimeout(pomo.panelTimer);
  qs("#pomo-panel").classList.add("is-visible");
}

function scheduleHidePomodoroPanel() {
  window.clearTimeout(pomo.panelTimer);
  pomo.panelTimer = window.setTimeout(function () {
    qs("#pomo-panel").classList.remove("is-visible");
  }, 1500);
}

/* ---------- 结束 ---------- */

function finishPomodoro(completed) {
  if (!pomo.active) return;
  pomo.running = false;
  pomo.completed = true;
  pomo.ducking = false;
  pomo.holdTrack = false;
  reportPomodoroStats(completed);
  if (!completed) {
    stopAllPomodoroAudio();
    call("pomodoro_finish", pomo.uid).then(function (data) {
      setPomodoroFullscreen(false);
      leavePomodoroStage(data);
    });
    return;
  }

  // 完成页沿用休息时的音频策略：环境音继续，背景音乐按休息歌单来。
  // 提示音只在真的有音乐时压低，否则会把「淡出」的定时器一起取消掉。
  call("pomodoro_phase", pomo.phaseIndex + 1).then(function (result) {
    if (result && result.ok && result.play) {
      if (result.command) applyPomodoroCommand(result.command);
      else if (result.resume) playAndFade(pomoAudio(), pomo.musicVolume, 800);
      fadeAudio(pomoAudio(), pomo.musicVolume * 0.12, 400);
      playPomodoroRing(function () {
        fadeAudio(pomoAudio(), pomo.musicVolume, 1200);
      });
    } else {
      fadeOutAndPause(pomoAudio());
      playPomodoroRing(null);
    }
  });
  renderPomodoroDone();
  qs("#pomo-done").hidden = false;
}

function renderPomodoroDone() {
  const total = pomo.runFocus + pomo.runRest;
  qs("#pomo-done-stats").innerHTML =
    '<div class="pomo-done-row"><span>' + esc(T("pomodoro.stat.focus")) + "</span><b>" +
    esc(formatDuration(pomo.runFocus)) + "</b></div>" +
    '<div class="pomo-done-row"><span>' + esc(T("pomodoro.stat.rest")) + "</span><b>" +
    esc(formatDuration(pomo.runRest)) + "</b></div>" +
    '<div class="pomo-done-row"><span>' + esc(T("pomodoro.stat.total")) + "</span><b>" +
    esc(formatDuration(total)) + "</b></div>";
}

function reportPomodoroStats(completed) {
  if (!pomo.uid) return;
  const focus = Math.round(pomo.focusCarry);
  const rest = Math.round(pomo.restCarry);
  if (!focus && !rest && !completed) return;
  pomo.focusCarry -= focus;
  pomo.restCarry -= rest;
  pomo.lastReport = Date.now();
  call("pomodoro_report", pomo.uid, focus, rest, !!completed);
}

function requestExitPomodoro() {
  if (!pomo.active) return;
  qs("#pomo-confirm").hidden = false;
}

async function confirmExitPomodoro() {
  qs("#pomo-confirm").hidden = true;
  reportPomodoroStats(false);
  stopAllPomodoroAudio();
  const data = await call("pomodoro_finish", pomo.uid);
  await setPomodoroFullscreen(false);
  leavePomodoroStage(data);
}

async function closePomodoroDone() {
  stopAllPomodoroAudio();
  const data = await call("pomodoro_finish", pomo.uid);
  await setPomodoroFullscreen(false);
  leavePomodoroStage(data);
}

function leavePomodoroStage(data) {
  stopPomodoroTicker();
  stopAllPomodoroAudio();
  pomo.active = false;
  pomo.prep = false;
  pomo.running = false;
  pomo.paused = false;
  pomo.completed = false;
  pomo.plan = null;
  pomo.uid = null;
  pomo.pendingAfterRing = null;
  qs("#pomo-stage").hidden = true;
  qs("#pomo-done").hidden = true;
  qs("#pomo-confirm").hidden = true;
  document.body.classList.remove("pomo-mode");
  if (data) apply(data);
  else renderPomodoroView();
}

function stopAllPomodoroAudio() {
  [pomoAudio(), pomoAmbient(), pomoRing()].forEach(function (element) {
    if (!element) return;
    element.dataset.fadeToken = String((Number(element.dataset.fadeToken) || 0) + 1);
    element.pause();
    element.removeAttribute("src");
    element.load();
  });
  const video = pomoBackgroundVideo();
  if (video) video.pause();
}

/* ---------- 淡入淡出 ---------- */

function fadeAudio(element, target, ms) {
  if (!element) return;
  const token = String((Number(element.dataset.fadeToken) || 0) + 1);
  element.dataset.fadeToken = token;
  const start = element.volume;
  const started = performance.now();
  function step(now) {
    if (element.dataset.fadeToken !== token) return;
    const ratio = Math.min(1, (now - started) / Math.max(1, ms));
    element.volume = Math.min(1, Math.max(0, start + (target - start) * ratio));
    if (ratio < 1) window.requestAnimationFrame(step);
  }
  window.requestAnimationFrame(step);
}

function fadeOutAndPause(element, ms) {
  if (!element) return;
  fadeAudio(element, 0, ms || 400);
  const token = element.dataset.fadeToken;
  window.setTimeout(function () {
    if (element.dataset.fadeToken !== token) return;
    element.pause();
  }, (ms || 400) + 40);
}

function playAndFade(element, target, ms) {
  if (!element) return;
  if (!element.getAttribute("src")) return;
  element.play().catch(function () {});
  fadeAudio(element, target, ms || 600);
}

/* ---------- 事件 ---------- */

function bindPomodoroStageEvents() {
  qs("#pomo-prep-skip").addEventListener("click", beginFormalPomodoro);
  qs("#pomo-pause").addEventListener("click", togglePomodoroPause);
  qs("#pomo-fullscreen").addEventListener("click", togglePomodoroFullscreen);
  qs("#pomo-exit").addEventListener("click", requestExitPomodoro);
  qs("#pomo-exit-cancel").addEventListener("click", function () {
    qs("#pomo-confirm").hidden = true;
  });
  qs("#pomo-exit-confirm").addEventListener("click", confirmExitPomodoro);
  qs("#pomo-done-close").addEventListener("click", closePomodoroDone);

  qs("#pomo-hotzone").addEventListener("mouseenter", showPomodoroPanel);
  qs("#pomo-panel").addEventListener("mouseenter", showPomodoroPanel);
  qs("#pomo-hotzone").addEventListener("mouseleave", scheduleHidePomodoroPanel);
  qs("#pomo-panel").addEventListener("mouseleave", scheduleHidePomodoroPanel);

  const musicVolume = qs("#pomo-music-volume");
  musicVolume.addEventListener("input", function () {
    setPomodoroMusicVolume(Number(musicVolume.value) / 100);
  });
  musicVolume.addEventListener("change", function () {
    call("pomodoro_set_volumes", pomo.musicVolume, pomo.environmentVolume);
  });
  const environmentVolume = qs("#pomo-environment-volume");
  environmentVolume.addEventListener("input", function () {
    setPomodoroEnvironmentVolume(Number(environmentVolume.value) / 100);
  });
  environmentVolume.addEventListener("change", function () {
    call("pomodoro_set_volumes", pomo.musicVolume, pomo.environmentVolume);
  });

  qs("#pomo-ring").addEventListener("ended", onPomodoroRingEnded);
  qs("#pomo-audio").addEventListener("ended", pomodoroMusicEnded);
  qs("#pomo-audio").addEventListener("error", function () {
    if (qs("#pomo-audio").getAttribute("src")) reportPomodoroAudioFailed("media");
  });
  qs("#pomo-audio").addEventListener("play", function () {
    call("pomodoro_music_playing", true);
  });
  qs("#pomo-audio").addEventListener("pause", function () {
    call("pomodoro_music_playing", false);
  });

  window.addEventListener("pagehide", function () {
    if (pomo.active) reportPomodoroStats(false);
  });
}
