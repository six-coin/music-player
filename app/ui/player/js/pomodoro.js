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
  advancing: false,
  exiting: false,
  closePending: false,
  confirmClosing: false,
  idleTimer: null,
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
  // 两个元素放的是同一段底噪的不同位置，互不相关：等功率交叉才不掉音量。
  fadeAudio(next, ambient.volume, fade * 1000, true);
  fadeAudio(current, 0, fade * 1000, true);
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
  pomo.advancing = false;
  pomo.exiting = false;
  pomo.closePending = false;
  pomo.confirmClosing = false;
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
  qs("#pomo-more").hidden = true;
  qs("#pomo-more").classList.remove("is-closing");
  qs("#pomo-prep").hidden = false;
  qs(".pomo-hud").hidden = true;
  qs("#pomo-panel").classList.remove("is-visible");
  qs("#pomo-panel-title").textContent = pomo.plan.name || "";
  qs("#pomo-more-open").hidden = true; // 预备阶段没有「本段」可调
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
  pomoWake();
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
  // 换段要等一次结算回来：这段时间不再往上一段累加，免得算到下一段头上。
  if (!pomo.running || pomo.paused || pomo.advancing) {
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
  qs("#pomo-more-open").hidden = false;
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

/* 换段：先让 Python 结算这一段的最后一首，再推进段位。
   不是这张歌单的最后一段时一首都不记，下一段接着放它；是最后一段就按阈值算一遍。
   结算要走一个来回，这里挡住重入——计时器每 250ms 还会再叫一次。 */
async function advancePomodoroPhase() {
  if (pomo.advancing) return;
  pomo.advancing = true;
  try {
    reportPomodoroStats();
    await call("pomodoro_leave_phase", pomodoroPlaybackPosition(), false);
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
  } finally {
    pomo.advancing = false;
  }
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
  // 段数按「专注段」算：25/5/25/5/25/5/25 是 4 段，最后一个休息也算走完第 4 段。
  const focusCount = Math.max(1, Math.ceil(segments.length / 2));
  const count =
    pomo.phase === "focus"
      ? T("pomodoro.segment_focus", {
          index: Math.floor(pomo.phaseIndex / 2) + 1,
          total: focusCount,
        })
      : T("pomodoro.segment_rest", {
          done: Math.floor((pomo.phaseIndex + 1) / 2),
          total: focusCount,
        });
  qs("#pomo-panel-phase").textContent =
    T("pomodoro.phase." + pomo.phase) + " · " + count;
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

/* 刚离开的那一段停在哪：切回同一个时段时后端按它接着放。
   ``played_ms`` 是这一首到此刻已经放了多少——换段接着放时计时器从这里走，
   不重新数；没有音乐在放的段（休息不选歌单）没有可报的位置。 */
function pomodoroPlaybackPosition() {
  const music = pomoAudio();
  if (!pomo.musicActive || !pomo.trackMd5 || !music || !music.getAttribute("src")) return null;
  const position = Number(music.currentTime);
  return {
    md5: pomo.trackMd5,
    position_ms: Math.round((Number.isFinite(position) ? position : 0) * 1000),
    played_ms: Math.round(pomo.playedMs),
  };
}

function applyPhaseResult(result, fade) {
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

/* 进入当前段：放不放、放哪张歌单由 Python 决定。
   「刚离开那一段停在哪儿」已经由 advancePomodoroPhase 里的 pomodoro_leave_phase
   报过了，这里不用再报一次——再报一次会把刚结算掉的续播点又写回去。 */
async function applyPomodoroPhaseMusic(afterRing) {
  if (!pomo.active) return;
  const result = await call("pomodoro_phase", pomo.phaseIndex);
  if (!result || !result.ok) return;
  applyPhaseResult(result, afterRing ? pomoFadeInMs() : 800);
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
  // 接着放上一段没放完的那首时，计时器从已经放过的时长继续。
  pomo.playedMs = Math.max(0, Number(command.played_ms) || 0);
  pomo.lastAudioTick = performance.now();
  pomo.pendingAutoplay = !!command.autoplay;
  // 切回某个时段时后端会给回上次的播放位置：等元数据到了再跳，太早设会被丢掉。
  const position = Number(command.position_ms) || 0;
  if (position > 0) {
    const seek = function () {
      if (music.getAttribute("src") !== command.url) return;
      const duration = Number(music.duration);
      const limit =
        Number.isFinite(duration) && duration > 0
          ? Math.max(0, duration - 0.3)
          : position / 1000;
      music.currentTime = Math.min(position / 1000, limit);
    };
    if (music.readyState >= 1) seek();
    else music.addEventListener("loadedmetadata", seek, { once: true });
  }
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

/* ---------- 本次番茄钟设置 ---------- */

/* 面板上的「更多」：热切换两个时段的歌单与顺序，也能直接跳过本段。 */
function pomodoroMoreRow(label, control) {
  // 不能用 <label>：它会把点击转发给菜单里的第一个 <button>，菜单刚开就被关掉。
  return '<div class="pomo-more-row"><span>' + esc(label) + "</span>" + control + "</div>";
}

function pomodoroMoreMarkup() {
  const plan = pomo.plan || {};
  const orders = pomodoroOptions().orders || [];
  const block = function (phase, title, config) {
    return (
      '<div class="pomo-more-group"><h3>' + esc(title) + "</h3>" +
      pomodoroMoreRow(
        T("pomodoro.item.playlist"),
        pomoSelect(
          'data-more-phase="' + phase + '" data-more-field="playlist"',
          pomoPlaylistOptions(),
          config.playlist || ""
        )
      ) +
      pomodoroMoreRow(
        T("pomodoro.item.order"),
        pomoSelect(
          'data-more-phase="' + phase + '" data-more-field="order"',
          pomoValueOptions("pomodoro.order", orders),
          config.order || "shuffle"
        )
      ) +
      "</div>"
    );
  };
  return (
    block("focus", T("pomodoro.phase.focus"), plan.focus || {}) +
    block("rest", T("pomodoro.phase.rest"), plan.rest || {})
  );
}

function openPomodoroMore() {
  if (!pomo.active || pomo.completed || pomo.prep) return;
  qs("#pomo-more-body").innerHTML = pomodoroMoreMarkup();
  showPomodoroLayer("#pomo-more");
}

function closePomodoroMore() {
  hidePomodoroLayer("#pomo-more");
}

function moreSelectValue(phase, field) {
  const node = qs('[data-more-phase="' + phase + '"][data-more-field="' + field + '"]');
  return node ? node.dataset.value : "";
}

function morePhasePayload(phase) {
  return {
    playlist: moreSelectValue(phase, "playlist"),
    order: moreSelectValue(phase, "order") || "shuffle",
  };
}

async function applyPomodoroMore() {
  const focus = morePhasePayload("focus");
  const rest = morePhasePayload("rest");
  hidePomodoroLayer("#pomo-more");
  const result = await call(
    "pomodoro_set_phases",
    focus,
    rest,
    pomodoroPlaybackPosition()
  );
  if (!result || !result.ok) return;
  if (pomo.plan) {
    pomo.plan.focus = focus;
    pomo.plan.rest = rest;
  }
  applyPhaseResult(result, 600);
}

/* 跳过本段：和倒计时走完一样推进，已计的时间照常上报。 */
function skipPomodoroPhase() {
  if (!pomo.active || pomo.completed || pomo.prep) return;
  hidePomodoroLayer("#pomo-more");
  if (pomo.paused) resumePomodoro();
  advancePomodoroPhase();
}

/* ---------- 鼠标闲置 ---------- */

/* 计时的时候鼠标一直停在画面中间很碍眼：5 秒不动就把指针藏起来，
   一动立刻回来。确认框和完成页要点击，露着光标更稳妥。 */
const POMO_IDLE_MS = 5000;

function pomoWake() {
  const stage = qs("#pomo-stage");
  if (stage) stage.classList.remove("is-idle");
  window.clearTimeout(pomo.idleTimer);
  pomo.idleTimer = null;
  if (!pomo.active) return;
  pomo.idleTimer = window.setTimeout(function () {
    pomo.idleTimer = null;
    if (!pomo.active) return;
    const node = qs("#pomo-stage");
    const confirm = qs("#pomo-confirm");
    const done = qs("#pomo-done");
    const more = qs("#pomo-more");
    if (!node || node.hidden) return;
    if ((confirm && !confirm.hidden) || (done && !done.hidden) || (more && !more.hidden)) return;
    node.classList.add("is-idle");
    qs("#pomo-panel").classList.remove("is-visible");
  }, POMO_IDLE_MS);
}

function pomoStopIdle() {
  window.clearTimeout(pomo.idleTimer);
  pomo.idleTimer = null;
  const stage = qs("#pomo-stage");
  if (stage) stage.classList.remove("is-idle");
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
    call(
      "pomodoro_finish",
      pomo.uid,
      pomo.startedAt,
      Math.round(pomo.runFocus),
      Math.round(pomo.runRest)
    ).then(function (data) {
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
  qs("#pomo-more-open").hidden = true;
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
  window.clearTimeout(node.hideTimer);
  node.classList.remove("is-closing");
  node.hidden = false;
}

/* 收起带淡出：同一个层连收两次只算一次，后一次把前一次的定时器顶掉。 */
function hidePomodoroLayer(selector, done) {
  const node = qs(selector);
  if (!node || node.hidden) {
    if (done) done();
    return;
  }
  node.classList.add("is-closing");
  window.clearTimeout(node.hideTimer);
  node.hideTimer = window.setTimeout(function () {
    node.hidden = true;
    node.classList.remove("is-closing");
    if (done) done();
  }, 170);
}

/* 这一层开着吗：正在淡出的不算，免得连按两下同一件事做两次。 */
function pomoLayerOpen(selector) {
  const node = qs(selector);
  return !!node && !node.hidden && !node.classList.contains("is-closing");
}

/* 确认框有两种来由：面板上的「退出」和窗口的 X / Alt+F4。文案分开，
   后者要说明「关窗会结束这一轮」。两种来由之间切换时先收掉旧的、再放新的：
   原地换字看起来就是「没动画直接跳过去」。 */
function setPomodoroConfirmCopy(closing) {
  qs("#pomo-confirm-title").textContent = T(
    closing ? "pomodoro.close_title" : "pomodoro.exit_title"
  );
  qs("#pomo-confirm-body").textContent = T(
    closing ? "pomodoro.close_body" : "pomodoro.exit_body"
  );
  qs("#pomo-exit-confirm").textContent = T(
    closing ? "pomodoro.close_confirm" : "pomodoro.exit_confirm"
  );
}

function showPomodoroConfirm(closing) {
  const node = qs("#pomo-confirm");
  if (!node) return;
  if (pomoLayerOpen("#pomo-confirm") && pomo.confirmClosing === closing) return; // 同一份文案，不重播
  pomo.confirmClosing = closing;
  const open = function () {
    setPomodoroConfirmCopy(closing);
    showPomodoroLayer("#pomo-confirm");
  };
  if (node.hidden) {
    open();
    return;
  }
  hidePomodoroLayer("#pomo-confirm", open);
}

function cancelPomodoroConfirm() {
  pomo.closePending = false;
  hidePomodoroLayer("#pomo-confirm");
  pomoWake();
}

function requestExitPomodoro() {
  if (!pomo.active) return;
  showPomodoroConfirm(false);
}

/* 窗口的 X / Alt+F4 被 Python 拦下后会调这里；返回 true 表示页面接管了提示。 */
window.pomoAskClose = function () {
  if (!pomo.active || pomo.exiting) return false; // 已经在退出了，别再弹一个
  if (pomo.closePending) return true; // 已经在问关窗了，别把动画重播一遍
  pomo.closePending = true;
  showPomodoroConfirm(true);
  pomoWake();
  return true;
};

async function confirmExitPomodoro() {
  if (pomo.exiting) return; // 键盘与按钮可能同时来一下
  pomo.exiting = true;
  const closing = pomo.closePending;
  pomo.closePending = false;
  hidePomodoroLayer("#pomo-confirm");
  reportPomodoroStats(false);
  // 整轮到此为止：这一段的最后一首不会再有人接着放，按「最后一段」结算。
  await call("pomodoro_leave_phase", pomodoroPlaybackPosition(), true);
  stopAllPomodoroAudio();
  const data = await call(
    "pomodoro_finish",
    pomo.uid,
    pomo.startedAt,
    Math.round(pomo.runFocus),
    Math.round(pomo.runRest)
  );
  await setPomodoroFullscreen(false);
  if (closing) {
    // 用户本来就是想关窗：退出番茄钟之后把窗口也关掉。
    call("force_close");
    return;
  }
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
  pomoStopIdle();
  pomo.closePending = false;
  pomo.confirmClosing = false;
  pomo.advancing = false;
  pomo.exiting = false;
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
    qs("#pomo-more").hidden = true;
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

function fadeAudio(element, target, ms, equalPower) {
  if (!element) return;
  const token = String((Number(element.dataset.fadeToken) || 0) + 1);
  element.dataset.fadeToken = token;
  const start = element.volume;
  const started = performance.now();
  function step(now) {
    if (element.dataset.fadeToken !== token) return;
    const ratio = Math.min(1, (now - started) / Math.max(1, ms));
    // 等功率曲线：淡入用 sin、淡出用 cos，两段不相干的底噪叠在一起时
    // 功率不变，接缝处不会掉 3 dB。普通淡入淡出仍用线性。
    const curve = equalPower
      ? target >= start
        ? Math.sin((ratio * Math.PI) / 2)
        : 1 - Math.cos((ratio * Math.PI) / 2)
      : ratio;
    element.volume = Math.min(1, Math.max(0, start + (target - start) * curve));
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

/* 三个提示框共用一套键盘约定：Esc 取消 / 继续计时，Enter 完成 / 退出。
   确认框盖在「更多」上面，所以先认它。下拉框开着时 Esc 先收菜单、Enter 自己
   开关菜单；菜单收着时 Esc 仍然算取消。焦点落在弹窗里的按钮上时 Enter 交给
   那个按钮，别抢它的默认动作。 */
function pomoDialogKeydown(event) {
  if (!pomo.active || pomo.leaving) return false;
  if (event.ctrlKey || event.altKey || event.metaKey) return false;
  const target = event.target;
  if (!target || !target.closest) return false;
  const select = target.closest(".pomo-select");
  if (select && (event.key !== "Escape" || select.classList.contains("open"))) return false;
  const confirmOpen = pomoLayerOpen("#pomo-confirm");
  const moreOpen = pomoLayerOpen("#pomo-more");
  if (event.key === "Escape") {
    if (confirmOpen) {
      cancelPomodoroConfirm();
      return true;
    }
    if (moreOpen) {
      closePomodoroMore();
      return true;
    }
    return false;
  }
  if (event.key === "Enter") {
    if (confirmOpen) {
      if (target.closest("#pomo-confirm button")) return false;
      confirmExitPomodoro();
      return true;
    }
    if (moreOpen) {
      if (target.closest("#pomo-more button")) return false;
      applyPomodoroMore();
      return true;
    }
  }
  return false;
}

function bindPomodoroStageEvents() {
  qs("#pomo-prep-skip").addEventListener("click", beginFormalPomodoro);
  qs("#pomo-pause").addEventListener("click", togglePomodoroPause);
  qs("#pomo-fullscreen").addEventListener("click", togglePomodoroFullscreen);
  qs("#pomo-exit").addEventListener("click", requestExitPomodoro);
  qs("#pomo-exit-cancel").addEventListener("click", cancelPomodoroConfirm);
  qs("#pomo-exit-confirm").addEventListener("click", confirmExitPomodoro);
  qs("#pomo-done-close").addEventListener("click", closePomodoroDone);
  qs("#pomo-more-open").addEventListener("click", openPomodoroMore);
  qs("#pomo-more-cancel").addEventListener("click", closePomodoroMore);
  qs("#pomo-more-done").addEventListener("click", applyPomodoroMore);
  qs("#pomo-more-skip").addEventListener("click", skipPomodoroPhase);

  bindWheelVolume(qs("#pomo-music-volume"));
  bindWheelVolume(qs("#pomo-environment-volume"));

  // 提示框的 Esc / Enter：先于全局快捷键注册，拦下来就不再往下走。
  document.addEventListener("keydown", function (event) {
    if (pomoDialogKeydown(event)) event.preventDefault();
  });

  // 闲置隐藏光标：动一下就回来。
  ["pointermove", "pointerdown", "wheel", "keydown"].forEach(function (name) {
    window.addEventListener(
      name,
      function () {
        if (pomo.active) pomoWake();
      },
      { passive: true }
    );
  });

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
