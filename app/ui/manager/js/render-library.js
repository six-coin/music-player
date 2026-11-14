/* 标签与作者分区：列表与详情。 */
/* ---------- 标签 ---------- */

function tagGroupByUid(uid) {
  return (
    ((state.data && state.data.library.tag_groups) || []).find(function (item) {
      return item.uid === uid;
    }) || null
  );
}

function visibleTagGroups() {
  const list = (state.data && state.data.library.tag_groups) || [];
  const query = state.tagQuery.trim().toLowerCase();
  if (!query) return list;
  return list.filter(function (group) {
    if (group.name.toLowerCase().indexOf(query) !== -1) return true;
    return (group.tags || []).some(function (tag) {
      return tag.name.toLowerCase().indexOf(query) !== -1;
    });
  });
}

function tagFlags(group) {
  const flags = [];
  if (group.compulsory) flags.push(T("tag.compulsory"));
  if (group.unique) flags.push(T("tag.unique"));
  return flags;
}

function renderTagList() {
  const list = qs("#tag-list");
  const total = ((state.data && state.data.library.tag_groups) || []).length;
  const items = visibleTagGroups();
  qs("#tags-count").textContent = T("tag.total", { count: total });

  if (!items.length) {
    list.innerHTML = total
      ? '<li class="row-empty">' + esc(T("tag.no_match")) + "</li>"
      : emptyList("tag", T("tag.empty"), T("tag.empty_hint"), {
          action: "new_tag_group",
          label: T("tag.new_group"),
        });
    return;
  }

  list.innerHTML = items
    .map(function (group) {
      const classes = ["song-row"];
      if (state.activeKind === "tag_group" && state.active === group.uid) {
        classes.push("is-active");
      }
      const flags = tagFlags(group);
      const sub =
        T("tag.group_summary", { tags: (group.tags || []).length, songs: group.count || 0 }) +
        (flags.length ? " · " + flags.join(" / ") : "");
      return (
        '<li class="' + classes.join(" ") + '" data-tag-group="' + esc(group.uid) +
        '" tabindex="0"><div class="song-body"><span class="song-title">' + esc(group.name) +
        '</span><span class="song-sub">' + esc(sub) + "</span></div></li>"
      );
    })
    .join("");
}

function renderTagDetail() {
  const pane = qs("#tag-detail");
  const group =
    state.activeKind === "tag_group" && state.active ? tagGroupByUid(state.active) : null;

  if (!group) {
    pane.innerHTML =
      '<div class="detail-empty">' +
      '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M20.59 13.41 12 22 2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z"/>' +
      '<circle cx="7" cy="7" r="1.5"/></svg>' +
      "<h2>" + esc(T("tag.no_selection_title")) + "</h2>" +
      "<p>" + esc(T("tag.no_selection_hint")) + "</p></div>";
    return;
  }

  const tags = (group.tags || []).slice().sort(function (a, b) {
    return a.name.localeCompare(b.name, "zh-CN");
  });

  const rows = tags.length
    ? tags
        .map(function (tag) {
          return (
            '<div class="tag-edit-row">' +
            '<input class="input" data-tag-name="' + esc(tag.uid) + '" data-tag-original="' +
            esc(tag.name) + '" value="' + esc(tag.name) + '" maxlength="60">' +
            '<span class="tag-count">' + esc(T("tag.usage", { count: tag.count || 0 })) + "</span>" +
            '<button class="icon-btn" type="button" data-tag-remove="' + esc(tag.uid) +
            '" aria-label="' + esc(T("action.remove")) + '">×</button></div>'
          );
        })
        .join("")
    : '<p class="tag-hint">' + esc(T("tag.empty")) + "</p>";

  const flags = tagFlags(group);
  const badge = flags.length
    ? '<span class="badge">' + esc(flags.join(" / ")) + "</span>"
    : "";

  pane.innerHTML =
    '<header class="detail-head"><div class="detail-title"><h2>' + esc(group.name) +
    '</h2><div class="detail-meta">' + badge +
    "<span>" + esc(T("tag.group_summary", { tags: tags.length, songs: group.count || 0 })) +
    "</span></div></div>" +
    '<div class="detail-tools"><button class="btn ghost" data-menu="tag">' +
    esc(T("action.more")) + "</button></div></header>" +

    '<section class="card"><h3 class="card-title">' + esc(T("common.basic")) + "</h3>" +
    '<div class="field-row"><span class="field-label">' + esc(T("tag.name")) + "</span>" +
    '<div class="field-body"><input class="input" id="tag-group-name" value="' +
    esc(group.name) + '" maxlength="60"></div></div>' +
    '<div class="toggle-row"><div class="toggle-body">' +
    '<div class="toggle-title">' + esc(T("tag.compulsory")) + "</div>" +
    '<p class="toggle-hint">' + esc(T("tag.compulsory_hint")) + "</p></div>" +
    '<button class="switch" type="button" role="switch" data-switch="compulsory" aria-checked="' +
    (group.compulsory ? "true" : "false") + '"><span class="switch-knob"></span></button></div>' +
    '<div class="toggle-row"><div class="toggle-body">' +
    '<div class="toggle-title">' + esc(T("tag.unique")) + "</div>" +
    '<p class="toggle-hint">' + esc(T("tag.unique_hint")) + "</p></div>" +
    '<button class="switch" type="button" role="switch" data-switch="unique" aria-checked="' +
    (group.unique ? "true" : "false") + '"><span class="switch-knob"></span></button></div>' +
    "</section>" +

    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("tag.tags")) + '</h3><span class="detail-hint">' +
    esc(T("tag.usage", { count: group.count || 0 })) + "</span></div>" +
    rows +
    '<form class="inline-form" id="tag-add-form">' +
    '<input class="input" id="tag-new" maxlength="60" placeholder="' +
    esc(T("tag.add_placeholder")) + '">' +
    '<button class="btn primary small" type="submit">' + esc(T("action.add")) + "</button>" +
    "</form></section>";
}

