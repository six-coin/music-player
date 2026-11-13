/* 管理器的前端。没有框架、没有构建步骤：拉一次文案与快照，整体重绘。 */

const state = {
  data: null,
  strings: {},
  tab: "imported",
  sort: "title",
  query: "",
  playlistQuery: "",
  active: null,
  activeKind: null,
  serverSelection: null,
  serverKind: null,
  selection: new Set(),
  anchor: null,
  taskId: null,
  nameTimer: null,
  playlistNameTimer: null,
  dragMd5: null,
};

function qs(selector, root) {
  return (root || document).querySelector(selector);
}

function qsa(selector, root) {
  return Array.prototype.slice.call((root || document).querySelectorAll(selector));
}

function esc(text) {
  return String(text === undefined || text === null ? "" : text).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

/* ---------- 桥接 ---------- */

function bridge() {
  return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

async function call(method) {
  const api = bridge();
  if (!api) return null;
  const args = Array.prototype.slice.call(arguments, 1);
  try {
    return await api[method].apply(api, args);
  } catch (error) {
    console.error(method, error);
    toast(String(error), false);
    return null;
  }
}

/* ---------- 文案 ---------- */

function T(key, values) {
  let template = state.strings[key];
  if (template === undefined) return key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, function (match, name) {
    return Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match;
  });
}

async function loadStrings() {
  const table = await call("get_strings");
  state.strings = table || {};
}

function applyStrings() {
  qsa("[data-i18n]").forEach(function (node) {
    node.textContent = T(node.dataset.i18n);
  });
  qsa("[data-i18n-placeholder]").forEach(function (node) {
    node.setAttribute("placeholder", T(node.dataset.i18nPlaceholder));
  });
  qsa("[data-i18n-title]").forEach(function (node) {
    node.setAttribute("title", T(node.dataset.i18nTitle));
  });
}

/* ---------- 格式化 ---------- */

function pad(value) {
  return value < 10 ? "0" + value : String(value);
}

function formatDuration(ms) {
  const total = Math.max(0, Math.round((ms || 0) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return hours > 0 ? hours + ":" + pad(minutes) + ":" + pad(seconds) : minutes + ":" + pad(seconds);
}

function formatSize(bytes) {
  const value = Math.max(0, bytes || 0);
  if (value < 1024) return value + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 100 || index === 0 ? 0 : 1;
  return size.toFixed(digits) + " " + units[index];
}

function formatDate(seconds) {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  return date.getFullYear() + "/" + pad(date.getMonth() + 1) + "/" + pad(date.getDate());
}

function formatTime(at, now) {
  if (!at) return "";
  const diff = Math.max(0, (now || Math.floor(Date.now() / 1000)) - at);
  if (diff < 60) return T("time.just_now");
  if (diff < 3600) return T("time.minutes_ago", { count: Math.floor(diff / 60) });
  if (diff < 86400) return T("time.hours_ago", { count: Math.floor(diff / 3600) });
  if (diff < 86400 * 7) return T("time.days_ago", { count: Math.floor(diff / 86400) });
  return formatDate(at);
}

/* ---------- 数据索引 ---------- */

function musicByMd5(md5) {
  if (!state.data) return null;
  return state.data.library.musics.find(function (item) {
    return item.md5 === md5;
  }) || null;
}

function authorMap() {
  const map = {};
  ((state.data && state.data.library.authors) || []).forEach(function (author) {
    map[author.uid] = author;
  });
  return map;
}

function tagMap() {
  const map = {};
  ((state.data && state.data.library.tag_groups) || []).forEach(function (group) {
    group.tags.forEach(function (tag) {
      map[tag.uid] = { name: tag.name, group: group };
    });
  });
  return map;
}

/* ---------- 渲染 ---------- */

function applyTheme(theme) {
  if (!theme) return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem("theme", theme);
  } catch (error) {
    /* 隐私模式下写不了，忽略 */
  }
}

function showView(name) {
  qsa("[data-view]").forEach(function (view) {
    view.classList.toggle("is-hidden", view.dataset.view !== name);
  });
}

function applyNav(section) {
  qsa(".rail-item").forEach(function (item) {
    item.classList.toggle("is-active", item.dataset.section === section);
  });
  if (section === "overview") showView("overview");
  else if (section === "songs") showView("songs");
  else if (section === "playlists") showView("playlists");
  else showView("pending");
  if (section !== "overview" && section !== "songs" && section !== "playlists") {
    qs("#pending-title").textContent = T("nav." + section);
  }
}

function renderSummary(data) {
  const counts = data.counts || {};
  qs("#summary").textContent = T("overview.summary", {
    songs: counts.musics || 0,
    playlists: counts.playlists || 0,
    authors: counts.authors || 0,
  });
}

function renderStats(data) {
  const counts = data.counts || {};
  const values = {
    musics: String(counts.musics || 0),
    duration: formatDuration(counts.total_duration_ms),
    size: formatSize(counts.total_size),
    playlists: String(counts.playlists || 0),
    authors: String(counts.authors || 0),
    tag_groups: String(counts.tag_groups || 0),
  };
  qsa("[data-stat]").forEach(function (node) {
    const key = node.dataset.stat;
    node.textContent = values[key] !== undefined ? values[key] : "0";
  });
}

function renderRecent(data) {
  const list = qs("#recent");
  const overview = data.overview || {};
  const source = state.tab === "edited" ? overview.recent_edited : overview.recent_imported;
  const items = source || [];
  const now = overview.generated_at;

  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<li class="row-empty">' + esc(T("overview.recent_empty")) + "</li>";
    return;
  }

  items.forEach(function (item) {
    const row = document.createElement("li");
    row.className = "row is-clickable";
    if (item.kind === "music") row.dataset.md5 = item.md5;

    const body = document.createElement("div");
    body.className = "row-body";
    const title = document.createElement("span");
    title.className = "row-title";
    title.textContent = item.title || "";
    body.appendChild(title);
    if (item.subtitle) {
      const sub = document.createElement("span");
      sub.className = "row-sub";
      sub.textContent = item.subtitle;
      body.appendChild(sub);
    }

    const time = document.createElement("span");
    time.className = "row-time";
    time.textContent = formatTime(item.at, now);

    row.appendChild(body);
    row.appendChild(time);
    list.appendChild(row);
  });
}

function renderIssues(data) {
  const list = qs("#issues");
  const issues = (data.overview && data.overview.issues) || [];
  list.innerHTML = "";

  if (!issues.length) {
    list.innerHTML = '<li class="row-empty">' + esc(T("overview.issues_clear")) + "</li>";
    return;
  }

  issues.forEach(function (issue) {
    const row = document.createElement("li");
    row.className = "row is-clickable";
    row.dataset.issue = issue.kind;

    const mark = document.createElement("span");
    mark.className = "row-mark";

    const body = document.createElement("div");
    body.className = "row-body";
    const title = document.createElement("span");
    title.className = "row-title";
    title.textContent = T("overview.issue_" + issue.kind, { count: issue.count });
    body.appendChild(title);

    row.appendChild(mark);
    row.appendChild(body);
    list.appendChild(row);
  });
}

function renderEmpty(data) {
  const counts = data.counts || {};
  const isEmpty = !counts.musics;
  qs("#overview-empty").hidden = !isEmpty;
  qs("#overview-columns").hidden = isEmpty;
}

function renderOverview(data) {
  renderSummary(data);
  renderStats(data);
  renderRecent(data);
  renderIssues(data);
  renderEmpty(data);
}

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
  if (state.sort === "created") {
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
    const message = total ? T("songs.no_match") : T("songs.empty_hint");
    list.innerHTML = '<li class="row-empty">' + esc(message) + "</li>";
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
    const warn = group.compulsory && selected.length === 0;
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
    return (
      '<div class="tag-group' + (warn ? " is-warn" : "") + '">' +
      '<div class="tag-group-head"><span>' + esc(group.name) + "</span>" +
      '<span class="tag-flag">' + esc(flags.join(" · ")) + "</span></div>" +
      '<div class="chips">' + chips + "</div>" +
      (warn ? '<p class="tag-hint">' + esc(T("song.missing_tag")) + "</p>" : "") +
      "</div>"
    );
  });

  const aliasCount = Math.max(0, (music.names || []).length - 1);
  const flags = [];
  if (music.missing) flags.push('<span class="tag-flag">' + esc(T("song.missing_file")) + "</span>");
  if (music.tag_issue) flags.push('<span class="tag-flag">' + esc(T("song.missing_tag")) + "</span>");

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
    '<div class="field-body file-line"><span class="mono">assets\\music\\' +
    esc(music.md5 + "." + music.ext) + "</span></div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.size")) + "</span>" +
    '<div class="field-body">' + formatSize(music.size) + "</div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.duration")) + "</span>" +
    '<div class="field-body">' + formatDuration(music.duration_ms) + "</div></div>" +
    '<div class="field-row"><span class="field-label">' + esc(T("song.imported_at")) + "</span>" +
    '<div class="field-body">' + formatDate(music.created_at) + "</div></div>" +
    "</section>" +

    '<p class="modal-note" style="margin-top:4px">' +
    esc(T("song.alias_count", { count: aliasCount })) + "</p>";
}

