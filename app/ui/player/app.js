/* 播放器的前端。没有框架、没有构建步骤：拉一次文案与快照，整体重绘。
   播哪首由 Python 决定（快照里的 command），怎么播由这里执行。 */

const state = {
  data: null,
  strings: {},
  commandSeq: 0,
  noticeSeq: 0,
  playedMs: 0,
  lastTick: 0,
  ticks: 0,
  draggingSeek: false,
  autoplay: false,
  pendingSeek: null,
  failedFor: null,
  startTimer: null,
  noticeTimer: null,
  pickerOpen: false,
  pickerItems: [],
  pickerIndex: 0,
  pickerTimer: null,
  systemWatch: false,
};

const audio = document.getElementById("audio");

/* ---------- 基础 ---------- */

function qs(selector, root) {
  return (root || document).querySelector(selector);
}

function qsa(selector, root) {
  return Array.prototype.slice.call((root || document).querySelectorAll(selector));
}

function esc(text) {
  return String(text === undefined || text === null ? "" : text).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

function bridge() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

async function call(method) {
  const api = bridge();
  if (!api) return null;
  const args = Array.prototype.slice.call(arguments, 1);
  try {
    return await api[method].apply(api, args);
  } catch (error) {
    console.error(method, error);
    return null;
  }
}

/* ---------- 文案 ---------- */

function T(key, values) {
  const template = state.strings[key];
  if (template === undefined) return key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, function (match, name) {
    return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
  });
}

async function loadStrings() {
  const table = await call("get_strings");
  state.strings = table || {};
}

function applyStrings() {
  qsa("[data-i18n]").forEach(function (node) {
    node.textContent = T(node.dataset.i18n);
  });
  qsa("[data-i18n-placeholder]").forEach(function (node) {
    node.setAttribute("placeholder", T(node.dataset.i18nPlaceholder));
  });
  qsa("[data-i18n-title]").forEach(function (node) {
    node.setAttribute("title", T(node.dataset.i18nTitle));
  });
}

/* ---------- 格式化 ---------- */

function pad(value) {
  return value < 10 ? "0" + value : String(value);
}

