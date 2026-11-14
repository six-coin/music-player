/* 歌单分区的事件绑定。 */
function bindPlaylistEvents() {
  qs("#btn-new-playlist").addEventListener("click", openCreatePlaylist);

  qs("#playlist-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-playlist-uid]");
    if (row) selectPlaylist(row.dataset.playlistUid);
  });

  qs("#playlist-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-playlist-uid]");
    if (!row) return;
    event.preventDefault();
    const playlist = playlistByUid(row.dataset.playlistUid);
    if (!playlist || playlist.builtin) return;
    if (state.active !== playlist.uid) selectPlaylist(playlist.uid);
    openMenu({ x: event.clientX, y: event.clientY }, [
      {
        label: T("playlist.delete"),
        onClick: function () {
          confirmDeletePlaylist(playlist);
        },
      },
    ]);
  });

  const playlistSearch = qs("#playlists-search");
  playlistSearch.addEventListener("input", function () {
    state.playlistQuery = playlistSearch.value;
    qs("#playlists-search-clear").hidden = !playlistSearch.value;
    renderPlaylistList();
  });
  qs("#playlists-search-clear").addEventListener("click", function () {
    playlistSearch.value = "";
    state.playlistQuery = "";
    qs("#playlists-search-clear").hidden = true;
    renderPlaylistList();
    playlistSearch.focus();
  });

  const playlistDetail = qs("#playlist-detail");

  playlistDetail.addEventListener("input", function (event) {
    if (event.target.id === "playlist-name") schedulePlaylistNameSave(event.target);
  });

  playlistDetail.addEventListener(
    "blur",
    function (event) {
      if (event.target.id === "playlist-name") flushPlaylistName();
    },
    true
  );

  playlistDetail.addEventListener("selectchange", async function (event) {
    const playlist = playlistByUid(state.active);
    if (!playlist) return;
    const mode = event.target.closest("[data-filter-mode]");
    if (mode) {
      await flushPlaylistName();
      const data = await call("update_filter", playlist.uid, Number(mode.dataset.filterMode), {
        mode: mode.dataset.value,
      });
      if (data) apply(data);
      return;
    }
    const target = event.target.closest("[data-filter-target]");
    if (target) {
      await flushPlaylistName();
      const data = await call("update_filter", playlist.uid, Number(target.dataset.filterTarget), {
        target: target.dataset.value,
      });
      if (data) apply(data);
    }
  });

  playlistDetail.addEventListener("change", async function (event) {
    const playlist = playlistByUid(state.active);
    if (!playlist) return;

    const inherit = event.target.closest("[data-inherit]");
    if (inherit) {
      const key = inherit.dataset.inherit;
      const value = inherit.checked ? null : adaptationDefaults()[key];
      const data = await call("update_adaptation", playlist.uid, { [key]: value });
      if (data) apply(data);
      return;
    }

    const field = event.target.closest("[data-adapt]");
    if (field) {
      const key = field.dataset.adapt;
      // 跳过基数在输入框里是百分比，存下去要换算成比例。
      const value = key === "base" ? Number(field.value) / 100 : parseInt(field.value, 10);
      if (!Number.isFinite(value)) {
        renderPlaylistDetail();
        return;
      }
      const data = await call("update_adaptation", playlist.uid, { [key]: value });
      if (data) apply(data);
    }
  });

  playlistDetail.addEventListener("click", async function (event) {
    const playlist = playlistByUid(state.active);
    if (!playlist) return;

    if (event.target.closest("[data-stats]")) {
      openStatsDrawer(playlist);
      return;
    }

    const adaptSwitch = event.target.closest("[data-adapt-enabled]");
    if (adaptSwitch) {
      const next = adaptSwitch.getAttribute("aria-checked") !== "true";
      adaptSwitch.setAttribute("aria-checked", next ? "true" : "false");
      const data = await call("update_adaptation", playlist.uid, { enabled: next });
      if (!data) return;
      await delay(170);
      apply(data);
      return;
    }

    if (event.target.closest("[data-playlist-add]")) {
      openSongPicker(playlist);
      return;
    }
    if (event.target.closest("[data-filter-add]")) {
      const data = await call("add_filter", playlist.uid);
      if (data) apply(data);
      return;
    }
    if (event.target.closest("[data-playlist-preview]")) {
      openPlaylistPreview(playlist);
      return;
    }

    const removeEntry = event.target.closest("[data-entry-remove]");
    if (removeEntry) {
      const data = await call("remove_playlist_song", playlist.uid, removeEntry.dataset.entryRemove);
      if (data) apply(data);
      return;
    }

    const pick = event.target.closest("[data-filter-pick]");
    if (pick) {
      const index = Number(pick.dataset.filterPick);
      openValuePicker(playlist, index, playlist.filters[index]);
      return;
    }

    const up = event.target.closest("[data-filter-up]");
    if (up) {
      const data = await call("move_filter", playlist.uid, Number(up.dataset.filterUp), -1);
      if (data) apply(data);
      return;
    }
    const down = event.target.closest("[data-filter-down]");
    if (down) {
      const data = await call("move_filter", playlist.uid, Number(down.dataset.filterDown), 1);
      if (data) apply(data);
      return;
    }
    const remove = event.target.closest("[data-filter-remove]");
    if (remove) {
      const data = await call("remove_filter", playlist.uid, Number(remove.dataset.filterRemove));
      if (data) apply(data);
      return;
    }

    const menu = event.target.closest("[data-menu='playlist']");
    if (menu) {
      openMenu(menu, [
        {
          label: T("playlist.delete"),
          onClick: function () {
            confirmDeletePlaylist(playlist);
          },
        },
      ]);
    }
  });

  playlistDetail.addEventListener("dragstart", function (event) {
    const row = event.target.closest(".entry-row");
    if (!row) return;
    state.dragMd5 = row.dataset.entry;
    row.classList.add("is-dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", state.dragMd5);
    }
  });

  playlistDetail.addEventListener("dragover", function (event) {
    const row = event.target.closest(".entry-row");
    if (!row || !state.dragMd5) return;
    event.preventDefault();
    qsa(".entry-row", playlistDetail).forEach(function (node) {
      node.classList.remove("drop-before", "drop-after");
    });
    const rect = row.getBoundingClientRect();
    row.classList.add(event.clientY > rect.top + rect.height / 2 ? "drop-after" : "drop-before");
  });

  playlistDetail.addEventListener("drop", async function (event) {
    const row = event.target.closest(".entry-row");
    const playlist = playlistByUid(state.active);
    if (!row || !state.dragMd5 || !playlist) return;
    event.preventDefault();

    const after = row.classList.contains("drop-after");
    const entries = (playlist.entries || []).slice();
    const from = entries.indexOf(state.dragMd5);
    if (from === -1) return;
    entries.splice(from, 1);
    let index = entries.indexOf(row.dataset.entry);
    if (index === -1) index = entries.length;
    if (after) index += 1;
    entries.splice(index, 0, state.dragMd5);

    state.dragMd5 = null;
    const data = await call("set_playlist_entries", playlist.uid, entries);
    if (data) apply(data);
  });

  playlistDetail.addEventListener("dragend", function () {
    state.dragMd5 = null;
    qsa(".entry-row", playlistDetail).forEach(function (node) {
      node.classList.remove("is-dragging", "drop-before", "drop-after");
    });
  });
}
