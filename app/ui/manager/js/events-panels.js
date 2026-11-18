/* 试听条、设置页、统计抽屉、歌曲详情的事件绑定。 */
function bindPanelEvents() {
  /* ---------- 试听条 ---------- */

  qs("#audition-toggle").addEventListener("click", function () {
    const audio = auditionAudio();
    if (!audio.src) return;
    if (audio.paused) audio.play();
    else audio.pause();
  });

  qs("#audition-close").addEventListener("click", auditionStop);

  qs("#audition-volume").addEventListener("input", function (event) {
    const value = Number(event.target.value);
    auditionAudio().volume = value / 100;
    qs("#audition-volume-value").textContent = value + "%";
  });

  qs("#audition-volume").addEventListener("change", function (event) {
    patchSetting("audition.volume", Number(event.target.value) / 100);
  });

  qs("#audition-seek").addEventListener("input", function (event) {
    const audio = auditionAudio();
    if (!Number.isFinite(audio.duration) || !audio.duration) return;
    audio.currentTime = (Number(event.target.value) / 1000) * audio.duration;
  });

  ["play", "pause", "ended", "timeupdate", "loadedmetadata", "emptied"].forEach(function (name) {
    auditionAudio().addEventListener(name, syncAudition);
  });

  /* ---------- 设置页 ---------- */

  qs("#settings-nav").addEventListener("click", function (event) {
    const tab = event.target.closest("[data-settings]");
    if (!tab) return;
    if (tab.dataset.settings === state.settingsTab) return;
    state.settingsTab = tab.dataset.settings;
    renderSettings(true);
  });

  const settingsBody = qs("#settings-body");

  settingsBody.addEventListener("click", async function (event) {
    const keycap = event.target.closest("[data-key-group]");
    if (keycap) {
      beginKeyCapture(keycap);
      return;
    }
    const resetKey = event.target.closest("[data-key-reset]");
    if (resetKey) {
      const parts = resetKey.dataset.keyReset.split(":");
      const cap = resetKey.parentNode ? resetKey.parentNode.querySelector("[data-key-group]") : null;
      await saveKey(parts[0], parts[1], keyDefaults(parts[0])[parts[1]], cap);
      return;
    }
    const resetAll = event.target.closest("[data-key-reset-all]");
    if (resetAll) {
      await resetKeyGroup(resetAll.dataset.keyResetAll);
      return;
    }
    const theme = event.target.closest("[data-theme-value]");
    if (theme) {
      const data = await call("set_theme", theme.dataset.themeValue);
      if (data) apply(data);
      return;
    }
    const language = event.target.closest("[data-language]");
    if (language) {
      const data = await call("set_language", language.dataset.language);
      if (!data) return;
      // 文案表要重新拉一次：静态标记上的中文是 HTML 里的兜底，不换就还是旧语言。
      await loadStrings();
      applyStrings();
      apply(data);
      return;
    }
    const toggle = event.target.closest("[data-setting-switch]");
    if (toggle) {
      const next = toggle.getAttribute("aria-checked") !== "true";
      toggle.setAttribute("aria-checked", next ? "true" : "false");
      await patchSetting(toggle.dataset.settingSwitch, next);
    }
  });

  settingsBody.addEventListener("change", async function (event) {
    if (event.target.id === "import-dir") {
      const dir = event.target.value.trim();
      event.target.value = dir;
      await patchSetting("import.dir", dir);
      return;
    }
    if (event.target.id === "player-volume") {
      await patchSetting("player.volume", Number(event.target.value) / 100);
      return;
    }
    if (event.target.id === "audition-default") {
      await patchSetting("audition.volume", Number(event.target.value) / 100);
      return;
    }
    const field = event.target.closest("[data-default]");
    if (field) {
      const key = field.dataset.default;
      const value = Number(field.value);
      if (!Number.isFinite(value)) {
        renderSettings();
        return;
      }
      // 跳过基数在界面上是 1–99 的百分比，存的是 0.01–0.99 的比例。
      await patchSetting("common.adaptation." + key, key === "base" ? value / 100 : value);
    }
  });

  settingsBody.addEventListener("keydown", function (event) {
    if (event.target.id !== "data-dir" || event.key !== "Enter") return;
    event.preventDefault();
    applyDataDir(event.target.value);
  });

  settingsBody.addEventListener("input", function (event) {
    if (event.target.id === "player-volume") {
      const label = qs("#player-volume-value");
      if (label) label.textContent = event.target.value + "%";
      return;
    }
    if (event.target.id === "audition-default") {
      const label = qs("#audition-default-value");
      if (label) label.textContent = event.target.value + "%";
    }
  });

  settingsBody.addEventListener("selectchange", async function (event) {
    const select = event.target.closest("[data-setting-select]");
    if (!select) return;
    await patchSetting(select.dataset.settingSelect, select.dataset.value);
  });

  /* 录制快捷键：捕获阶段拦下，别让 Esc、方向键先被别处的监听器吃掉。
     只按修饰键不算一个组合，继续等主键。 */
  document.addEventListener(
    "keydown",
    function (event) {
      if (!state.recording) return;
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") {
        endKeyCapture();
        return;
      }
      const spec = keySpec(event);
      if (!spec) return;
      const recording = state.recording;
      saveKey(recording.group, recording.action, spec, recording.node);
    },
    true
  );

  /* 点到别处就当放弃：录制状态留在身后，下一次随便按个键都会被吞掉。 */
  document.addEventListener("click", function (event) {
    if (!state.recording) return;
    if (event.target.closest("[data-key-group]")) return;
    endKeyCapture();
  });

  qs("#drawer-close").addEventListener("click", closeDrawer);

  qs("#drawer-body").addEventListener("click", async function (event) {
    if (!state.drawer) return;
    if (event.target.closest("[data-reset-all]")) {
      confirmClearPlaylistStats();
      return;
    }
    const one = event.target.closest("[data-reset-md5]");
    if (one) {
      confirmClearSongStats(one.dataset.resetMd5, one.dataset.resetTitle || "");
      return;
    }
  });

  qs("#song-detail").addEventListener("input", function (event) {
    if (event.target.id !== "song-name") return;
    scheduleNameSave(event.target);
  });

  qs("#song-detail").addEventListener("blur", function (event) {
    if (event.target.id === "song-name") flushNameSave();
  }, true);

  qs("#song-detail").addEventListener("click", async function (event) {
    const tag = event.target.closest("[data-tag]");
    if (tag && state.active) {
      await flushNameSave();
      const on = tag.dataset.on !== "1";
      const box = tag.closest("[data-tag-group-box]");
      if (on && box && box.dataset.unique === "1") {
        box.querySelectorAll(".chip-toggle.is-on").forEach(function (other) {
          if (other !== tag) {
            other.classList.remove("is-on");
            other.dataset.on = "0";
          }
        });
      }
      tag.dataset.on = on ? "1" : "0";
      tag.classList.toggle("is-on", on);
      syncTagGroup(box);
      syncSongTagFlags();

      const data = await call("toggle_music_tag", state.active, tag.dataset.tag, on);
      if (!data) return;
      if (data.ok === false) {
        apply(data);
        return;
      }
      // 详情区保持原样，避免整段重绘把动画和滚动位置一起冲掉；只刷新列表上的标记。
      state.data = data;
      renderSongList();
      return;
    }

    if (event.target.closest("#btn-authors")) {
      const music = musicByMd5(state.active);
      if (music) openAuthorPicker(music);
      return;
    }

    const copy = event.target.closest("[data-copy]");
    if (copy) {
      try {
        await navigator.clipboard.writeText(copy.dataset.copy);
        toast(T("action.copied"));
      } catch (error) {
        toast("复制失败：" + String(error), false);
      }
      return;
    }

    const menu = event.target.closest("[data-menu='song']");
    if (menu) {
      const music = musicByMd5(state.active);
      if (!music) return;
      openMenu(menu, songMenuItems(music));
    }
  });
}
