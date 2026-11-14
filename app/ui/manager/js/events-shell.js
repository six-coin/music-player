/* 外壳事件：导航、概览页签、全局点击分发、歌曲列表、搜索、多选条、弹窗与快捷键。 */
function bindShellEvents() {
  qsa(".rail-item").forEach(function (item) {
    item.addEventListener("click", function () {
      goSection(item.dataset.section);
    });
  });

  qsa(".stat").forEach(function (card) {
    card.addEventListener("click", function () {
      goSection(card.dataset.target);
    });
  });

  qsa(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      state.tab = tab.dataset.tab;
      qsa(".tab").forEach(function (node) {
        node.classList.toggle("is-active", node === tab);
      });
      if (state.data) renderRecent(state.data);
    });
  });

  document.addEventListener("click", function (event) {
    const action = event.target.closest("[data-action]");
    if (action) {
      const name = action.dataset.action;
      if (name === "import") doImport();
      else if (name === "data_dir") call("open_data_dir");
      else if (name === "log_dir") call("open_log_dir");
      else if (name === "integrity") openIntegrity();
      else if (name === "integrity_deep") openIntegrity({ deep: true });
      else if (name === "fix_orphans") confirmFixOrphans();
      else if (name === "clear_stats") confirmClearStats();
      else if (name === "browse_import_dir") browseImportDir();
      else if (name === "clear_import_dir") patchSetting("import.dir", "");
      else if (name === "refresh_status") refreshStatus();
      else if (name === "about_readme") openAboutReadme();
      else if (name === "about_reset") confirmResetSettings();
      else if (name === "about_data_dir") changeDataDir();
      else if (name === "about_restart") call("restart_app");
      else if (name === "goto_default") goSection("playlists");
      else if (name === "new_playlist") openCreatePlaylist();
      else if (name === "new_tag_group") openCreateTagGroup();
      else if (name === "new_author") openCreateAuthor();
      else if (name === "clean_authors") cleanAuthors();
      else if (name === "launch_player") launchProgram("launch_player");
      else if (name === "launch_simple") launchProgram("launch_simple");
      else if (name === "settings") goSection("settings");
      return;
    }

    const recent = event.target.closest("#recent .row[data-md5]");
    if (recent) {
      selectMusic(recent.dataset.md5);
      return;
    }

    const issue = event.target.closest("#issues .row");
    if (issue) {
      if (issue.dataset.issue === "orphan_file" || issue.dataset.issue === "broken_reference") {
        openIntegrity();
      } else {
        goSection("songs");
      }
      return;
    }

    if (state.drawer && !event.target.closest("#drawer") && !event.target.closest("[data-stats]")) {
      closeDrawer();
    }

    // 刚点开菜单的那一次点击不能再把菜单关掉。
    if (event.target.closest("[data-menu]")) return;
    if (!event.target.closest("#menu")) closeMenu();
  });
  const search = qs("#songs-search");
  search.addEventListener("input", function () {
    state.query = search.value;
    qs("#songs-search-clear").hidden = !search.value;
    renderSongList();
  });
  search.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      search.value = "";
      state.query = "";
      qs("#songs-search-clear").hidden = true;
      renderSongList();
    }
  });

  qs("#songs-search-clear").addEventListener("click", function () {
    search.value = "";
    state.query = "";
    qs("#songs-search-clear").hidden = true;
    renderSongList();
    search.focus();
  });

  qs("#songs-select-all").addEventListener("change", function (event) {
    const musics = visibleMusics();
    if (event.target.checked) {
      musics.forEach(function (music) {
        state.selection.add(music.md5);
      });
    } else {
      musics.forEach(function (music) {
        state.selection.delete(music.md5);
      });
    }
    renderSongs();
  });

  qs("#song-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest(".song-row");
    if (!row) return;
    event.preventDefault();
    const music = musicByMd5(row.dataset.md5);
    if (!music) return;
    if (state.active !== music.md5) selectMusic(music.md5);
    openMenu({ x: event.clientX, y: event.clientY }, songMenuItems(music));
  });

  qs("#song-list").addEventListener("click", function (event) {
    const row = event.target.closest(".song-row");
    if (!row) return;
    const md5 = row.dataset.md5;
    if (event.target.classList.contains("song-check")) {
      toggleSelection(md5);
      return;
    }
    if (event.shiftKey) selectRange(md5);
    else if (event.ctrlKey || event.metaKey) toggleSelection(md5);
    else selectMusic(md5);
  });

  qs("#song-list").addEventListener("keydown", function (event) {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (keys.indexOf(event.key) === -1) return;
    const musics = visibleMusics();
    if (!musics.length) return;
    event.preventDefault();
    let index = musics.findIndex(function (item) {
      return item.md5 === state.active;
    });
    if (index === -1) index = 0;
    if (event.key === "ArrowDown") index = Math.min(musics.length - 1, index + 1);
    else if (event.key === "ArrowUp") index = Math.max(0, index - 1);
    else if (event.key === "Home") index = 0;
    else index = musics.length - 1;
    const md5 = musics[index].md5;
    selectMusic(md5);
    window.requestAnimationFrame(function () {
      const row = qs('.song-row[data-md5="' + md5 + '"]');
      if (row) row.focus();
    });
  });

  qs("#selection-bar").addEventListener("click", function (event) {
    const button = event.target.closest("[data-batch]");
    if (!button) return;
    const action = button.dataset.batch;
    if (action === "tags") openBatchTags();
    else if (action === "playlist") openBatchPlaylist();
    else if (action === "delete") confirmDeleteSongs(Array.from(state.selection));
    else if (action === "clear") {
      state.selection.clear();
      renderSongs();
    }
  });
  qs("#modal-close").addEventListener("click", closeModal);
  qs("#modal").addEventListener("click", function (event) {
    if (event.target === qs("#modal")) closeModal();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (!qs("#modal").hidden) closeModal();
      else if (!qs("#drawer").hidden) closeDrawer();
      closeMenu();
      return;
    }
    if (!qs("#modal").hidden) trapFocus(event);
  });
}
