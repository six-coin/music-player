/* 歌单、标签、作者的编辑动作：新建、删除、条件取值、拖拽排序。 */
/* ---------- 删除前的从属关系 ---------- */

/* 二次确认里最多列三项：再多就不是「提醒」，而是把弹窗变成清单了。 */
const DEPENDENCY_LIMIT = 3;

function allMusics() {
  return (state.data && state.data.library.musics) || [];
}

function songsUsingTag(tagUid) {
  return allMusics().filter(function (music) {
    return (music.tags || []).indexOf(tagUid) !== -1;
  });
}

function songsUsingTagGroup(group) {
  const uids = new Set(
    (group.tags || []).map(function (tag) {
      return tag.uid;
    })
  );
  return allMusics().filter(function (music) {
    return (music.tags || []).some(function (uid) {
      return uids.has(uid);
    });
  });
}

function songsByAuthor(uid) {
  return allMusics().filter(function (music) {
    return (music.authors || []).indexOf(uid) !== -1;
  });
}

function playlistsWithSong(md5) {
  return ((state.data && state.data.playlists) || []).filter(function (playlist) {
    if (playlist.kind === "manual") {
      return (playlist.entries || []).indexOf(md5) !== -1;
    }
    return (playlist.filters || []).some(function (condition) {
      return condition.target === "music" && (condition.values || []).indexOf(md5) !== -1;
    });
  });
}

function playlistReferrers(uid) {
  return ((state.data && state.data.playlists) || []).filter(function (playlist) {
    if (playlist.uid === uid) return false;
    return (playlist.filters || []).some(function (condition) {
      return condition.target === "playlist" && (condition.values || []).indexOf(uid) !== -1;
    });
  });
}

function dependencyMarkup(items) {
  if (!items || !items.length) return "";
  const shown = items.slice(0, DEPENDENCY_LIMIT);
  const rest = items.length - shown.length;
  const rows = shown
    .map(function (item) {
      return (
        '<li><span class="dep-kind">' + esc(item.kind) + "</span>" +
        '<span class="dep-name" title="' + esc(item.name) + '">' + esc(item.name) + "</span></li>"
      );
    })
    .join("");
  return (
    '<div class="deps"><p class="deps-title">' + esc(T("delete.deps_title")) + "</p>" +
    '<ul class="deps-list">' + rows + "</ul>" +
    (rest > 0
      ? '<p class="deps-more">' + esc(T("delete.deps_more", { count: rest })) + "</p>"
      : "") +
    "</div>"
  );
}

function songDeps(musics) {
  return musics.map(function (music) {
    return { kind: T("delete.kind_song"), name: music.title };
  });
}

function playlistDeps(playlists) {
  return playlists.map(function (playlist) {
    return { kind: T("delete.kind_playlist"), name: playlist.title };
  });
}

/* ---------- 歌单交互 ---------- */

function openCreatePlaylist() {
  let kind = "manual";
  openModal({
    title: T("playlist.create_title"),
    body:
      '<div class="field-row"><span class="field-label">' + esc(T("playlist.name")) +
      '</span><div class="field-body"><input class="input" id="new-playlist-name" placeholder="' +
      esc(T("playlist.name_placeholder")) + '" maxlength="120"></div></div>' +
      '<div class="field-row"><span class="field-label">' + esc(T("playlist.kind")) +
      '</span><div class="field-body"><div class="seg" id="new-playlist-kind">' +
      '<button class="seg-item is-active" type="button" data-kind="manual">' +
      esc(T("playlist.kind_manual")) + "</button>" +
      '<button class="seg-item" type="button" data-kind="filter">' +
      esc(T("playlist.kind_filter")) + "</button></div></div></div>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("playlist.create"),
        primary: true,
        onClick: async function () {
          const input = qs("#new-playlist-name");
          const name = input.value.trim();
          if (!name) {
            input.classList.add("invalid");
            return;
          }
          const data = await call("create_playlist", name, kind);
          if (data && data.ok) {
            closeModal();
            apply(data);
          } else if (data) {
            toast(data.message || T("playlist.invalid"), false);
          }
        },
      },
    ],
    onMount: function () {
      qs("#new-playlist-kind").onclick = function (event) {
        const button = event.target.closest("[data-kind]");
        if (!button) return;
        kind = button.dataset.kind;
        qsa("#new-playlist-kind .seg-item").forEach(function (node) {
          node.classList.toggle("is-active", node === button);
        });
      };
      qs("#new-playlist-name").focus();
    },
  });
}

