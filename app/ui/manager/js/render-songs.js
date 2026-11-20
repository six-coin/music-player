/* 歌曲分区：列表、多选条、详情卡片。 */
/* ---------- 歌曲列表 ---------- */

function visibleMusics() {
  const musics = (state.data && state.data.library.musics) || [];
  const query = state.query.trim().toLowerCase();
  let result = musics;
  if (query) {
    const tags = tagMap();
    result = musics.filter(function (music) {
      const haystack = [music.title]
        .concat(music.names || [])
        .concat([music.authors_text || ""])
        .concat(
          (music.tags || []).map(function (uid) {
            return tags[uid] ? tags[uid].name : "";
          })
        )
        .join(" ")
        .toLowerCase();
      return haystack.indexOf(query) !== -1;
    });
  }
  return sortMusics(result);
}

function sortMusics(musics) {
  const list = musics.slice();
  if (state.sort === "attention") {
    // 缺文件最严重（放不了），其次是标签不合规；同类里再按名称。
    const weight = function (music) {
      return (music.missing ? 2 : 0) + (music.tag_issue ? 1 : 0);
    };
    list.sort(function (a, b) {
      const diff = weight(b) - weight(a);
      return diff || a.title.localeCompare(b.title, "zh-CN");
    });
  } else if (state.sort === "created") {
    list.sort(function (a, b) {
      return b.created_at - a.created_at;
    });
  } else if (state.sort === "duration") {
    list.sort(function (a, b) {
      return b.duration_ms - a.duration_ms;
    });
  } else if (state.sort === "author") {
    list.sort(function (a, b) {
      return (a.authors_text || "").localeCompare(b.authors_text || "", "zh-CN");
    });
  } else {
    list.sort(function (a, b) {
      return a.title.localeCompare(b.title, "zh-CN");
    });
  }
  return list;
}

function renderSongList() {
  const list = qs("#song-list");
  const scroll = list.scrollTop;
  const musics = visibleMusics();
  const total = (state.data && state.data.library.musics.length) || 0;

  qs("#songs-count").textContent = state.query
    ? T("songs.count_filtered", { shown: musics.length, total: total })
    : T("songs.count", { count: total });

  if (!musics.length) {
    list.innerHTML = total
      ? '<li class="row-empty">' + esc(T("songs.no_match")) + "</li>"
      : emptyList("song", T("empty.library_title"), T("songs.empty_hint"), {
          action: "import",
          label: T("action.import_first"),
        });
    return;
  }

  const html = musics.map(function (music) {
    const classes = ["song-row"];
    if (state.selection.has(music.md5)) classes.push("is-selected");
    if (state.active === music.md5) classes.push("is-active");
    if (music.missing) classes.push("is-missing");

    let dot = "";
    if (music.missing) dot = '<span class="song-dot is-missing"></span>';
    else if (music.tag_issue) dot = '<span class="song-dot"></span>';

    const sub = [music.authors_text || T("song.no_author"), formatDuration(music.duration_ms)]
      .filter(Boolean)
      .join(" · ");

    return (
      '<li class="' + classes.join(" ") + '" data-md5="' + esc(music.md5) +
      '" tabindex="' + (state.active === music.md5 ? "0" : "-1") + '">' +
      '<input class="song-check" type="checkbox" tabindex="-1"' +
      (state.selection.has(music.md5) ? " checked" : "") +
      ' aria-label="' + esc(music.title) + '">' +
      '<div class="song-body"><span class="song-title">' + esc(music.title) +
      '</span><span class="song-sub">' + esc(sub) + "</span></div>" +
      dot +
      "</li>"
    );
  });

  list.innerHTML = html.join("");
  list.scrollTop = scroll;

  const all = qs("#songs-select-all");
  const selectedVisible = musics.filter(function (music) {
    return state.selection.has(music.md5);
  }).length;
  all.checked = selectedVisible > 0 && selectedVisible === musics.length;
  all.indeterminate = selectedVisible > 0 && selectedVisible < musics.length;
}

function renderSelectionBar() {
  const bar = qs("#selection-bar");
  const count = state.selection.size;
  bar.classList.toggle("is-hidden", count === 0);
  if (count) qs("#selection-count").textContent = T("songs.selected", { count: count });
}

function syncTagGroup(box) {
  if (!box) return;
  const selected = box.querySelectorAll(".chip-toggle.is-on").length;
  const missing = box.dataset.compulsory === "1" && selected === 0;
  const conflict = box.dataset.unique === "1" && selected > 1;
  const text = missing ? T("song.missing_tag") : conflict ? T("song.tag_conflict") : "";
  box.classList.toggle("is-warn", Boolean(text));
  const hint = box.querySelector(".tag-hint");
  if (hint) {
    hint.textContent = text;
    hint.hidden = !text;
  }
}

function syncSongTagFlags() {
  const meta = qs("#song-detail .detail-meta");
  if (!meta) return;
  const flag = meta.querySelector("[data-tag-issue-flag]");
  const warn = qs("#song-detail .tag-group.is-warn");
  if (warn && !flag) {
    const node = document.createElement("span");
    node.className = "tag-flag";
    node.dataset.tagIssueFlag = "1";
    node.textContent = T("song.missing_tag");
    meta.insertBefore(node, meta.firstChild);
  } else if (!warn && flag) {
    flag.remove();
  }
}

