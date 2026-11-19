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
  startedAt: 0,
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
  leaving: false,
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

function pomoRing() {
  return qs("#pomo-ring");
}

/* 环境音：两个 <audio> 交替接力。
   <audio loop> 在接缝处会空一拍（MP3 的编码器延迟 + 元素重新起播），对雨声这种
   连续底噪特别明显。这里提前一个淡化时长把备用元素从 0 播起来，两边交叉淡化，
   听感上就没有断点了。 */
const AMBIENT_FADE_MS = 320;

const ambient = {
  a: null,
  b: null,
  active: null,
  timer: null,
  volume: 0.35,
  playing: false,
  url: "",
};

function ambientElements() {
  if (!ambient.a) {
    ambient.a = qs("#pomo-ambient");
    ambient.b = qs("#pomo-ambient-b");
  }
  return [ambient.a, ambient.b];
}

function ambientStart(url, volume) {
  const pair = ambientElements();
  ambientStop();
  ambient.volume = volume;
  ambient.url = url;
  if (!pair[0] || !pair[1] || !url) return;
  pair.forEach(function (element) {
    element.src = url;
    element.loop = false; // 循环由这里接管
    element.volume = 0;
  });
  pair[0].currentTime = 0;
  ambient.active = pair[0];
  ambient.playing = true;
  pair[0].play().catch(function () {});
  fadeAudio(pair[0], volume, 1200);
  ambient.timer = window.setInterval(ambientWatch, 80);
}

function ambientWatch() {
  const element = ambient.active;
  if (!ambient.playing || !element) return;
  const duration = element.duration;
  if (!duration || !isFinite(duration)) return;
  const fade = Math.min(AMBIENT_FADE_MS / 1000, duration / 3);
  if (duration - element.currentTime > fade + 0.08) return;
  ambientHandoff(fade);
}

function ambientHandoff(fade) {
  const pair = ambientElements();
  const current = ambient.active;
  const next = current === pair[0] ? pair[1] : pair[0];
  if (!next) return;
  ambient.active = next;
  next.currentTime = 0;
  next.volume = 0;
  next.play().catch(function () {});
  fadeAudio(next, ambient.volume, fade * 1000);
  fadeAudio(current, 0, fade * 1000);
  window.setTimeout(function () {
    if (ambient.active === current) return;
    current.dataset.fadeToken = String((Number(current.dataset.fadeToken) || 0) + 1);
    current.pause();
    current.currentTime = 0;
  }, fade * 1000 + 80);
}

function ambientPause() {
  ambient.playing = false;
  ambientElements().forEach(function (element) {
    if (element) fadeOutAndPause(element);
  });
}

function ambientResume() {
  const element = ambient.active;
  if (!element || !ambient.url) return;
  ambient.playing = true;
  playAndFade(element, ambient.volume, 600);
}

function ambientSetVolume(value) {
  ambient.volume = value;
  if (ambient.active) ambient.active.volume = value;
}

function ambientStop() {
  window.clearInterval(ambient.timer);
  ambient.timer = null;
  ambient.playing = false;
  ambient.active = null;
  ambient.url = "";
  ambientElements().forEach(function (element) {
    if (!element) return;
    element.dataset.fadeToken = String((Number(element.dataset.fadeToken) || 0) + 1);
    element.pause();
    element.removeAttribute("src");
    element.load();
    element.volume = 0;
  });
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
  pomo.startedAt = 0;
  pomo.prepDeadline = Date.now() + Math.max(0, Number(plan.prep_seconds) || 0) * 1000;

  audio.pause();
  call("set_playing", false);
  openPomodoroStage();
  startPomodoroTicker();
  renderPomodoros();
  // 预备时长为 0 就是跳过：直接进第一段，不闪一下预备页。
  if (pomo.prepDeadline <= Date.now()) beginFormalPomodoro();
}