function confirmDeletePlaylist(playlist) {
  const referrers = playlistReferrers(playlist.uid);
  openModal({
    title: T("playlist.delete"),
    body:
      '<p class="modal-note">' +
      esc(T("playlist.delete_confirm", { name: playlist.title })) +
      "</p>" +
      dependencyMarkup(playlistDeps(referrers)),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("playlist.delete"),
        danger: true,
        onClick: async function () {
          const data = await call("delete_playlist", playlist.uid);
          closeModal();
          if (data) apply(data);
        },
      },
    ],
  });
}

function openSongPicker(playlist) {
  const existing = new Set(playlist.entries || []);
  const chosen = new Set();
  const items = (state.data.library.musics || []).filter(function (music) {
    return !existing.has(music.md5);
  });

  if (!items.length) {
    openModal({
      title: T("playlist.add_songs"),
      body: '<p class="row-empty">' + esc(T("playlist.pick_songs_empty")) + "</p>",
      actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
    });
    return;
  }

  openModal({
    title: T("playlist.add_songs"),
    wide: true,
    body:
      '<input class="input" id="pick-song-search" placeholder="' + esc(T("songs.search")) +
      '"><ul class="pick-list" id="pick-song-list" style="margin-top:10px">' +
      items
        .map(function (music) {
          const name = (music.title + " " + (music.authors_text || "")).toLowerCase();
          return (
            '<li class="pick-row" data-song-pick="' + esc(music.md5) + '" data-name="' +
            esc(name) + '"><span class="pick-row-body">' + esc(music.title) +
            '</span><span class="pick-row-tools">' +
            esc(music.authors_text || "") + "</span></li>"
          );
        })
        .join("") +
      "</ul>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("action.apply"),
        primary: true,
        onClick: async function () {
          if (!chosen.size) {
            closeModal();
            return;
          }
          const data = await call("add_playlist_songs", playlist.uid, Array.from(chosen));
          closeModal();
          if (data) apply(data);
        },
      },
    ],
    onMount: function () {
      qs("#pick-song-search").addEventListener("input", function () {
        const query = this.value.trim().toLowerCase();
        qsa("#pick-song-list .pick-row").forEach(function (row) {
          row.hidden = Boolean(query) && row.dataset.name.indexOf(query) === -1;
        });
      });
      qs("#modal-body").onclick = function (event) {
        const row = event.target.closest("[data-song-pick]");
        if (!row) return;
        const md5 = row.dataset.songPick;
        if (chosen.has(md5)) chosen.delete(md5);
        else chosen.add(md5);
        row.classList.toggle("is-on", chosen.has(md5));
      };
    },
  });
}

function valueOptions(target, excludeUid) {
  if (target === "music") {
    return (state.data.library.musics || []).map(function (music) {
      return { uid: music.md5, label: music.title, sub: music.authors_text || "" };
    });
  }
  if (target === "playlist") {
    return (state.data.playlists || [])
      .filter(function (playlist) {
        return playlist.uid !== excludeUid;
      })
      .map(function (playlist) {
        return { uid: playlist.uid, label: playlist.title, sub: "" };
      });
  }
  if (target === "tag") {
    const tags = tagMap();
    return Object.keys(tags).map(function (uid) {
      return { uid: uid, label: tags[uid].name, sub: tags[uid].group.name };
    });
  }
  if (target === "author") {
    return (state.data.library.authors || []).map(function (author) {
      return { uid: author.uid, label: author.name, sub: "" };
    });
  }
  return [];
}

function openValuePicker(playlist, index, condition) {
  const options = valueOptions(condition.target, playlist.uid);
  const chosen = new Set(condition.values || []);

  if (!options.length) {
    openModal({
      title: T("playlist.filter_pick"),
      body: '<p class="row-empty">' + esc(T("playlist.pick_empty")) + "</p>",
      actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
    });
    return;
  }

  openModal({
    title: T("playlist.filter_pick"),
    wide: true,
    body:
      '<input class="input" id="pick-value-search" placeholder="' + esc(T("playlist.pick_search")) +
      '"><ul class="pick-list" id="pick-value-list" style="margin-top:10px">' +
      options
        .map(function (option) {
          const active = chosen.has(option.uid);
          const name = (option.label + " " + option.sub).toLowerCase();
          return (
            '<li class="pick-row' + (active ? " is-on" : "") + '" data-value-pick="' +
            esc(option.uid) + '" data-name="' + esc(name) + '">' +
            '<span class="pick-row-body">' + esc(option.label) + "</span>" +
            '<span class="pick-row-tools">' + esc(option.sub) + "</span></li>"
          );
        })
        .join("") +
      "</ul>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("action.apply"),
        primary: true,
        onClick: async function () {
          const data = await call("update_filter", playlist.uid, index, {
            values: Array.from(chosen),
          });
          closeModal();
          if (data) apply(data);
        },
      },
    ],
    onMount: function () {
      qs("#pick-value-search").addEventListener("input", function () {
        const query = this.value.trim().toLowerCase();
        qsa("#pick-value-list .pick-row").forEach(function (row) {
          row.hidden = Boolean(query) && row.dataset.name.indexOf(query) === -1;
        });
      });
      qs("#modal-body").onclick = function (event) {
        const row = event.target.closest("[data-value-pick]");
        if (!row) return;
        const uid = row.dataset.valuePick;
        if (chosen.has(uid)) chosen.delete(uid);
        else chosen.add(uid);
        row.classList.toggle("is-on", chosen.has(uid));
      };
    },
  });
}

