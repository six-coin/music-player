/* 事件绑定：按钮、进度条、音量、audio 事件、窗口内快捷键。 */
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
    if (item && item.dataset.state !== "current") {
      call("jump_to", item.dataset.md5, Math.round(state.playedMs)).then(apply);
    }
  });

  qs("#queue-toggle").addEventListener("click", function () {
    if (!state.data) return; // 快照还没到，别去读 state.data.queue
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
    if (runShortcut(event)) event.preventDefault();
  });
}

/* 快捷键全部来自设置：快照里的 keys 就是当前绑定，认不出来就不响应。
   顺序即优先级——设置页会拦住重复绑定，手改出来的重复键按这个顺序取第一个。 */
function runShortcut(event) {
  const keys = playerKeys();
  if (matchKey(event, keys.play_pause)) {
    togglePlay();
    return true;
  }
  if (matchKey(event, keys.next)) {
    callTrack("next_track");
    return true;
  }
  if (matchKey(event, keys.prev)) {
    callTrack("prev_track");
    return true;
  }
  if (matchKey(event, keys.seek_back)) {
    seekBy(-5000);
    return true;
  }
  if (matchKey(event, keys.seek_forward)) {
    seekBy(5000);
    return true;
  }
  if (matchKey(event, keys.volume_up)) {
    stepVolume(5);
    return true;
  }
  if (matchKey(event, keys.volume_down)) {
    stepVolume(-5);
    return true;
  }
  if (matchKey(event, keys.pick_loop)) {
    // 任何模式下都能挑一首来循环：选完自动切到单曲循环。
    if (state.data) openPicker();
    return true;
  }
  if (matchKey(event, keys.queue)) {
    if (!state.data || !state.data.queue.visible) return false;
    call("set_queue_visible", false).then(apply);
    return true;
  }
  return false;
}
