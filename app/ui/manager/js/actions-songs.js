/* 歌曲的编辑动作：改名、作者、别名、批量、换源、删除、试听。 */
/* ---------- 名称编辑（防抖） ---------- */

function scheduleNameSave(input) {
  if (!state.active) return;
  input.classList.remove("invalid");
  window.clearTimeout(state.nameTimer);
  const md5 = state.active;
  state.nameTimer = window.setTimeout(function () {
    state.nameTimer = null;
    saveName(md5, input.value);
  }, 420);
}

async function saveName(md5, value) {
  const result = await call("update_music_name", md5, value);
  const input = qs("#song-name");
  if (!result || !result.ok) {
    if (input) input.classList.add("invalid");
    return;
  }
  const music = musicByMd5(md5);
  if (music) {
    music.title = value.trim();
    if (music.names.length) music.names[0] = music.title;
    else music.names = [music.title];
  }
  const row = qs('.song-row[data-md5="' + md5 + '"] .song-title');
  if (row) row.textContent = value.trim();
}

async function flushNameSave() {
  if (!state.nameTimer) return;
  window.clearTimeout(state.nameTimer);
  state.nameTimer = null;
  const input = qs("#song-name");
  if (input && state.active) await saveName(state.active, input.value);
}
/* ---------- 试听 ---------- */

function auditionAudio() {
  return qs("#audition-audio");
}

async function auditionPlay(md5) {
  const info = await call("audition_url", md5);
  if (!info || !info.ok) {
    toast((info && info.message) || T("audition.failed"), false);
    return;
  }

  const audio = auditionAudio();
  if (state.auditionMd5 !== md5) {
    audio.src = info.url;
    state.auditionMd5 = md5;
    qs("#audition-title").textContent = info.title || "";
    qs("#audition-total").textContent = formatDuration(info.duration_ms);
    qs("#audition-seek").value = "0";
    qs("#audition-current").textContent = "0:00";
  }

  const configured = Number(settingValue("audition.volume"));
  audio.volume = Number.isFinite(configured) ? Math.min(1, Math.max(0, configured)) : 0.2;
  const volumePercent = Math.round(audio.volume * 100);
  qs("#audition-volume").value = String(volumePercent);
  qs("#audition-volume-value").textContent = volumePercent + "%";

  qs("#audition").hidden = false;
  qs("#app").classList.add("has-audition");
  const started = audio.play();
  if (started && started.catch) {
    started.catch(function () {
      toast(T("audition.failed"), false);
    });
  }
}

function auditionStop() {
  const audio = auditionAudio();
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  state.auditionMd5 = null;
  qs("#audition").hidden = true;
  qs("#audition-toggle").dataset.playing = "false";
  qs("#app").classList.remove("has-audition");
}

function syncAudition() {
  const audio = auditionAudio();
  const playing = Boolean(audio.src) && !audio.paused && !audio.ended;
  const toggle = qs("#audition-toggle");
  toggle.dataset.playing = playing ? "true" : "false";
  toggle.setAttribute("aria-label", playing ? T("audition.pause") : T("audition.play"));

  const duration = audio.duration;
  if (Number.isFinite(duration) && duration > 0) {
    qs("#audition-seek").value = String(Math.round((audio.currentTime / duration) * 1000));
    qs("#audition-current").textContent = formatDuration(audio.currentTime * 1000);
    qs("#audition-total").textContent = formatDuration(duration * 1000);
  }
}
/* ---------- 作者选择 ---------- */