function renderSongs() {
  renderSongList();
  renderSelectionBar();
  renderDetail();
}

/* ---------- 自绘下拉框 ---------- */

function selectMarkup(attrs, options, value) {
  const current = options.find(function (item) {
    return item.value === value;
  });
  const menu = options
    .map(function (option) {
      return (
        '<button class="select-option' + (option.value === value ? " active" : "") +
        '" type="button" role="option" data-value="' + esc(option.value) + '">' +
        esc(option.label) + "</button>"
      );
    })
    .join("");
  return (
    '<div class="select small" ' + attrs +
    ' role="combobox" tabindex="0" aria-expanded="false" aria-haspopup="listbox" data-value="' +
    esc(value) + '"><span class="select-value">' + esc(current ? current.label : "") +
    '</span><svg class="select-arrow" viewBox="0 0 12 12" aria-hidden="true">' +
    '<path d="M2.5 4.5L6 8l3.5-3.5"/></svg>' +
    '<div class="select-menu" role="listbox">' + menu + "</div></div>"
  );
}

function setSelectValue(select, value, notify) {
  select.dataset.value = value;
  const option = select.querySelector('.select-option[data-value="' + value + '"]');
  const label = select.querySelector(".select-value");
  if (label) label.textContent = option ? option.textContent : value;
  select.querySelectorAll(".select-option").forEach(function (node) {
    node.classList.toggle("active", node.dataset.value === value);
  });
  if (notify) {
    select.dispatchEvent(
      new CustomEvent("selectchange", { bubbles: true, detail: { value: value } })
    );
  }
}