function formatDuration(ms) {
  const total = Math.max(0, Math.round((ms || 0) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours > 0 ? hours + ":" + pad(minutes) + ":" + pad(seconds) : minutes + ":" + pad(seconds);
}

/* ---------- 主题 ---------- */

function applyTheme(theme) {
  if (!theme) return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem("theme", theme);
  } catch (error) {
    /* 写不了就只影响下次首帧，忽略 */
  }
}

function watchSystemTheme() {
  if (state.systemWatch || !window.matchMedia) return;
  state.systemWatch = true;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = function (event) {
    if (state.data && state.data.theme_source === "system") {
      applyTheme(event.matches ? "dark" : "light");
    }
  };
  if (media.addEventListener) media.addEventListener("change", handler);
}

/* ---------- 快照 ---------- */

function apply(data) {
  if (!data || !data.ok) return;
  state.data = data;
  applyTheme(data.theme);
  if (data.theme_source === "system") watchSystemTheme();

  qs("#app").classList.toggle("no-queue", !data.queue.visible);
  renderPlaylists();
  renderTrack();
  renderTransport();
  renderQueue();
  renderEmpty();
  renderVolume();
  renderNotice();
  if (data.command) runCommand(data.command);
}

function renderPlaylists() {
  const list = qs("#playlists");
  const top = list.scrollTop;
  list.innerHTML = state.data.playlists
    .map(function (playlist) {
      return (
        '<button type="button" role="listitem" class="playlist-item' +
        (playlist.active ? " is-active" : "") +
        '" data-uid="' +
        esc(playlist.uid) +
        '">' +
        '<span class="name">' +
        esc(playlist.title) +
        "</span>" +
        '<span class="count">' +
        playlist.count +
        "</span></button>"
      );
    })
    .join("");
  list.scrollTop = top;
}

function renderTrack() {
  const data = state.data;
  const track = data.track;
  qs("#track-title").textContent = track ? track.title : "";
  qs("#track-authors").textContent = track
    ? track.authors || T("player.unknown_author")
    : "";
  qs("#pick-loop").hidden = !track || data.mode !== "repeat_one";
  qs("#play").disabled = !track;
}

function renderTransport() {
  const data = state.data;
  qs("#prev").disabled = !data.transport.can_prev;
  qs("#next").disabled = !data.transport.can_next;

  qsa(".mode-btn").forEach(function (button) {
    const active = button.dataset.mode === data.mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.setAttribute("title", T("player.mode." + button.dataset.mode));
  });

  qs("#mode-label").textContent = T("player.mode_label", {
    mode: T("player.mode." + data.mode),
  });

  const key = data.queue.visible ? "player.action.queue_hide" : "player.action.queue_show";
  ["#queue-toggle", "#queue-collapse"].forEach(function (selector) {
    const button = qs(selector);
    button.setAttribute("title", T(key));
    button.setAttribute("aria-label", T(key));
    button.setAttribute("aria-expanded", data.queue.visible ? "true" : "false");
  });
}

function renderQueue() {
  const data = state.data;
  const list = qs("#queue-list");
  const more = qs("#queue-more");
  const top = list.scrollTop;

  if (data.queue.pinned) {
    list.innerHTML =
      '<div class="queue-pinned">' +
      esc(T("player.queue.pinned", { title: data.queue.pinned })) +
      "</div>";
    more.hidden = true;
    list.scrollTop = 0;
    return;
  }

  if (!data.queue.items.length) {
    list.innerHTML = '<div class="queue-empty">' + esc(T("player.queue.empty")) + "</div>";
  } else {
    list.innerHTML = data.queue.items
      .map(function (item, index) {
        const current = data.mode === "repeat_one" && item.md5 === data.queue.current_md5;
        return (
          '<button type="button" class="queue-item' +
          (item.missing ? " is-missing" : "") +
          (current ? " is-current" : "") +
          '" data-md5="' +
          esc(item.md5) +
          '" title="' +
          esc(item.title) +
          '">' +
          '<span class="idx">' +
          (index + 1) +
          "</span>" +
          '<span class="name">' +
          esc(item.title) +
          "</span>" +
          (item.missing ? '<span class="tag">' + esc(T("player.missing")) + "</span>" : "") +
          "</button>"
        );
      })
      .join("");
  }

  more.hidden = !data.queue.more;
  more.textContent = data.queue.more ? T("player.queue.more", { count: data.queue.more }) : "";
  list.scrollTop = top;
}

function renderEmpty() {
  const empty = state.data.empty;
  const box = qs("#empty");
  const playing = qs("#playing");
  if (!empty) {
    box.hidden = true;
    playing.hidden = false;
    return;
  }
  box.hidden = false;
  playing.hidden = true;
  qs("#empty-title").textContent = T("player.empty." + empty + ".title");
  qs("#empty-body").textContent = T("player.empty." + empty + ".body");
  qs("#empty-action").hidden = empty === "no_selection";
}

function renderVolume() {
  const volume = Math.round((state.data.volume || 0) * 100);
  const slider = qs("#volume");
  slider.value = String(volume);
  setFill(slider, volume / 100);
  qs("#volume-value").textContent = volume + "%";
  audio.volume = Math.min(1, Math.max(0, volume / 100));
}

function renderNotice() {
  const notice = state.data.notice;
  if (!notice || notice.seq === state.noticeSeq) return;
  state.noticeSeq = notice.seq;
  showNotice(notice.text);
}

function showNotice(text) {
  if (!text) return;
  const box = qs("#notice");
  box.textContent = text;
  box.classList.add("is-visible");
  window.clearTimeout(state.noticeTimer);
  state.noticeTimer = window.setTimeout(function () {
    box.classList.remove("is-visible");
  }, 4000);
}

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

/* ---------- 选歌弹窗 ---------- */

async function openPicker() {
  state.pickerOpen = true;
  state.pickerIndex = 0;
  qs("#picker").hidden = false;
  qs("#app").setAttribute("inert", "");
  qs("#picker-search").value = "";
  await loadPicker("");
  qs("#picker-search").focus();
}

function closePicker() {
  state.pickerOpen = false;
  qs("#picker").hidden = true;
  qs("#app").removeAttribute("inert");
}

async function loadPicker(query) {
  const result = await call("list_songs", query);
  state.pickerItems = (result && result.items) || [];
  state.pickerIndex = 0;
  renderPicker();
}

function renderPicker() {
  const list = qs("#picker-list");
  if (!state.pickerItems.length) {
    list.innerHTML = '<div class="picker-empty">' + esc(T("player.pick.empty")) + "</div>";
    return;
  }
  list.innerHTML = state.pickerItems
    .map(function (item, index) {
      const meta = [item.authors || T("player.unknown_author")];
      if (item.in_playlist) meta.push(T("player.pick.in_playlist"));
      return (
        '<button type="button" role="option" aria-selected="' +
        (index === state.pickerIndex ? "true" : "false") +
        '" class="picker-item' +
        (index === state.pickerIndex ? " is-active" : "") +
        '" data-md5="' +
        esc(item.md5) +
        '" data-index="' +
        index +
        '">' +
        '<span class="picker-name">' +
        esc(item.title) +
        "</span>" +
        '<span class="picker-meta">' +
        esc(meta.join(" · ")) +
        "</span></button>"
      );
    })
    .join("");
}

function movePicker(delta) {
  if (!state.pickerItems.length) return;
  state.pickerIndex =
    (state.pickerIndex + delta + state.pickerItems.length) % state.pickerItems.length;
  renderPicker();
  const active = qs('.picker-item[data-index="' + state.pickerIndex + '"]');
  if (active) active.scrollIntoView({ block: "nearest" });
}

function choosePicker(index) {
  const item = state.pickerItems[index];
  if (!item) return;
  closePicker();
  call("pick_loop_song", item.md5, Math.round(state.playedMs)).then(apply);
}

/* ---------- 事件 ---------- */

function bindEvents() {
  qs("#play").addEventListener("click", togglePlay);
  qs("#prev").addEventListener("click", function () {
    callTrack("prev_track");
  });
  qs("#next").addEventListener("click", function () {
    callTrack("next_track");
  });

  qsa(".mode-btn").forEach(function (button) {
    button.addEventListener("click", function () {
      call("set_mode", button.dataset.mode).then(apply);
    });
  });

  qs("#playlists").addEventListener("click", function (event) {
    const item = event.target.closest(".playlist-item");
    if (item) call("select_playlist", item.dataset.uid).then(apply);
  });

  qs("#queue-list").addEventListener("click", function (event) {
    const item = event.target.closest(".queue-item");
    if (item) call("jump_to", item.dataset.md5, Math.round(state.playedMs)).then(apply);
  });

  qs("#queue-toggle").addEventListener("click", function () {
    call("set_queue_visible", !state.data.queue.visible).then(apply);
  });
  qs("#queue-collapse").addEventListener("click", function () {
    call("set_queue_visible", false).then(apply);
  });

  qs("#empty-action").addEventListener("click", function () {
    call("open_manager");
  });

  qs("#pick-loop").addEventListener("click", openPicker);
  qs("#picker-close").addEventListener("click", closePicker);
  qs("#picker").addEventListener("click", function (event) {
    if (event.target === qs("#picker")) closePicker();
  });
  qs("#picker-list").addEventListener("click", function (event) {
    const item = event.target.closest(".picker-item");
    if (item) choosePicker(Number(item.dataset.index));
  });

  const search = qs("#picker-search");
  search.addEventListener("input", function () {
    const value = search.value;
    window.clearTimeout(state.pickerTimer);
    state.pickerTimer = window.setTimeout(function () {
      loadPicker(value);
    }, 150);
  });
  search.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      movePicker(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      movePicker(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
      choosePicker(state.pickerIndex);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closePicker();
    }
  });

  const seek = qs("#seek");
  seek.addEventListener("input", function () {
    state.draggingSeek = true;
    renderProgress();
  });
  seek.addEventListener("change", function () {
    const duration = durationMs();
    if (duration > 0) {
      audio.currentTime = (Number(seek.value) / 1000) * (duration / 1000);
      reportPosition();
    }
    state.draggingSeek = false;
    renderProgress();
  });

  const volume = qs("#volume");
  volume.addEventListener("input", function () {
    const value = Number(volume.value);
    audio.volume = value / 100;
    if (state.data) state.data.volume = value / 100;
    setFill(volume, value / 100);
    qs("#volume-value").textContent = value + "%";
  });
  volume.addEventListener("change", function () {
    call("set_volume", Number(volume.value) / 100);
  });

  audio.addEventListener("loadedmetadata", function () {
    if (state.pendingSeek !== null) {
      const duration = isFinite(audio.duration) ? audio.duration : 0;
      const target = duration > 0 ? Math.min(state.pendingSeek / 1000, Math.max(0, duration - 0.25)) : 0;
      try {
        audio.currentTime = target;
      } catch (error) {
        /* 元数据还没准备好时赋值会抛，下一次事件会补上 */
      }
      state.pendingSeek = null;
    }
    renderProgress();
    if (state.autoplay) playAudio();
  });

  audio.addEventListener("play", function () {
    window.clearTimeout(state.startTimer);
    setPlayingUI(true);
    call("set_playing", true);
  });

  audio.addEventListener("pause", function () {
    window.clearTimeout(state.startTimer);
    setPlayingUI(false);
    call("set_playing", false);
    reportPosition();
  });

  audio.addEventListener("ended", function () {
    callTrack("track_ended");
  });

  audio.addEventListener("error", function () {
    if (audio.getAttribute("src")) reportFailed("media");
  });

  document.addEventListener("keydown", function (event) {
    if (state.pickerOpen) {
      if (event.key === "Escape") {
        event.preventDefault();
        closePicker();
      }
      return;
    }
    const tag = (event.target && event.target.tagName ? event.target.tagName : "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;

    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowLeft" && event.ctrlKey) {
      event.preventDefault();
      callTrack("prev_track");
    } else if (event.key === "ArrowRight" && event.ctrlKey) {
      event.preventDefault();
      callTrack("next_track");
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      seekBy(-5000);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      seekBy(5000);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      stepVolume(5);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      stepVolume(-5);
    } else if (event.key === "Escape") {
      if (state.data && state.data.queue.visible) {
        event.preventDefault();
        call("set_queue_visible", false).then(apply);
      }
    }
  });
}

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