function openAuthorPicker(music) {
  const selected = (music.authors || []).slice();

  const body =
    '<div class="pick">' +
    '<div class="pick-col"><span class="pick-title">' + esc(T("author.available")) + "</span>" +
    '<input class="input" id="pick-search" placeholder="' + esc(T("author.search")) + '">' +
    '<ul class="pick-list" id="pick-available"></ul></div>' +
    '<div class="pick-col"><span class="pick-title">' + esc(T("author.selected")) + "</span>" +
    '<ul class="pick-list" id="pick-selected"></ul></div>' +
    "</div>" +
    '<div class="inline-form" style="margin-top:12px">' +
    '<input class="input" id="author-new" placeholder="' + esc(T("author.new_placeholder")) + '">' +
    '<button class="btn" id="author-create">' + esc(T("action.add")) + "</button></div>";

  openModal({
    title: T("author.picker_title"),
    body: body,
    wide: true,
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("action.done"),
        primary: true,
        onClick: async function () {
          const data = await call("set_music_authors", music.md5, selected);
          closeModal();
          if (data) apply(data);
        },
      },
    ],
    onMount: function () {
      renderPickLists();
      qs("#pick-search").addEventListener("input", filterPick);
    },
  });

  function filterPick() {
    const query = qs("#pick-search").value.trim().toLowerCase();
    qsa("#pick-available .pick-row").forEach(function (row) {
      row.hidden = query && row.dataset.name.indexOf(query) === -1;
    });
  }

  function renderPickLists() {
    // 与作者分区同一个顺序：按名称，中文按拼音。
    const authors = sortedAuthors();
    const available = authors.filter(function (author) {
      return selected.indexOf(author.uid) === -1;
    });
    const availableList = qs("#pick-available");
    availableList.innerHTML = available.length
      ? available
          .map(function (author) {
            return (
              '<li class="pick-row" data-pick-add="' + esc(author.uid) + '" data-name="' +
              esc(author.name.toLowerCase()) + '">' + esc(author.name) + "</li>"
            );
          })
          .join("")
      : '<li class="row-empty">' + esc(T("author.empty")) + "</li>";

    const selectedList = qs("#pick-selected");
    selectedList.innerHTML = selected.length
      ? selected
          .map(function (uid, index) {
            const author = authors.find(function (item) {
              return item.uid === uid;
            });
            const name = author ? author.name : T("common.unknown_author");
            return (
              '<li class="pick-row is-on"><span class="pick-row-body">' + esc(name) + "</span>" +
              '<span class="pick-row-tools">' +
              '<button class="icon-btn" data-pick-up="' + index + '" aria-label="' +
              esc(T("action.up")) + '">↑</button>' +
              '<button class="icon-btn" data-pick-down="' + index + '" aria-label="' +
              esc(T("action.down")) + '">↓</button>' +
              '<button class="icon-btn" data-pick-remove="' + index + '" aria-label="' +
              esc(T("action.remove")) + '">×</button></span></li>'
            );
          })
          .join("")
      : '<li class="row-empty">' + esc(T("author.selected_empty")) + "</li>";

    filterPick();
  }

  qs("#modal-body").onclick = async function (event) {
    const add = event.target.closest("[data-pick-add]");
    if (add) {
      selected.push(add.dataset.pickAdd);
      renderPickLists();
      return;
    }
    const remove = event.target.closest("[data-pick-remove]");
    if (remove) {
      selected.splice(Number(remove.dataset.pickRemove), 1);
      renderPickLists();
      return;
    }
    const up = event.target.closest("[data-pick-up]");
    if (up) {
      const index = Number(up.dataset.pickUp);
      if (index > 0) {
        const item = selected.splice(index, 1)[0];
        selected.splice(index - 1, 0, item);
        renderPickLists();
      }
      return;
    }
    const down = event.target.closest("[data-pick-down]");
    if (down) {
      const index = Number(down.dataset.pickDown);
      if (index < selected.length - 1) {
        const item = selected.splice(index, 1)[0];
        selected.splice(index + 1, 0, item);
        renderPickLists();
      }
      return;
    }
    if (event.target.closest("#author-create")) {
      const input = qs("#author-new");
      const name = input.value.trim();
      if (!name) return;
      const data = await call("create_author", name);
      if (data) {
        apply(data);
        const author = data.library.authors.find(function (item) {
          return item.name === name;
        });
        if (author && selected.indexOf(author.uid) === -1) selected.push(author.uid);
        renderPickLists();
        input.value = "";
      }
    }
  };
}
/* ---------- 别名 ---------- */