function closeSelects(except) {
  qsa(".select.open").forEach(function (select) {
    if (select === except) return;
    select.classList.remove("open");
    select.setAttribute("aria-expanded", "false");
  });
}

function toggleSelect(select) {
  const open = select.classList.contains("open");
  closeSelects(select);
  select.classList.toggle("open", !open);
  select.setAttribute("aria-expanded", String(!open));
}

function stepSelect(select, delta) {
  const options = qsa(".select-option", select);
  if (!options.length) return;
  let index = options.findIndex(function (node) {
    return node.dataset.value === select.dataset.value;
  });
  if (index === -1) index = 0;
  index = Math.min(options.length - 1, Math.max(0, index + delta));
  setSelectValue(select, options[index].dataset.value, true);
}

function initSelects() {
  document.addEventListener("click", function (event) {
    const option = event.target.closest(".select-option");
    if (option) {
      const select = option.closest(".select");
      setSelectValue(select, option.dataset.value, true);
      closeSelects();
      return;
    }
    const select = event.target.closest(".select");
    if (select) {
      toggleSelect(select);
      return;
    }
    closeSelects();
  });

  document.addEventListener("keydown", function (event) {
    const select = event.target.closest(".select");
    if (!select) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      toggleSelect(select);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      stepSelect(select, event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Escape") {
      event.stopPropagation();
      closeSelects();
      select.blur();
    }
  });
}

function setupSortSelect() {
  const select = qs("#songs-sort");
  if (!select) return;
  select.querySelector(".select-menu").innerHTML = [
    { value: "title", label: T("songs.sort_title") },
    { value: "created", label: T("songs.sort_created") },
    { value: "duration", label: T("songs.sort_duration") },
    { value: "author", label: T("songs.sort_author") },
  ]
    .map(function (option) {
      return (
        '<button class="select-option' + (option.value === state.sort ? " active" : "") +
        '" type="button" role="option" data-value="' + option.value + '">' +
        esc(option.label) + "</button>"
      );
    })
    .join("");
  select.dataset.value = state.sort;
  select.querySelector(".select-value").textContent = T(
    "songs.sort_" + (state.sort === "created" ? "created" : state.sort)
  );
  select.addEventListener("selectchange", function (event) {
    state.sort = event.detail.value;
    renderSongList();
  });
}

/* ---------- 歌单 ---------- */

function playlistByUid(uid) {
  return (
    ((state.data && state.data.playlists) || []).find(function (item) {
      return item.uid === uid;
    }) || null
  );
}

function visiblePlaylists() {
  const list = (state.data && state.data.playlists) || [];
  const query = state.playlistQuery.trim().toLowerCase();
  if (!query) return list;
  return list.filter(function (playlist) {
    return playlist.title.toLowerCase().indexOf(query) !== -1;
  });
}

function playlistKindLabel(playlist) {
  return T(playlist.kind === "manual" ? "playlist.kind_manual" : "playlist.kind_filter");
}

function renderPlaylistList() {
  const list = qs("#playlist-list");
  const total = (state.data.playlists || []).length;
  const items = visiblePlaylists();
  qs("#playlists-count").textContent = T("playlist.total", { count: total });

  if (!items.length) {
    list.innerHTML = '<li class="row-empty">' + esc(T("playlist.empty")) + "</li>";
    return;
  }

  list.innerHTML = items
    .map(function (playlist) {
      const classes = ["song-row"];
      if (state.activeKind === "playlist" && state.active === playlist.uid) {
        classes.push("is-active");
      }
      const badge = playlist.builtin
        ? T("playlist.builtin")
        : playlistKindLabel(playlist);
      const count = playlist.error
        ? T("playlist.resolve_error")
        : T("playlist.count", { count: playlist.count });
      return (
        '<li class="' + classes.join(" ") + '" data-playlist-uid="' + esc(playlist.uid) +
        '" tabindex="0"><div class="song-body"><span class="song-title">' +
        esc(playlist.title) + '</span><span class="song-sub">' + esc(badge) + " · " +
        esc(count) + "</span></div></li>"
      );
    })
    .join("");
}