function renderDetail() {
  const pane = qs("#song-detail");
  const music = state.activeKind === "music" && state.active ? musicByMd5(state.active) : null;

  if (!music) {
    pane.innerHTML =
      '<div class="detail-empty">' +
      '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>' +
      "</svg>" +
      "<h2>" + esc(T("song.no_selection_title")) + "</h2>" +
      "<p>" + esc(T("song.no_selection_hint")) + "</p>" +
      "</div>";
    return;
  }

  const authors = authorMap();
  const tags = tagMap();
  const authorChips = (music.authors || []).length
    ? music.authors
        .map(function (uid) {
          const name = authors[uid] ? authors[uid].name : T("common.unknown_author");
          return '<span class="chip">' + esc(name) + "</span>";
        })
        .join("")
    : '<span class="chip">' + esc(T("song.no_author")) + "</span>";

  const groups = (state.data.library.tag_groups || []).map(function (group) {
    const selected = group.tags.filter(function (tag) {
      return (music.tags || []).indexOf(tag.uid) !== -1;
    });
    const missing = group.compulsory && selected.length === 0;
    const conflict = group.unique && selected.length > 1;
    const warn = missing || conflict;
    const flags = [];
    if (group.compulsory) flags.push(T("tag.compulsory"));
    if (group.unique) flags.push(T("tag.unique"));
    const chips = group.tags
      .map(function (tag) {
        const on = selected.some(function (item) {
          return item.uid === tag.uid;
        });
        return (
          '<button class="chip-toggle' + (on ? " is-on" : "") + '" data-tag="' + esc(tag.uid) +
          '" data-on="' + (on ? "1" : "0") + '">' + esc(tag.name) + "</button>"
        );
      })
      .join("");
    const hint = missing ? T("song.missing_tag") : conflict ? T("song.tag_conflict") : "";
    return (
      '<div class="tag-group' + (warn ? " is-warn" : "") + '" data-tag-group-box="' +
      esc(group.uid) + '" data-compulsory="' + (group.compulsory ? "1" : "0") +
      '" data-unique="' + (group.unique ? "1" : "0") + '">' +
      '<div class="tag-group-head"><span>' + esc(group.name) + "</span>" +
      '<span class="tag-flag">' + esc(flags.join(" · ")) + "</span></div>" +
      '<div class="chips">' + chips + "</div>" +
      '<p class="tag-hint"' + (warn ? "" : " hidden") + ">" + esc(hint) + "</p>" +
      "</div>"
    );
  });

  const aliasCount = Math.max(0, (music.names || []).length - 1);
  const flags = [];
  if (music.missing) flags.push('<span class="tag-flag">' + esc(T("song.missing_file")) + "</span>");
  if (music.tag_issue) {
    flags.push(
      '<span class="tag-flag" data-tag-issue-flag="1">' + esc(T("song.missing_tag")) + "</span>"
    );
  }

  pane.innerHTML =
    '<header class="detail-head">' +
    '<div class="detail-title"><h2>' + esc(music.title) + "</h2>" +
    '<div class="detail-meta">' +
    "<span>" + esc(music.authors_text || T("song.no_author")) + "</span>" +
    "<span>·</span><span>" + formatDuration(music.duration_ms) + "</span>" +
    "<span>·</span><span>" + formatSize(music.size) + "</span>" +
    "<span>·</span><span>" + formatDate(music.created_at) + "</span>" +
    flags.join("") +
    "</div></div>" +
    '<div class="detail-tools"><button class="btn ghost" data-menu="song">' +
    esc(T("action.more")) + "</button></div>" +
    "</header>" +

    '<section class="card"><h3 class="card-title">' + esc(T("song.basic")) + "</h3>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.name")) + "</span>" +
    '<div class="field-body"><input class="input" id="song-name" value="' +
    esc(music.title) + '" maxlength="200"></div></div>' +
    '<div class="field-row"><span class="field-label">' + esc(T("song.authors")) + "</span>" +
    '<div class="field-body"><div class="chips" id="author-chips">' + authorChips + "</div>" +
    '<button class="btn soft small" id="btn-authors" style="margin-top:8px">' +
    esc(T("action.edit")) + "</button></div></div>" +
    '<div class="field-row field-row--top"><span class="field-label">' + esc(T("song.tags")) + "</span>" +
    '<div class="field-body">' + (groups.length ? groups.join("") : '<p class="tag-hint">' +
      esc(T("batch.no_tags")) + "</p>") + "</div></div>" +
    "</section>" +

    '<section class="card"><h3 class="card-title">' + esc(T("song.file")) + "</h3>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.md5")) + "</span>" +
    '<div class="field-body file-line"><span class="mono">' + esc(music.md5) + "</span>" +
    '<button class="btn soft small" data-copy="' + esc(music.md5) + '">' +
    esc(T("action.copy")) + "</button></div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.path")) + "</span>" +
    '<div class="field-body file-line"><span class="mono">music\\' +
    esc(music.md5 + "." + music.ext) + "</span></div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.size")) + "</span>" +
    '<div class="field-body">' + formatSize(music.size) + "</div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.duration")) + "</span>" +
    '<div class="field-body">' + formatDuration(music.duration_ms) + "</div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.imported_at")) + "</span>" +
    '<div class="field-body">' + formatDate(music.created_at) + "</div></div>" +
    "</section>" +

    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("adaptation.title")) + '</h3><span class="detail-hint" id="music-adapt-source"></span>' +
    '</div><div class="adapt-inline" id="music-adapt">' + esc(T("adaptation.loading")) +
    '</div><p class="detail-hint">' + esc(T("adaptation.song_scope_hint")) + "</p></section>" +

    '<p class="modal-note" style="margin-top:4px">' +
    esc(T("song.alias_count", { count: aliasCount })) + "</p>";
}

function renderSongs() {
  renderSongList();
  renderSelectionBar();
  renderDetail();
  const music = state.activeKind === "music" && state.active ? musicByMd5(state.active) : null;
  if (music) loadMusicStats(music.md5);
}