function openAliasEditor(music) {
  openModal({
    title: T("alias.title"),
    body:
      '<p class="modal-note">' + esc(T("song.alias_hint")) + "</p>" +
      '<div class="inline-form"><input class="input" id="alias-new" placeholder="' +
      esc(T("alias.placeholder")) + '"><button class="btn" id="alias-add">' +
      esc(T("action.add")) + "</button></div>" +
      '<div id="alias-list"></div>',
    actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
    onMount: function () {
      renderAliases();
      qs("#modal-body").onclick = onAliasClick;
      qs("#alias-new").addEventListener("keydown", function (event) {
        if (event.key === "Enter") addAlias();
      });
    },
  });

  function renderAliases() {
    const current = musicByMd5(music.md5);
    const aliases = current ? current.names.slice(1) : [];
    const list = qs("#alias-list");
    list.innerHTML = aliases.length
      ? aliases
          .map(function (name, index) {
            return (
              '<div class="alias-row"><span class="alias-name">' + esc(name) + "</span>" +
              '<button class="icon-btn" data-alias-up="' + index + '" aria-label="' +
              esc(T("action.up")) + '">↑</button>' +
              '<button class="icon-btn" data-alias-down="' + index + '" aria-label="' +
              esc(T("action.down")) + '">↓</button>' +
              '<button class="icon-btn" data-alias-remove="' + index + '" aria-label="' +
              esc(T("action.remove")) + '">×</button></div>'
            );
          })
          .join("")
      : '<p class="row-empty">' + esc(T("alias.empty")) + "</p>";
  }

  async function addAlias() {
    const input = qs("#alias-new");
    const name = input.value.trim();
    if (!name) return;
    const data = await call("add_alias", music.md5, name);
    input.value = "";
    if (data) {
      apply(data);
      renderAliases();
    }
  }

  async function onAliasClick(event) {
    const remove = event.target.closest("[data-alias-remove]");
    const up = event.target.closest("[data-alias-up]");
    const down = event.target.closest("[data-alias-down]");
    if (event.target.closest("#alias-add")) {
      await addAlias();
      return;
    }
    let data = null;
    if (remove) data = await call("remove_alias", music.md5, Number(remove.dataset.aliasRemove));
    else if (up) data = await call("move_alias", music.md5, Number(up.dataset.aliasUp), -1);
    else if (down) data = await call("move_alias", music.md5, Number(down.dataset.aliasDown), 1);
    if (data) {
      apply(data);
      renderAliases();
    }
  }
}
/* ---------- 批量操作 ---------- */

function openBatchTags() {
  const md5s = Array.from(state.selection);
  if (!md5s.length) return;
  const chosen = new Set();

  const groups = state.data.library.tag_groups || [];
  const body =
    '<p class="modal-note">' + esc(T("batch.tags_note", { count: md5s.length })) + "</p>" +
    (groups.length
      ? groups
          .map(function (group) {
            const chips = group.tags
              .map(function (tag) {
                return (
                  '<button class="chip-toggle" data-batch-tag="' + esc(tag.uid) + '">' +
                  esc(tag.name) + "</button>"
                );
              })
              .join("");
            return (
              '<div class="tag-group"><div class="tag-group-head"><span>' + esc(group.name) +
              '</span></div><div class="chips">' + chips + "</div></div>"
            );
          })
          .join("")
      : '<p class="row-empty">' + esc(T("batch.no_tags")) + "</p>") +
    '<label class="check" style="margin-top:12px"><input type="checkbox" id="batch-clear">' +
    "<span>" + esc(T("batch.clear_groups")) + "</span></label>";

  openModal({
    title: T("batch.tags_title"),
    body: body,
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("action.apply"),
        primary: true,
        onClick: async function () {
          const clear = qs("#batch-clear").checked;
          const data = await call("batch_add_tags", md5s, Array.from(chosen), clear);
          closeModal();
          if (data) apply(data);
        },
      },
    ],
    onMount: function () {
      qs("#modal-body").onclick = function (event) {
        const chip = event.target.closest("[data-batch-tag]");
        if (!chip) return;
        const uid = chip.dataset.batchTag;
        if (chosen.has(uid)) chosen.delete(uid);
        else chosen.add(uid);
        chip.classList.toggle("is-on", chosen.has(uid));
      };
    },
  });
}

function openBatchPlaylist() {
  const md5s = Array.from(state.selection);
  if (!md5s.length) return;
  const manuals = (state.data.playlists || []).filter(function (playlist) {
    return playlist.kind === "manual";
  });

  const body = manuals.length
    ? '<ul class="pick-list">' + manuals
        .map(function (playlist) {
          return (
            '<li class="pick-row" data-playlist="' + esc(playlist.uid) + '">' +
            '<span class="pick-row-body">' + esc(playlist.title) + "</span>" +
            '<span class="pick-row-tools">' + playlist.count + "</span></li>"
          );
        })
        .join("") + "</ul>"
    : '<p class="row-empty">' + esc(T("batch.no_playlists")) + "</p>";

  let picked = null;
  openModal({
    title: T("batch.playlist_title"),
    body: body,
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("action.apply"),
        primary: true,
        onClick: async function () {
          if (!picked) {
            toast(T("batch.pick_playlist"), false);
            return;
          }
          const data = await call("batch_add_to_playlist", md5s, picked);
          closeModal();
          if (data) apply(data);
        },
      },
    ],
    onMount: function () {
      qs("#modal-body").onclick = function (event) {
        const row = event.target.closest("[data-playlist]");
        if (!row) return;
        picked = row.dataset.playlist;
        qsa("[data-playlist]").forEach(function (node) {
          node.classList.toggle("is-on", node === row);
        });
      };
    },
  });
}
/* ---------- 换源与删除 ---------- */