function renderPlaylistDetail() {
  const pane = qs("#playlist-detail");
  const playlist =
    state.activeKind === "playlist" && state.active ? playlistByUid(state.active) : null;

  if (!playlist) {
    pane.innerHTML =
      '<div class="detail-empty">' +
      '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>' +
      "<h2>" + esc(T("playlist.no_selection_title")) + "</h2>" +
      "<p>" + esc(T("playlist.no_selection_hint")) + "</p></div>";
    return;
  }

  const count = playlist.error
    ? T("playlist.resolve_error")
    : T("playlist.count", { count: playlist.count });
  const badge = playlist.builtin
    ? '<span class="badge is-builtin">' + esc(T("playlist.builtin")) + "</span>"
    : '<span class="badge">' + esc(playlistKindLabel(playlist)) + "</span>";

  const nameRow = playlist.builtin
    ? '<div class="field-row"><span class="field-label">' + esc(T("playlist.name")) +
      '</span><div class="field-body"><span>' + esc(playlist.title) +
      '</span><p class="detail-hint">' + esc(T("playlist.builtin_hint")) + "</p></div></div>"
    : '<div class="field-row"><span class="field-label">' + esc(T("playlist.name")) +
      '</span><div class="field-body"><input class="input" id="playlist-name" value="' +
      esc(playlist.title) + '" maxlength="120"></div></div>';

  const content =
    playlist.kind === "manual" ? manualPlaylistCard(playlist) : filterPlaylistCard(playlist);

  pane.innerHTML =
    '<header class="detail-head"><div class="detail-title"><h2>' +
    esc(playlist.title) + "</h2><div class=\"detail-meta\">" + badge +
    "<span>·</span><span>" + esc(count) + "</span></div></div>" +
    '<div class="detail-tools">' +
    (playlist.builtin
      ? ""
      : '<button class="btn ghost" data-menu="playlist">' + esc(T("action.more")) + "</button>") +
    "</div></header>" +
    '<section class="card">' + nameRow + "</section>" +
    content;
}

function manualPlaylistCard(playlist) {
  const musics = (playlist.entries || [])
    .map(function (md5) {
      return musicByMd5(md5);
    })
    .filter(Boolean);

  const rows = musics
    .map(function (music) {
      return (
        '<li class="entry-row" draggable="true" data-entry="' + esc(music.md5) + '">' +
        '<span class="grip" aria-hidden="true">⋮⋮</span>' +
        '<div class="entry-body"><span class="entry-title">' + esc(music.title) +
        '</span><span class="entry-sub">' + esc(music.authors_text || T("song.no_author")) +
        " · " + formatDuration(music.duration_ms) + "</span></div>" +
        '<button class="icon-btn" data-entry-remove="' + esc(music.md5) +
        '" aria-label="' + esc(T("action.remove")) + '">×</button></li>'
      );
    })
    .join("");

  return (
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("playlist.content")) + " · " + esc(T("playlist.count", { count: musics.length })) +
    '</h3><button class="btn soft small" data-playlist-add="1">' +
    esc(T("playlist.add_songs")) + "</button></div>" +
    (rows
      ? '<ul class="entry-list" id="entry-list">' + rows + "</ul>"
      : '<p class="row-empty">' + esc(T("playlist.entries_empty")) + "</p>") +
    "</section>"
  );
}

function filterPlaylistCard(playlist) {
  const rows = (playlist.filters || [])
    .map(function (condition, index) {
      return filterRowMarkup(condition, index);
    })
    .join("");

  return (
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("playlist.conditions")) + " · " +
    esc(
      playlist.error
        ? T("playlist.resolve_error")
        : T("playlist.count", { count: playlist.count })
    ) +
    '</h3><button class="btn soft small" data-filter-add="1">' +
    esc(T("playlist.add_condition")) + "</button></div>" +
    (rows || '<p class="row-empty">' + esc(T("playlist.condition_empty")) + "</p>") +
    '<div class="card-tools" style="margin-top:10px"><span></span>' +
    '<button class="btn ghost small" data-playlist-preview="1">' +
    esc(T("playlist.preview")) + "</button></div>" +
    (playlist.error ? '<p class="detail-error">' + esc(playlist.error) + "</p>" : "") +
    "</section>"
  );
}