function openPomodoroStage() {
  const stage = qs("#pomo-stage");
  pomo.leaving = false;
  stage.classList.remove("is-leaving");
  stage.hidden = false;
  document.body.classList.add("pomo-mode");
  qs("#pomo-done").hidden = true;
  qs("#pomo-done").classList.remove("is-closing");
  qs("#pomo-confirm").hidden = true;
  qs("#pomo-confirm").classList.remove("is-closing");
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
    String(Number(pomo.plan.hud_scale) || 1)
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

  const duckMs = pomoDuckMs();
  if (pomo.plan && pomo.plan.ring && duckMs > 0 && remaining <= duckMs && !pomo.ducking) {
    pomo.ducking = true;
    pomo.holdTrack = true;
  }
  if (pomo.ducking) updateDuckVolume(remaining, duckMs);

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
  pomo.startedAt = Math.floor(Date.now() / 1000);
  pomo.deadline = Date.now() + pomo.plan.segments[0] * 60000;
  pomo.lastTick = Date.now();
  pomo.lastReport = Date.now();
  updatePomodoroHud(pomo.deadline - Date.now());
  playPomodoroRing(function () {
    applyPomodoroPhaseMusic(true);
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
    applyPomodoroPhaseMusic(true);
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

/* 提示音期间音乐压低到多少、压多久、响完用多久回来：都是全局偏好。 */
function pomoDuckMs() {
  const value = Number(pomo.plan && pomo.plan.duck_ms);
  return isFinite(value) ? Math.max(0, value) : 10000;
}

function pomoDuckRatio() {
  const value = Number(pomo.plan && pomo.plan.duck_ratio);
  return isFinite(value) ? Math.min(1, Math.max(0, value)) : 0.12;
}

function pomoFadeInMs() {
  const value = Number(pomo.plan && pomo.plan.fade_in_ms);
  return isFinite(value) ? Math.max(0, value) : 2000;
}

function updateDuckVolume(remaining, duckMs) {
  const music = pomoAudio();
  if (!music || music.paused) return;
  const duck = pomoDuckRatio();
  const ratio = Math.min(1, Math.max(0, remaining / Math.max(1, duckMs)));
  music.dataset.fadeToken = String((Number(music.dataset.fadeToken) || 0) + 1);
  music.volume = Math.min(1, Math.max(0, pomo.musicVolume * (duck + (1 - duck) * ratio)));
}

/* ---------- 阶段音乐 ---------- */

async function applyPomodoroPhaseMusic(afterRing) {
  if (!pomo.active) return;
  const result = await call("pomodoro_phase", pomo.phaseIndex);
  if (!result || !result.ok) return;
  const fade = afterRing ? pomoFadeInMs() : 800;
  pomo.musicActive = !!result.play;
  if (!result.play) {
    fadeOutAndPause(pomoAudio());
    return;
  }
  if (result.resume) {
    playAndFade(pomoAudio(), pomo.musicVolume, fade);
    return;
  }
  if (result.command) applyPomodoroCommand(result.command, fade);
}

function applyPomodoroCommand(command, fadeMs) {
  const music = pomoAudio();
  const fade = fadeMs === undefined ? 800 : fadeMs;
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
  fadeAudio(music, pomo.musicVolume, fade);
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
  ambientPause();
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
  if (pomo.plan && pomo.plan.environment) ambientResume();
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
  const plan = pomo.plan;
  if (!plan || !plan.environment || !plan.environment.url) return;
  ambientStart(plan.environment.url, pomo.environmentVolume);
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
  ambientSetVolume(pomo.environmentVolume);
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
  if (completed) recordPomodoroSession();
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
      // 渐弱时长为 0 表示「提示音期间不压低音乐」，完成页也一样。
      const duck = pomoDuckMs() > 0 ? pomoDuckRatio() : 1;
      fadeAudio(pomoAudio(), pomo.musicVolume * duck, 400);
      playPomodoroRing(function () {
        fadeAudio(pomoAudio(), pomo.musicVolume, pomoFadeInMs());
      });
    } else {
      fadeOutAndPause(pomoAudio());
      playPomodoroRing(null);
    }
  });
  renderPomodoroDone();
  showPomodoroLayer("#pomo-done");
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

/* 完整走完一轮才记一条播放记录；中途退出不记。 */
function recordPomodoroSession() {
  if (!pomo.uid || !pomo.startedAt) return;
  call(
    "pomodoro_record_session",
    pomo.uid,
    pomo.startedAt,
    Math.round(pomo.runFocus),
    Math.round(pomo.runRest)
  );
}

function showPomodoroLayer(selector) {
  const node = qs(selector);
  if (!node) return;
  node.classList.remove("is-closing");
  node.hidden = false;
}

function hidePomodoroLayer(selector, done) {
  const node = qs(selector);
  if (!node || node.hidden) {
    if (done) done();
    return;
  }
  node.classList.add("is-closing");
  window.setTimeout(function () {
    node.hidden = true;
    node.classList.remove("is-closing");
    if (done) done();
  }, 170);
}

function requestExitPomodoro() {
  if (!pomo.active) return;
  showPomodoroLayer("#pomo-confirm");
}

async function confirmExitPomodoro() {
  hidePomodoroLayer("#pomo-confirm");
  reportPomodoroStats(false);
  stopAllPomodoroAudio();
  const data = await call("pomodoro_finish", pomo.uid);
  await setPomodoroFullscreen(false);
  leavePomodoroStage(data);
}

async function closePomodoroDone() {
  hidePomodoroLayer("#pomo-done");
  stopAllPomodoroAudio();
  const data = await call("pomodoro_finish", pomo.uid);
  await setPomodoroFullscreen(false);
  leavePomodoroStage(data);
}

function leavePomodoroStage(data) {
  if (pomo.leaving) return; // 连点两下「退出」不该收两次尾
  pomo.leaving = true;
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
  // 淡出期间计时层还盖在窗口上，露出的是底下的播放器：等它透明了再真正收起，
  // 否则会先闪一下主界面再被盖住。
  const stage = qs("#pomo-stage");
  stage.classList.add("is-leaving");
  window.setTimeout(function () {
    stage.hidden = true;
    stage.classList.remove("is-leaving");
    qs("#pomo-done").hidden = true;
    qs("#pomo-confirm").hidden = true;
    document.body.classList.remove("pomo-mode");
    if (data) apply(data);
    else renderPomodoroView();
  }, 220);
}

function stopAllPomodoroAudio() {
  ambientStop();
  [pomoAudio(), pomoRing()].forEach(function (element) {
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
    hidePomodoroLayer("#pomo-confirm");
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