async function replaceSource(music) {
  const picked = await call("browse_audio");
  if (!picked || !picked.path) return;
  const started = await call("start_replace_source", music.md5, picked.path);
  if (!started || !started.task_id) return;
  openReplaceModal(started.task_id, music);
}

function openReplaceModal(taskId, music) {
  openModal({
    title: T("song.replace_title"),
    body:
      '<p class="progress-text" id="replace-line">' + esc(T("song.replace_running")) + "</p>" +
      '<div class="progress"><div class="progress-bar is-indeterminate" id="replace-bar"></div></div>' +
      '<div id="replace-report"></div>',
    dismissible: false,
    actions: [],
  });

  async function poll() {
    const task = await call("poll_task", taskId);
    if (!task) return;
    if (task.state === "running") {
      window.setTimeout(poll, 300);
      return;
    }

    const line = qs("#replace-line");
    const bar = qs("#replace-bar");
    if (bar) {
      bar.classList.remove("is-indeterminate");
      bar.style.width = "100%";
    }

    if (task.state === "failed" || (task.errors && task.errors.length)) {
      line.textContent = T("song.replace_failed");
      const note = document.createElement("p");
      note.className = "modal-note";
      note.textContent = (task.errors || []).join("；");
      qs("#replace-report").appendChild(note);
    } else {
      const report = task.result || {};
      line.textContent = T("song.replace_done");
      const body = document.createElement("div");
      body.innerHTML =
        '<p class="modal-note">' + esc(report.title || music.title) + "</p>" +
        '<ul class="report-list">' +
        "<li>" +
        esc(
          T("song.replace_report", {
            playlists: report.playlists || 0,
            stats: report.stats || 0,
          })
        ) +
        "</li><li>" +
        esc(report.recycled ? T("song.replace_recycled") : T("song.replace_recycled_no")) +
        "</li></ul>";
      qs("#replace-report").appendChild(body);
      const data = await call("get_state");
      if (data) apply(data);
    }

    const actions = qs("#modal-actions");
    const button = document.createElement("button");
    button.className = "btn primary";
    button.textContent = T("action.close");
    button.addEventListener("click", closeModal);
    actions.appendChild(button);
    modalDismissible = true;
    qs("#modal-close").hidden = false;
  }

  poll();
}

/* 导出：后端弹目录选择框，把原文件按「歌名 - 作者.后缀」复制过去。 */
async function exportSongs(md5s) {
  const list = (md5s || []).filter(function (md5) {
    return Boolean(musicByMd5(md5));
  });
  if (!list.length) return;
  const result = await call("export_musics", list);
  if (!result || result.canceled) return;
  if (result.ok === false) {
    toast(result.message || T("export.failed"), false);
    return;
  }
  if (result.errors && result.errors.length) {
    console.warn("导出时跳过的文件：", result.errors);
    toast(
      T("export.partial", { count: result.exported, failed: result.errors.length }),
      false
    );
    return;
  }
  toast(T("export.done", { count: result.exported, folder: result.folder }), true);
}

function confirmDeleteSongs(md5s) {
  const list = (md5s || []).filter(function (md5) {
    return Boolean(musicByMd5(md5));
  });
  if (!list.length) return;
  const one = list.length === 1 ? musicByMd5(list[0]) : null;
  const text = one
    ? T("song.delete_confirm", { title: one.title })
    : T("song.delete_batch_confirm", { count: list.length });

  // 歌曲的从属关系是「在哪些歌单里」：删掉之后这些歌单会各少一首。
  const playlists = [];
  const seen = new Set();
  list.forEach(function (md5) {
    playlistsWithSong(md5).forEach(function (playlist) {
      if (seen.has(playlist.uid)) return;
      seen.add(playlist.uid);
      playlists.push(playlist);
    });
  });

  openModal({
    title: one ? T("song.delete") : T("song.delete_batch", { count: list.length }),
    body:
      '<p class="modal-note">' + esc(text) + "</p>" + dependencyMarkup(playlistDeps(playlists)),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("song.delete"),
        danger: true,
        onClick: async function () {
          const data = await call("delete_musics", list);
          if (!data) return;
          state.selection.clear();
          closeModal();
          apply(data);
        },
      },
    ],
  });
}