function filterRowMarkup(condition, index) {
  const modeOptions = [
    { value: "include", label: T("playlist.filter_include") },
    { value: "exclude", label: T("playlist.filter_exclude") },
  ];
  const targetOptions = [
    { value: "all", label: T("playlist.target_all") },
    { value: "music", label: T("playlist.target_music") },
    { value: "playlist", label: T("playlist.target_playlist") },
    { value: "tag", label: T("playlist.target_tag") },
    { value: "author", label: T("playlist.target_author") },
  ];

  const values =
    condition.target === "all"
      ? '<span class="filter-summary">' + esc(T("playlist.target_all")) + "</span>"
      : '<span class="filter-summary">' + esc(filterSummary(condition)) + "</span>" +
        '<button class="btn soft small" data-filter-pick="' + index + '">' +
        esc(T("playlist.filter_pick")) + "</button>";

  return (
    '<div class="filter-row" data-filter-index="' + index + '">' +
    selectMarkup('data-filter-mode="' + index + '"', modeOptions, condition.mode) +
    selectMarkup('data-filter-target="' + index + '"', targetOptions, condition.target) +
    '<div class="filter-values">' + values + "</div>" +
    '<div class="filter-tools">' +
    '<button class="icon-btn" data-filter-up="' + index + '" aria-label="' +
    esc(T("action.up")) + '">↑</button>' +
    '<button class="icon-btn" data-filter-down="' + index + '" aria-label="' +
    esc(T("action.down")) + '">↓</button>' +
    '<button class="icon-btn" data-filter-remove="' + index + '" aria-label="' +
    esc(T("action.remove")) + '">×</button>' +
    "</div></div>"
  );
}

function filterSummary(condition) {
  const values = condition.values || [];
  if (!values.length) return T("playlist.filter_empty");
  const names = values
    .map(function (uid) {
      return objectName(condition.target, uid);
    })
    .filter(Boolean);
  if (!names.length) return T("playlist.filter_empty");
  const shown = names.slice(0, 2).join("、");
  return names.length > 2 ? shown + T("playlist.more", { count: names.length - 2 }) : shown;
}

function objectName(target, uid) {
  if (target === "music") {
    const music = musicByMd5(uid);
    return music ? music.title : "";
  }
  if (target === "playlist") {
    const playlist = playlistByUid(uid);
    return playlist ? playlist.title : "";
  }
  if (target === "tag") {
    const tag = tagMap()[uid];
    return tag ? tag.name : "";
  }
  if (target === "author") {
    const author = authorMap()[uid];
    return author ? author.name : "";
  }
  return "";
}

function renderPlaylists() {
  renderPlaylistList();
  renderPlaylistDetail();
}

/* ---------- 总渲染 ---------- */

function apply(data) {
  if (!data) return;
  state.data = data;

  if (data.language) document.documentElement.lang = data.language;
  applyTheme(data.theme);
  applyNav(data.section || "overview");

  // 后端的选择变化（点击最近导入、导入后自动选中）要反映到详情区；
  // 同一份选择重复下发时不能覆盖前端的多选。
  const incoming = data.selection ? data.selection.uid : null;
  const incomingKind = data.selection ? data.selection.kind : null;
  if (incoming !== state.serverSelection || incomingKind !== state.serverKind) {
    state.active = incoming;
    state.activeKind = incomingKind;
    if (incoming && incomingKind === "music") state.selection = new Set([incoming]);
  }
  state.serverSelection = incoming;
  state.serverKind = incomingKind;

  if (!state.active || !itemByKind(state.activeKind, state.active)) {
    state.active = incoming;
    state.activeKind = incomingKind;
  }
  state.selection.forEach(function (md5) {
    if (!musicByMd5(md5)) state.selection.delete(md5);
  });

  if (data.section === "overview") renderOverview(data);
  else if (data.section === "songs") renderSongs();
  else if (data.section === "playlists") renderPlaylists();

  if (data.message) toast(data.message, data.ok !== false);
}

function itemByKind(kind, uid) {
  if (!uid) return null;
  if (kind === "music") return musicByMd5(uid);
  if (kind === "playlist") return playlistByUid(uid);
  return null;
}

/* ---------- 交互 ---------- */

function toast(message, ok) {
  const node = qs("#toast");
  node.textContent = message;
  node.classList.toggle("is-error", ok === false);
  node.hidden = false;
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(function () {
    node.hidden = true;
  }, 2600);
}

async function goSection(section) {
  applyNav(section);
  const data = await call("select_section", section);
  if (data) apply(data);

  // 歌单数量少，进分区时直接落在第一个，省掉一次点击。
  if (section === "playlists" && state.activeKind !== "playlist") {
    const first = ((state.data && state.data.playlists) || [])[0];
    if (first) selectPlaylist(first.uid);
  }
}

async function selectMusic(md5) {
  state.active = md5;
  state.activeKind = "music";
  state.selection = new Set([md5]);
  state.anchor = md5;
  renderSongs();
  const data = await call("select_item", "music", md5);
  if (data) apply(data);
}

async function selectPlaylist(uid) {
  state.active = uid;
  state.activeKind = "playlist";
  renderPlaylists();
  const data = await call("select_item", "playlist", uid);
  if (data) apply(data);
}

function toggleSelection(md5) {
  if (state.selection.has(md5)) state.selection.delete(md5);
  else state.selection.add(md5);
  state.active = md5;
  state.anchor = md5;
  renderSongs();
}