function renderTags() {
  renderTagList();
  renderTagDetail();
}
/* ---------- 作者 ---------- */

function authorByUid(uid) {
  return (
    ((state.data && state.data.library.authors) || []).find(function (item) {
      return item.uid === uid;
    }) || null
  );
}

function visibleAuthors() {
  const list = (state.data && state.data.library.authors) || [];
  const query = state.authorQuery.trim().toLowerCase();
  if (!query) return list;
  return list.filter(function (author) {
    return author.name.toLowerCase().indexOf(query) !== -1;
  });
}

function renderAuthorList() {
  const list = qs("#author-list");
  const all = (state.data && state.data.library.authors) || [];
  const total = all.length;
  const items = visibleAuthors();
  qs("#authors-count").textContent = T("author.total", { count: total });

  const emptyCount = all.filter(function (author) {
    return !author.count;
  }).length;
  const tools = qs("#author-tools");
  if (tools) {
    tools.hidden = emptyCount === 0;
    qs("#author-empty-count").textContent = emptyCount
      ? T("author.empty_count", { count: emptyCount })
      : "";
  }

  if (!items.length) {
    list.innerHTML = total
      ? '<li class="row-empty">' + esc(T("author.no_match")) + "</li>"
      : emptyList("author", T("author.empty"), T("author.empty_hint"), {
          action: "new_author",
          label: T("author.new"),
        });
    return;
  }

  list.innerHTML = items
    .map(function (author) {
      const classes = ["song-row", "author-row"];
      if (state.activeKind === "author" && state.active === author.uid) {
        classes.push("is-active");
      }
      return (
        '<li class="' + classes.join(" ") + '" draggable="true" data-author-uid="' +
        esc(author.uid) + '" tabindex="0"><div class="song-body"><span class="song-title">' +
        esc(author.name) + '</span><span class="song-sub">' +
        esc(T("author.count", { count: author.count || 0 })) + "</span></div></li>"
      );
    })
    .join("");
}

function renderAuthorDetail() {
  const pane = qs("#author-detail");
  const author = state.activeKind === "author" && state.active ? authorByUid(state.active) : null;

  if (!author) {
    pane.innerHTML =
      '<div class="detail-empty">' +
      '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
      "<h2>" + esc(T("author.no_selection_title")) + "</h2>" +
      "<p>" + esc(T("author.no_selection_hint")) + "</p></div>";
    return;
  }

  const songs = ((state.data && state.data.library.musics) || []).filter(function (music) {
    return (music.authors || []).indexOf(author.uid) !== -1;
  });
  const rows = songs.length
    ? songs
        .map(function (music) {
          return (
            '<li class="entry-row" data-author-song="' + esc(music.md5) + '" tabindex="0">' +
            '<div class="entry-body"><span class="entry-title">' + esc(music.title) +
            '</span><span class="entry-sub">' + formatDuration(music.duration_ms) +
            "</span></div></li>"
          );
        })
        .join("")
    : '<li class="row-empty">' + esc(T("author.songs_empty")) + "</li>";

  pane.innerHTML =
    '<header class="detail-head"><div class="detail-title"><h2>' + esc(author.name) +
    '</h2><div class="detail-meta"><span>' +
    esc(T("author.count", { count: songs.length })) + "</span></div></div>" +
    '<div class="detail-tools"><button class="btn ghost" data-menu="author">' +
    esc(T("action.more")) + "</button></div></header>" +

    '<section class="card"><h3 class="card-title">' + esc(T("common.basic")) + "</h3>" +
    '<div class="field-row"><span class="field-label">' + esc(T("author.name")) + "</span>" +
    '<div class="field-body"><input class="input" id="author-name" value="' +
    esc(author.name) + '" maxlength="120"></div></div>' +
    '<div class="field-row field-row--top"><span class="field-label">' +
    esc(T("author.description")) + "</span>" +
    '<div class="field-body"><textarea class="input textarea" id="author-description" ' +
    'maxlength="2000" placeholder="' + esc(T("author.description_placeholder")) + '">' +
    esc(author.description || "") + "</textarea></div></div></section>" +

    '<section class="card card--list card--works"><div class="card-tools"><h3 class="card-title">' +
    esc(T("author.songs")) + '</h3><span class="detail-hint">' +
    esc(T("author.count", { count: songs.length })) + "</span></div>" +
    '<ul class="entry-list entry-list--works">' + rows + "</ul></section>";
}

function renderAuthors() {
  renderAuthorList();
  renderAuthorDetail();
}