async function openPlaylistPreview(playlist) {
  const result = await call("get_playlist_songs", playlist.uid);
  if (!result) return;

  let body;
  if (!result.ok) {
    body = '<div class="error-card" role="alert"><p class="error-card-text">' +
      esc(result.message) + "</p></div>";
  } else if (!result.items.length) {
    body = '<p class="row-empty">' + esc(T("playlist.preview_empty")) + "</p>";
  } else {
    body =
      '<ul class="report-list">' +
      result.items
        .map(function (music) {
          return (
            "<li>" + esc(music.title) +
            (music.authors_text ? " · " + esc(music.authors_text) : "") + "</li>"
          );
        })
        .join("") +
      "</ul>";
  }

  openModal({
    title: T("playlist.preview_title"),
    body: body,
    wide: true,
    actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
  });
}

function schedulePlaylistNameSave(input) {
  if (!state.active) return;
  input.classList.remove("invalid");
  window.clearTimeout(state.playlistNameTimer);
  const uid = state.active;
  state.playlistNameTimer = window.setTimeout(function () {
    state.playlistNameTimer = null;
    savePlaylistName(uid, input.value);
  }, 420);
}

async function savePlaylistName(uid, value) {
  const result = await call("update_playlist_name", uid, value);
  const input = qs("#playlist-name");
  if (!result || !result.ok) {
    if (input) input.classList.add("invalid");
    return;
  }
  const playlist = playlistByUid(uid);
  if (playlist) playlist.title = value.trim();
  const row = qs('.song-row[data-playlist-uid="' + uid + '"] .song-title');
  if (row) row.textContent = value.trim();
  const heading = qs("#playlist-detail .detail-title h2");
  if (heading) heading.textContent = value.trim();
}

async function flushPlaylistName() {
  if (!state.playlistNameTimer) return;
  window.clearTimeout(state.playlistNameTimer);
  state.playlistNameTimer = null;
  const input = qs("#playlist-name");
  if (input && state.active) await savePlaylistName(state.active, input.value);
}
/* ---------- 标签与作者交互 ---------- */

function openCreateTagGroup() {
  const flags = { compulsory: false, unique: false };
  openModal({
    title: T("tag.create_title"),
    body:
      '<div class="field-row"><span class="field-label">' + esc(T("tag.name")) +
      '</span><div class="field-body"><input class="input" id="new-tag-name" placeholder="' +
      esc(T("tag.name_placeholder")) + '" maxlength="60"></div></div>' +
      '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
      esc(T("tag.compulsory")) + '</div><p class="toggle-hint">' +
      esc(T("tag.compulsory_hint")) + "</p></div>" +
      '<button class="switch" type="button" role="switch" data-flag="compulsory" ' +
      'aria-checked="false"><span class="switch-knob"></span></button></div>' +
      '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
      esc(T("tag.unique")) + '</div><p class="toggle-hint">' +
      esc(T("tag.unique_hint")) + "</p></div>" +
      '<button class="switch" type="button" role="switch" data-flag="unique" ' +
      'aria-checked="false"><span class="switch-knob"></span></button></div>',
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("tag.create"),
        primary: true,
        onClick: async function () {
          const input = qs("#new-tag-name");
          const name = input.value.trim();
          if (!name) {
            input.classList.add("invalid");
            return;
          }
          const data = await call("create_tag_group", name, flags.compulsory, flags.unique);
          if (data && data.ok) {
            closeModal();
            apply(data);
          } else if (data) {
            toast(data.message || T("tag.name_required"), false);
          }
        },
      },
    ],
    onMount: function () {
      qs("#new-tag-name").focus();
      qsa("[data-flag]").forEach(function (button) {
        button.addEventListener("click", function () {
          const key = button.dataset.flag;
          flags[key] = !flags[key];
          button.setAttribute("aria-checked", flags[key] ? "true" : "false");
        });
      });
    },
  });
}