function selectRange(md5) {
  const musics = visibleMusics();
  const from = musics.findIndex(function (item) {
    return item.md5 === state.anchor;
  });
  const to = musics.findIndex(function (item) {
    return item.md5 === md5;
  });
  if (from === -1 || to === -1) return toggleSelection(md5);
  const start = Math.min(from, to);
  const end = Math.max(from, to);
  for (let index = start; index <= end; index += 1) state.selection.add(musics[index].md5);
  state.active = md5;
  renderSongs();
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
  openModal({
    title: T("playlist.delete"),
    body:
      '<p class="modal-note">' +
      esc(T("playlist.delete_confirm", { name: playlist.title })) +
      "</p>",
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
    body = '<p class="detail-error">' + esc(result.message) + "</p>";
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

/* ---------- 菜单 ---------- */

function closeMenu() {
  const menu = qs("#menu");
  menu.hidden = true;
  menu.innerHTML = "";
}

function openMenu(anchor, items) {
  const menu = qs("#menu");
  menu.innerHTML = items
    .map(function (item, index) {
      return '<button class="menu-item" data-menu-index="' + index + '">' +
        esc(item.label) + "</button>";
    })
    .join("");
  menu.hidden = false;

  const rect = anchor.getBoundingClientRect();
  const width = menu.offsetWidth;
  const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
  menu.style.left = left + "px";
  menu.style.top = rect.bottom + 4 + "px";

  menu.onclick = function (event) {
    const button = event.target.closest("[data-menu-index]");
    if (!button) return;
    const item = items[Number(button.dataset.menuIndex)];
    closeMenu();
    if (item && item.onClick) item.onClick();
  };
}

/* ---------- 弹窗 ---------- */

let modalDismissible = true;

function closeModal() {
  if (!modalDismissible) return;
  const modal = qs("#modal");
  modal.hidden = true;
  qs("#modal-body").innerHTML = "";
  qs("#modal-actions").innerHTML = "";
  qs("#app").inert = false;
  modalDismissible = true;
}

function openModal(options) {
  const modal = qs("#modal");
  const card = qs("#modal-card");
  closeMenu();
  qs("#app").inert = true;
  qs("#modal-title").textContent = options.title || "";
  qs("#modal-body").innerHTML = options.body || "";
  qs("#modal-body").onclick = null;
  qs("#modal-actions").innerHTML = "";

  (options.actions || []).forEach(function (action) {
    const button = document.createElement("button");
    button.className =
      "btn" + (action.primary ? " primary" : "") + (action.danger ? " danger" : "");
    button.textContent = action.label;
    button.addEventListener("click", action.onClick);
    qs("#modal-actions").appendChild(button);
  });

  card.classList.toggle("wide", Boolean(options.wide));
  modalDismissible = options.dismissible !== false;
  qs("#modal-close").hidden = !modalDismissible;
  modal.hidden = false;
  card.focus();

  if (options.onMount) options.onMount();
}

function trapFocus(event) {
  if (event.key !== "Tab") return;
  const card = qs("#modal-card");
  const focusables = qsa(
    "button, input, select, textarea, [tabindex]:not([tabindex='-1'])",
    card
  ).filter(function (node) {
    return !node.disabled && node.offsetParent !== null;
  });
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
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
    const authors = state.data.library.authors;
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

/* ---------- 完整性检查 ---------- */

async function openIntegrity() {
  const report = await call("run_integrity");
  if (!report) return;

  let body;
  if (report.ok) {
    body = '<div class="empty" style="min-height:200px"><h2>' +
      esc(T("integrity.ok")) + "</h2></div>";
  } else {
    body =
      '<p class="modal-note">' + esc(T("integrity.count", { count: report.count })) + "</p>" +
      report.sections
        .map(function (section) {
          const items = section.items
            .map(function (item) {
              return "<li>" + esc(item) + "</li>";
            })
            .join("");
          return (
            '<div class="report-section"><h3 class="report-title">' +
            esc(T("integrity." + section.key)) +
            '<span class="report-count">' + section.items.length + "</span></h3>" +
            '<ul class="report-list">' + items + "</ul></div>"
          );
        })
        .join("");
  }

  openModal({
    title: T("integrity.title"),
    body: body,
    wide: true,
    actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
  });
}

/* ---------- 导入 ---------- */

async function doImport() {
  const result = await call("browse_import");
  if (!result || !result.paths || !result.paths.length) return;
  if (result.paths.length === 1) {
    const started = await call("start_import", result.paths);
    if (started && started.task_id) openImportModal(started.task_id);
    return;
  }
  const preview = await call("preview_import", result.paths);
  if (!preview || !preview.items.length) return;
  openWizard(preview.items);
}

function progressMarkup() {
  return (
    '<p class="progress-text" id="import-line"></p>' +
    '<div class="progress"><div class="progress-bar" id="import-bar"></div></div>' +
    '<div id="import-errors"></div>'
  );
}

function openImportModal(taskId) {
  openModal({
    title: T("import.title"),
    body: progressMarkup(),
    dismissible: false,
    actions: [],
  });
  runImportTask(taskId, []);
}

function runImportTask(taskId, tagUids) {
  let misses = 0;

  async function poll() {
    const task = await call("poll_task", taskId);
    if (!task) {
      misses += 1;
      if (misses < 3) {
        window.setTimeout(poll, 500);
        return;
      }
      qs("#import-line").textContent = T("import.failed");
      modalDismissible = true;
      qs("#modal-close").hidden = false;
      return;
    }

    if (task.state === "running") {
      const percent = task.total ? Math.round((task.done / task.total) * 100) : 0;
      qs("#import-line").textContent = T("import.running", {
        done: task.done,
        total: task.total,
        current: task.current,
      });
      qs("#import-bar").style.width = percent + "%";
      window.setTimeout(poll, 300);
      return;
    }

    await finishImport(task, tagUids);
  }

  poll();
}

async function finishImport(task, tagUids) {
  qs("#import-line").textContent = T("import.done");
  qs("#import-bar").style.width = "100%";

  const summary = document.createElement("p");
  summary.className = "modal-note";
  summary.textContent = T("import.summary", {
    ok: task.imported.length,
    failed: task.errors.length,
  });
  qs("#import-errors").appendChild(summary);

  if (task.errors.length) {
    const list = document.createElement("ul");
    list.className = "report-list";
    task.errors.forEach(function (item) {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    qs("#import-errors").appendChild(list);
  }

  // 先把「关闭」放出来，后面即使刷新状态失败，用户也不会被锁在弹窗里。
  const actions = qs("#modal-actions");
  const button = document.createElement("button");
  button.className = "btn primary";
  button.textContent = T("action.close");
  button.addEventListener("click", closeModal);
  actions.appendChild(button);
  modalDismissible = true;
  qs("#modal-close").hidden = false;

  let data = null;
  if (tagUids.length && task.imported.length) {
    data = await call("batch_add_tags", task.imported, tagUids, false);
  }
  if (!data) data = await call("get_state");
  if (data) apply(data);

  if (task.imported.length) {
    const selected = await call("select_item", "music", task.imported[0]);
    if (selected) apply(selected);
  }
}

/* ---------- 批量导入向导 ---------- */

const wizard = { rows: [], tags: new Set(), step: 1 };

function openWizard(items) {
  wizard.rows = items.map(function (item) {
    return {
      path: item.path,
      filename: item.filename,
      title: item.title || "",
      authors: (item.authors || []).join(", "),
    };
  });
  wizard.tags = new Set();
  wizard.step = 1;
  renderWizard();
}

function renderWizard() {
  const step = wizard.step;
  const stepNames = {
    1: T("import.step_files"),
    2: T("import.step_tags"),
    3: T("import.step_confirm"),
  };
  let body = "";
  if (step === 1) body = wizardFiles();
  else if (step === 2) body = wizardTags();
  else body = wizardConfirm();

  const actions = [{ label: T("action.cancel"), onClick: closeModal }];
  if (step > 1) {
    actions.push({
      label: T("import.prev"),
      onClick: function () {
        wizard.step -= 1;
        renderWizard();
      },
    });
  }
  if (step < 3) {
    actions.push({
      label: T("import.next"),
      primary: true,
      onClick: function () {
        wizard.step += 1;
        renderWizard();
      },
    });
  } else {
    actions.push({ label: T("import.start"), primary: true, onClick: runWizardImport });
  }

  openModal({
    title: T("import.wizard_title"),
    body:
      '<p class="modal-note">' +
      esc(T("import.step", { current: step, total: 3 })) +
      " · " +
      esc(stepNames[step]) +
      "</p>" +
      body,
    wide: true,
    actions: actions,
    onMount: function () {
      mountWizard(step);
    },
  });
}

function wizardFiles() {
  if (!wizard.rows.length) {
    return '<p class="row-empty">' + esc(T("import.empty")) + "</p>";
  }
  const rows = wizard.rows
    .map(function (row, index) {
      return (
        '<div class="wizard-row" data-index="' + index + '">' +
        '<div class="wizard-head"><span class="wizard-file" title="' +
        esc(row.filename) + '">' + esc(row.filename) + "</span>" +
        '<button class="icon-btn" data-remove="' + index + '" aria-label="' +
        esc(T("action.remove")) + '">×</button></div>' +
        '<div class="wizard-fields">' +
        '<input class="input" data-field="title" value="' + esc(row.title) +
        '" placeholder="' + esc(T("import.title_field")) + '">' +
        '<input class="input" data-field="authors" value="' + esc(row.authors) +
        '" placeholder="' + esc(T("import.authors_field")) + '">' +
        "</div></div>"
      );
    })
    .join("");
  return (
    '<p class="modal-note">' +
    esc(T("import.files_note", { count: wizard.rows.length })) +
    "</p>" +
    '<div class="wizard-list">' + rows + "</div>"
  );
}

function wizardTags() {
  const groups = state.data.library.tag_groups || [];
  if (!groups.length) {
    return '<p class="row-empty">' + esc(T("batch.no_tags")) + "</p>";
  }
  const sections = groups
    .map(function (group) {
      const chips = group.tags
        .map(function (tag) {
          const on = wizard.tags.has(tag.uid);
          return (
            '<button class="chip-toggle' + (on ? " is-on" : "") + '" data-wizard-tag="' +
            esc(tag.uid) + '">' + esc(tag.name) + "</button>"
          );
        })
        .join("");
      return (
        '<div class="tag-group"><div class="tag-group-head"><span>' +
        esc(group.name) + '</span></div><div class="chips">' + chips + "</div></div>"
      );
    })
    .join("");
  return '<p class="modal-note">' + esc(T("import.tags_note")) + "</p>" + sections;
}

function wizardConfirm() {
  const rows = wizard.rows
    .map(function (row) {
      const title = row.title.trim() || row.filename;
      const authors = row.authors.trim();
      return "<li>" + esc(title) + (authors ? " · " + esc(authors) : "") + "</li>";
    })
    .join("");
  const cleanDefault = Boolean(
    state.data.settings && state.data.settings.import && state.data.settings.import.clean_audio
  );
  return (
    '<p class="modal-note">' +
    esc(T("import.confirm_note", { count: wizard.rows.length })) +
    "</p>" +
    '<ul class="report-list">' + rows + "</ul>" +
    '<label class="check" style="margin-top:14px"><input type="checkbox" id="wizard-clean"' +
    (cleanDefault ? " checked" : "") +
    "><span>" +
    esc(T("import.clean")) +
    "</span></label>"
  );
}

function mountWizard(step) {
  const body = qs("#modal-body");
  if (step === 1) {
    body.oninput = function (event) {
      const row = event.target.closest("[data-index]");
      const field = event.target.dataset.field;
      if (!row || !field) return;
      wizard.rows[Number(row.dataset.index)][field] = event.target.value;
    };
    body.onclick = function (event) {
      const remove = event.target.closest("[data-remove]");
      if (!remove) return;
      wizard.rows.splice(Number(remove.dataset.remove), 1);
      if (!wizard.rows.length) {
        closeModal();
        return;
      }
      renderWizard();
    };
  } else if (step === 2) {
    body.onclick = function (event) {
      const chip = event.target.closest("[data-wizard-tag]");
      if (!chip) return;
      const uid = chip.dataset.wizardTag;
      if (wizard.tags.has(uid)) wizard.tags.delete(uid);
      else wizard.tags.add(uid);
      chip.classList.toggle("is-on", wizard.tags.has(uid));
    };
  }
}

async function runWizardImport() {
  const cleanBox = qs("#wizard-clean");
  const clean = cleanBox ? cleanBox.checked : null;
  const items = wizard.rows.map(function (row) {
    return {
      path: row.path,
      title: row.title.trim(),
      authors: row.authors
        .split(/[,，]/)
        .map(function (name) {
          return name.trim();
        })
        .filter(Boolean),
    };
  });

  const started = await call("start_import", items, clean);
  if (!started || !started.task_id) return;

  openModal({
    title: T("import.wizard_title"),
    body: progressMarkup(),
    dismissible: false,
    actions: [],
  });
  runImportTask(started.task_id, Array.from(wizard.tags));
}

/* ---------- 事件绑定 ---------- */

function bindEvents() {
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
      else if (name === "integrity") openIntegrity();
      else if (name === "settings") goSection("settings");
      return;
    }

    const recent = event.target.closest("#recent .row[data-md5]");
    if (recent) {
      selectMusic(recent.dataset.md5);
      return;
    }

    if (event.target.closest("#issues .row")) {
      goSection("songs");
      return;
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
    else if (action === "clear") {
      state.selection.clear();
      renderSongs();
    }
  });

  qs("#btn-new-playlist").addEventListener("click", openCreatePlaylist);

  qs("#playlist-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-playlist-uid]");
    if (row) selectPlaylist(row.dataset.playlistUid);
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

  playlistDetail.addEventListener("click", async function (event) {
    const playlist = playlistByUid(state.active);
    if (!playlist) return;

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
      const data = await call("toggle_music_tag", state.active, tag.dataset.tag, on);
      if (data) apply(data);
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
        toast(String(error), false);
      }
      return;
    }

    const menu = event.target.closest("[data-menu='song']");
    if (menu) {
      const music = musicByMd5(state.active);
      if (!music) return;
      openMenu(menu, [
        {
          label: T("action.manage_aliases"),
          onClick: function () {
            openAliasEditor(music);
          },
        },
      ]);
    }
  });

  qs("#modal-close").addEventListener("click", closeModal);
  qs("#modal").addEventListener("click", function (event) {
    if (event.target === qs("#modal")) closeModal();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (!qs("#modal").hidden) closeModal();
      closeMenu();
      return;
    }
    if (!qs("#modal").hidden) {
      trapFocus(event);
      return;
    }
    if (event.key === "Escape" && qs("#menu").hidden === false) closeMenu();
  });
}

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

/* ---------- 启动 ---------- */

async function init() {
  bindEvents();
  initSelects();
  await loadStrings();
  applyStrings();
  setupSortSelect();
  apply(await call("get_state"));
}

if (bridge()) {
  init();
} else {
  window.addEventListener("pywebviewready", init, { once: true });
}
