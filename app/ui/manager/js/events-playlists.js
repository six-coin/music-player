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

  // 歌单列表拖拽排序：顺序写回 playlists.json 的 items 数组，播放器也照它展示。
  bindDragSort(qs("#playlist-list"), {
    row: "[data-playlist-uid]",
    allow: function () {
      return !state.playlistQuery.trim();
    },
    key: function (node) {
      return node.dataset.playlistUid;
    },
    commit: async function (order) {
      const data = await call("reorder_playlists", order);
      if (data) apply(data);
    },
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

  // 条件行：按住左边的手柄拖，顺序写回这个歌单的条件数组。
  bindDragSort(playlistDetail, {
    row: "[data-filter-row]",
    handle: "[data-filter-grip]",
    key: function (node) {
      return node.dataset.filterRow;
    },
    commit: async function (order) {
      const playlist = playlistByUid(state.active);
      if (!playlist) return;
      const data = await call(
        "reorder_filters",
        playlist.uid,
        order.map(function (index) {
          return Number(index);
        })
      );
      if (data) apply(data);
    },
  });

  // 手动歌单的曲目：整行可拖，顺序写回 entries。
  bindDragSort(playlistDetail, {
    row: ".entry-row",
    key: function (node) {
      return node.dataset.entry;
    },
    commit: async function (order) {
      const playlist = playlistByUid(state.active);
      if (!playlist) return;
      const data = await call("set_playlist_entries", playlist.uid, order);
      if (data) apply(data);
    },
  });
}