function confirmDeleteTagGroup(group) {
  const songs = songsUsingTagGroup(group);
  openModal({
    title: T("tag.delete_group"),
    body:
      '<p class="modal-note">' + esc(T("tag.delete_confirm", { name: group.name })) + "</p>" +
      dependencyMarkup(songDeps(songs)),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("tag.delete_group"),
        danger: true,
        onClick: async function () {
          const data = await call("delete_tag_group", group.uid, false);
          if (!data) return;
          if (data.ok) {
            closeModal();
            apply(data);
            return;
          }
          openModal({
            title: T("tag.delete_group"),
            body:
              '<p class="modal-note">' + esc(data.message) + "</p>" +
              dependencyMarkup(songDeps(songs)),
            actions: [
              { label: T("action.cancel"), onClick: closeModal },
              {
                label: T("tag.delete_force"),
                danger: true,
                onClick: async function () {
                  const forced = await call("delete_tag_group", group.uid, true);
                  if (forced) {
                    closeModal();
                    apply(forced);
                  }
                },
              },
            ],
          });
        },
      },
    ],
  });
}

function confirmDeleteTag(group, tag) {
  const songs = songsUsingTag(tag.uid);
  openModal({
    title: T("tag.delete_tag"),
    body:
      '<p class="modal-note">' +
      esc(T("tag.delete_tag_confirm", { name: tag.name, group: group.name })) +
      "</p>" +
      dependencyMarkup(songDeps(songs)),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("tag.delete_tag"),
        danger: true,
        onClick: async function () {
          const data = await call("remove_tag", group.uid, tag.uid);
          closeModal();
          if (data) apply(data);
        },
      },
    ],
  });
}

function openCreateAuthor() {
  openModal({
    title: T("author.create_title"),
    body:
      '<div class="field-row"><span class="field-label">' + esc(T("author.name")) +
      '</span><div class="field-body"><input class="input" id="new-author-name" placeholder="' +
      esc(T("author.name_placeholder")) + '" maxlength="120"></div></div>' +
      '<div class="field-row field-row--top"><span class="field-label">' +
      esc(T("author.description")) + '</span><div class="field-body">' +
      '<textarea class="input textarea" id="new-author-desc" maxlength="2000" placeholder="' +
      esc(T("author.description_placeholder")) + '"></textarea></div></div>',
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("author.create"),
        primary: true,
        onClick: async function () {
          const input = qs("#new-author-name");
          const name = input.value.trim();
          if (!name) {
            input.classList.add("invalid");
            return;
          }
          const created = await call("create_author", name);
          if (!created) return;
          const author = (created.library.authors || []).find(function (item) {
            return item.name === name;
          });
          const description = qs("#new-author-desc").value.trim();
          let data = created;
          if (author && description) {
            data = await call("update_author", author.uid, { description: description });
          }
          closeModal();
          apply(data || created);
          if (author) selectAuthor(author.uid);
        },
      },
    ],
    onMount: function () {
      qs("#new-author-name").focus();
    },
  });
}

function confirmCleanAuthors(count) {
  openModal({
    title: T("author.clean"),
    body: '<p class="modal-note">' + esc(T("author.clean_confirm", { count: count })) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("author.clean"),
        danger: true,
        onClick: async function () {
          const data = await call("delete_empty_authors");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function cleanAuthors() {
  const all = (state.data && state.data.library.authors) || [];
  const count = all.filter(function (author) {
    return !author.count;
  }).length;
  if (!count) {
    toast(T("author.cleaned", { count: 0 }));
    return;
  }
  confirmCleanAuthors(count);
}

async function launchProgram(method) {
  const result = await call(method);
  if (!result) return;
  if (result.message) toast(result.message, result.ok === true);
}

function confirmDeleteAuthor(author) {
  const songs = songsByAuthor(author.uid);
  openModal({
    title: T("author.delete"),
    body:
      '<p class="modal-note">' + esc(T("author.delete_confirm", { name: author.name })) + "</p>" +
      dependencyMarkup(songDeps(songs)),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("author.delete"),
        danger: true,
        onClick: async function () {
          const data = await call("delete_author", author.uid, false);
          if (!data) return;
          if (data.ok) {
            closeModal();
            apply(data);
            return;
          }
          openModal({
            title: T("author.delete"),
            body:
              '<p class="modal-note">' + esc(data.message) + "</p>" +
              dependencyMarkup(songDeps(songs)),
            actions: [
              { label: T("action.cancel"), onClick: closeModal },
              {
                label: T("author.delete_force"),
                danger: true,
                onClick: async function () {
                  const forced = await call("delete_author", author.uid, true);
                  if (forced) {
                    closeModal();
                    apply(forced);
                  }
                },
              },
            ],
          });
        },
      },
    ],
  });
}

async function moveAuthor(uid, delta) {
  const data = await call("move_author", uid, delta);
  if (data) apply(data);
}
