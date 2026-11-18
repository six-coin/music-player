/* 渲染：快照进来到界面出去，只读状态、不发命令。 */
/* ---------- 快照 ---------- */

function apply(data) {
  if (!data || !data.ok) return;
  state.data = data;
  applyTheme(data.theme);

  qs("#app").classList.toggle("no-queue", !data.queue.visible);
  renderPlaylists();
  renderPomodoros();
  renderTrack();
  renderTransport();
  renderQueue();
  renderEmpty();
  renderVolume();
  renderNotice();
  renderPomodoroDetail();
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
  const md5 = track ? track.md5 : null;
  if (md5 !== state.trackMd5) {
    state.trackMd5 = md5;
    const box = qs("#playing");
    box.classList.remove("is-switching");
    void box.offsetWidth;
    box.classList.add("is-switching");
  }
  qs("#track-title").textContent = track ? track.title : "";
  qs("#track-authors").textContent = track
    ? track.authors || T("player.unknown_author")
    : "";
  renderTrackHead(data.playlist);
  const pickLoop = qs("#pick-loop");
  pickLoop.hidden = !track || data.mode !== "repeat_one";
  pickLoop.title = T("player.action.pick_loop_title", {
    key: prettyKey(playerKeys().pick_loop),
  });
  qs("#play").disabled = !track;
}

/* 卡片顶部：这是哪个歌单，以及它有没有开自适应。 */
function renderTrackHead(playlist) {
  const head = qs("#track-head");
  head.hidden = !playlist;
  if (!playlist) return;
  qs("#track-playlist").textContent = playlist.title;
  const badge = qs("#track-adaptation");
  const on = !!playlist.adaptation;
  badge.textContent = T(on ? "player.adaptation.on" : "player.adaptation.off");
  badge.classList.toggle("is-on", on);
  // 调试状态下自适应既不判定也不记录，徽标只能说明「歌单开着」，得补一句。
  badge.title = T(
    on
      ? playlist.debug
        ? "player.adaptation.hint_debug"
        : "player.adaptation.hint_on"
      : "player.adaptation.hint_off"
  );
}

function renderTransport() {
  const data = state.data;
  qs("#prev").disabled = !data.transport.can_prev;
  qs("#next").disabled = !data.transport.can_next;

  qsa(".mode-btn").forEach(function (button) {
    const active = button.dataset.mode === data.mode;
    const label = T("player.mode." + button.dataset.mode);
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.setAttribute("title", label);
    // 图标按钮没有可见文字，读屏只能靠 aria-label。
    button.setAttribute("aria-label", label);
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
  const top = list.scrollTop;

  if (data.queue.pinned) {
    list.innerHTML =
      '<div class="queue-pinned">' +
      esc(T("player.queue.pinned", { title: data.queue.pinned })) +
      "</div>";
    list.scrollTop = 0;
    state.lastCurrent = null;
    return;
  }

  if (!data.queue.items.length) {
    list.innerHTML = '<div class="queue-empty">' + esc(T("player.queue.empty")) + "</div>";
  } else {
    list.innerHTML = data.queue.items
      .map(function (item, index) {
        const current = item.state === "current";
        return (
          '<button type="button" class="queue-item' +
          (item.state === "played" ? " is-played" : "") +
          (current ? " is-current" : "") +
          (item.missing ? " is-missing" : "") +
          '" data-md5="' +
          esc(item.md5) +
          '" data-state="' +
          esc(item.state) +
          '" title="' +
          esc(item.title) +
          '"' +
          (current ? ' aria-current="true"' : "") +
          ">" +
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

  list.scrollTop = top;

  // 换曲时把当前曲滚进视野；同一首重绘时保留用户自己的滚动位置。
  if (data.queue.current_md5 && data.queue.current_md5 !== state.lastCurrent) {
    const row = list.querySelector('.queue-item[data-state="current"]');
    if (row) row.scrollIntoView({ block: "nearest" });
    state.lastCurrent = data.queue.current_md5;
  }
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
