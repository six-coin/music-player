/* 管理器的前端。没有框架、没有构建步骤：拉一次文案与快照，整体重绘。 */

const state = {
  data: null,
  strings: {},
  tab: "imported",
  sort: "title",
  query: "",
  playlistQuery: "",
  tagQuery: "",
  authorQuery: "",
  settingsTab: "general",
  drawer: null,
  auditionMd5: null,
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
  dragAuthor: null,
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

function delay(ms) {
  return new Promise(function (resolve) {
    window.setTimeout(resolve, ms);
  });
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
  else if (section === "tags") showView("tags");
  else if (section === "authors") showView("authors");
  else if (section === "settings") showView("settings");
  else showView("pending");
  if (section === "settings") renderSettings();
  if (section !== "playlists") closeDrawer();
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

/* ---------- 空状态 ---------- */

const EMPTY_ICONS = {
  song: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  playlist: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  tag: '<path d="M20.59 13.41 12 22 2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z"/><circle cx="7" cy="7" r="1.5"/>',
  author:
    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
};

function emptyList(kind, title, hint, action) {
  return (
    '<li class="list-empty">' +
    '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
    (EMPTY_ICONS[kind] || EMPTY_ICONS.song) +
    "</svg>" +
    '<p class="list-empty-title">' + esc(title) + "</p>" +
    (hint ? '<p class="list-empty-hint">' + esc(hint) + "</p>" : "") +
    (action
      ? '<button class="btn primary small" data-action="' + action.action + '">' +
        esc(action.label) + "</button>"
      : "") +
    "</li>"
  );
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
    '<div class="field-body file-line"><span class="mono">assets\\music\\' +
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

/* ---------- 自绘下拉框 ---------- */

function selectMarkup(attrs, options, value, size) {
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
    '<div class="select ' + (size === undefined ? "small" : size) + '" ' + attrs +
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
    list.innerHTML = total
      ? '<li class="row-empty">' + esc(T("playlist.no_match")) + "</li>"
      : emptyList("playlist", T("playlist.empty"), T("playlist.empty_hint"), {
          action: "new_playlist",
          label: T("playlist.new"),
        });
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
    '<section class="card is-bare">' + nameRow + "</section>" +
    content +
    adaptationCard(playlist);
}

/* ---------- 自适应 ---------- */

function adaptationDefaults() {
  const common = (state.data && state.data.settings && state.data.settings.common) || {};
  return common.adaptation || {};
}

function adaptRow(key, label, hint, unit, value, fallback, overridden, limits) {
  const number = value === null || value === undefined ? fallback : value;
  const range =
    limits && limits.min !== undefined
      ? ' min="' + limits.min + '" max="' + limits.max + '" step="' + (limits.step || 1) + '"'
      : "";
  return (
    '<div class="adapt-row"><div><span class="adapt-name">' + esc(label) + "</span>" +
    '<span class="adapt-hint">' + esc(hint) + "</span></div>" +
    '<input class="input" type="number" data-adapt="' + key + '" value="' + esc(number) + '"' +
    range + (overridden ? "" : " disabled") + ">" +
    '<span class="adapt-unit">' + esc(unit) + "</span>" +
    '<label class="check adapt-inherit"><input type="checkbox" data-inherit="' + key + '"' +
    (overridden ? "" : " checked") + "><span>" + esc(T("adaptation.inherit")) + "</span></label>" +
    "</div>"
  );
}

function adaptationCard(playlist) {
  const adapt = playlist.adaptation || {};
  const defaults = adaptationDefaults();
  const overridden = function (key) {
    return adapt[key] !== null && adapt[key] !== undefined;
  };
  const globalText = function (key, unit) {
    return unit
      ? T("adaptation.global_unit", { value: defaults[key], unit: unit })
      : T("adaptation.global", { value: defaults[key] });
  };

  return (
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("adaptation.title")) + '</h3><button class="btn ghost small" data-stats="' +
    esc(playlist.uid) + '">' + esc(T("adaptation.view_stats")) + "</button></div>" +
    '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
    esc(T("adaptation.enabled")) + '</div><p class="toggle-hint">' +
    esc(T("adaptation.enabled_hint")) + "</p></div>" +
    '<button class="switch" type="button" role="switch" data-adapt-enabled aria-checked="' +
    (adapt.enabled ? "true" : "false") + '"><span class="switch-knob"></span></button></div>' +
    adaptRow(
      "window",
      T("adaptation.window"),
      globalText("window", T("adaptation.times")),
      T("adaptation.times"),
      adapt.window,
      defaults.window,
      overridden("window"),
      { min: 10, max: 1000 }
    ) +
    adaptRow(
      "min_plays",
      T("adaptation.min_plays"),
      globalText("min_plays", T("adaptation.times")),
      T("adaptation.times"),
      adapt.min_plays,
      defaults.min_plays,
      overridden("min_plays"),
      { min: 0, max: 1000 }
    ) +
    adaptRow(
      "base",
      T("adaptation.base"),
      globalText("base", ""),
      "",
      adapt.base,
      defaults.base,
      overridden("base"),
      { min: 0, max: 0.99, step: 0.01 }
    ) +
    adaptRow(
      "skip_seconds",
      T("adaptation.skip_seconds"),
      globalText("skip_seconds", T("adaptation.seconds")),
      T("adaptation.seconds"),
      adapt.skip_seconds,
      defaults.skip_seconds,
      overridden("skip_seconds"),
      { min: 5, max: 300 }
    ) +
    "</section>"
  );
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
    '<section class="card card--list"><div class="card-tools"><h3 class="card-title">' +
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
    (playlist.error ? '<p class="detail-error">' + esc(playlist.error) + "</p>" : "") +
    '<div class="card-foot">' +
    '<button class="btn ghost small" data-playlist-preview="1">' +
    esc(T("playlist.preview")) + "</button></div>" +
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

    '<section class="card card--list"><div class="card-tools"><h3 class="card-title">' +
    esc(T("author.songs")) + '</h3><span class="detail-hint">' +
    esc(T("author.count", { count: songs.length })) + "</span></div>" +
    '<ul class="entry-list">' + rows + "</ul></section>";
}

function renderAuthors() {
  renderAuthorList();
  renderAuthorDetail();
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
  else if (data.section === "tags") renderTags();
  else if (data.section === "authors") renderAuthors();
  else if (data.section === "settings") renderSettings();

  if (state.drawer) refreshDrawer();

  if (data.message) toast(data.message, data.ok !== false);
}

function itemByKind(kind, uid) {
  if (!uid) return null;
  if (kind === "music") return musicByMd5(uid);
  if (kind === "playlist") return playlistByUid(uid);
  if (kind === "tag_group") return tagGroupByUid(uid);
  if (kind === "author") return authorByUid(uid);
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

  // 数量都不多，进分区时直接落在第一个，省掉一次点击。
  if (section === "playlists" && state.activeKind !== "playlist") {
    const first = ((state.data && state.data.playlists) || [])[0];
    if (first) selectPlaylist(first.uid);
  } else if (section === "tags" && state.activeKind !== "tag_group") {
    const first = ((state.data && state.data.library.tag_groups) || [])[0];
    if (first) selectTagGroup(first.uid);
  } else if (section === "authors" && state.activeKind !== "author") {
    const first = ((state.data && state.data.library.authors) || [])[0];
    if (first) selectAuthor(first.uid);
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

async function selectTagGroup(uid) {
  state.active = uid;
  state.activeKind = "tag_group";
  renderTags();
  const data = await call("select_item", "tag_group", uid);
  if (data) apply(data);
}

async function selectAuthor(uid) {
  state.active = uid;
  state.activeKind = "author";
  renderAuthors();
  const data = await call("select_item", "author", uid);
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
  openModal({
    title: T("tag.delete_group"),
    body: '<p class="modal-note">' + esc(T("tag.delete_confirm", { name: group.name })) + "</p>",
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
            body: '<p class="modal-note">' + esc(data.message) + "</p>",
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
  openModal({
    title: T("author.delete"),
    body: '<p class="modal-note">' + esc(T("author.delete_confirm", { name: author.name })) + "</p>",
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
            body: '<p class="modal-note">' + esc(data.message) + "</p>",
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

/* ---------- 统计抽屉 ---------- */

function percent(value) {
  return (Math.round(value * 1000) / 10).toFixed(1).replace(/\.0$/, "") + "%";
}

function rateCell(rate) {
  const width = Math.min(100, Math.round(rate * 100));
  return (
    '<div class="rate"><div class="rate-track"><div class="rate-fill' +
    (rate >= 0.6 ? " is-high" : "") + '" style="width:' + width + '%"></div></div>' +
    '<span class="rate-text">' + esc(percent(rate)) + "</span></div>"
  );
}

function statsTable(rows, options) {
  const settings = options || {};
  const head =
    "<tr><th>" + esc(T("adaptation.col_song")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_records")) + "</th>" +
    "<th>" + esc(T("adaptation.col_rate")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_auto")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_probability")) + "</th>" +
    (settings.reset ? "<th></th>" : "") + "</tr>";

  const body = rows
    .map(function (row) {
      const reset = settings.reset
        ? '<td><button class="btn ghost small" data-reset-md5="' + esc(row.md5) + '">' +
          esc(T("adaptation.reset_one")) + "</button></td>"
        : "";
      return (
        '<tr><td class="cell-title" title="' + esc(row.title) + '">' + esc(row.title) + "</td>" +
        '<td class="num">' + row.total + "</td>" +
        "<td>" + rateCell(row.rate) + "</td>" +
        '<td class="num">' + row.auto_skipped + "</td>" +
        '<td class="num">' + esc(percent(row.probability)) + "</td>" +
        reset +
        "</tr>"
      );
    })
    .join("");

  return '<table class="drawer-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table>";
}

async function openStatsDrawer(playlist) {
  const data = await call("get_playlist_stats", playlist.uid);
  if (!data || !data.ok) {
    toast(T("adaptation.stats_failed"), false);
    return;
  }
  state.drawer = playlist.uid;
  qs("#drawer-title").textContent = T("adaptation.stats_title", { name: playlist.title });
  renderDrawer(data);
  qs("#drawer").hidden = false;
}

function closeDrawer() {
  if (!state.drawer) return;
  state.drawer = null;
  const drawer = qs("#drawer");
  drawer.classList.add("is-closing");
  window.setTimeout(function () {
    if (state.drawer) return;
    drawer.hidden = true;
    drawer.classList.remove("is-closing");
    qs("#drawer-body").innerHTML = "";
  }, 160);
}

function confirmClearPlaylistStats() {
  const uid = state.drawer;
  if (!uid) return;
  openModal({
    title: T("adaptation.reset_all"),
    body: '<p class="modal-note">' + esc(T("adaptation.reset_all_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("adaptation.reset_all"),
        danger: true,
        onClick: async function () {
          const data = await call("reset_stats", uid, "");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function renderDrawer(data) {
  const params = data.params || {};
  const note = T("adaptation.stats_note", {
    window: params.window,
    min: params.min_plays,
    base: params.base,
    seconds: params.skip_seconds,
  });
  const rows = data.rows || [];
  const body = rows.length
    ? statsTable(rows, { reset: true })
    : '<p class="drawer-note">' + esc(T("adaptation.stats_empty")) + "</p>";

  qs("#drawer-body").innerHTML =
    '<p class="drawer-note">' + esc(note) + "</p>" +
    '<div class="settings-actions" style="padding-bottom:10px">' +
    '<button class="btn ghost small" data-reset-all="1">' +
    esc(T("adaptation.reset_all")) + "</button></div>" +
    body;
}

async function refreshDrawer() {
  if (!state.drawer) return;
  const data = await call("get_playlist_stats", state.drawer);
  if (data && data.ok) renderDrawer(data);
}

async function loadMusicStats(md5) {
  const host = qs("#music-adapt");
  if (!host) return;
  const data = await call("get_music_stats", md5);
  if (!data || !data.ok) {
    host.textContent = T("adaptation.no_records");
    return;
  }

  const source = qs("#music-adapt-source");
  if (source && data.playlist) {
    source.textContent = T("adaptation.song_source", { name: data.playlist.title });
  }

  if (!data.in_playlist) {
    host.innerHTML = '<p class="tag-hint">' + esc(T("adaptation.not_in_default")) + "</p>";
    return;
  }

  const cell = function (value, label) {
    return (
      '<div class="adapt-cell"><span class="adapt-value">' + esc(value) +
      '</span><span class="adapt-label">' + esc(label) + "</span></div>"
    );
  };
  host.innerHTML =
    cell(String(data.total), T("adaptation.col_records")) +
    cell(percent(data.rate), T("adaptation.col_rate")) +
    cell(String(data.auto_skipped), T("adaptation.col_auto")) +
    cell(percent(data.probability), T("adaptation.col_probability"));
}

/* ---------- 设置 ---------- */

function settingsRow(title, hint, control, hintClass) {
  return (
    '<div class="settings-row"><div class="settings-row-main">' +
    '<div class="settings-row-title">' + esc(title) + "</div>" +
    (hint
      ? '<p class="settings-row-hint' + (hintClass ? " " + hintClass : "") + '">' +
        esc(hint) + "</p>"
      : "") +
    '</div><div class="settings-row-control">' + control + "</div></div>"
  );
}

function settingsCard(title, body, hint) {
  return (
    '<section class="card"><div class="card-heading"><h3 class="card-title">' +
    esc(title) + "</h3>" +
    (hint ? '<p class="card-hint">' + esc(hint) + "</p>" : "") +
    "</div>" + body + "</section>"
  );
}

function switchMarkup(attr, on, label) {
  return (
    '<button class="switch" type="button" role="switch" ' + attr + ' aria-checked="' +
    (on ? "true" : "false") + '"' + (label ? ' aria-label="' + esc(label) + '"' : "") +
    '><span class="switch-knob"></span></button>'
  );
}

function settingsGeneral() {
  const common = (state.data.settings && state.data.settings.common) || {};
  const adapt = common.adaptation || {};
  const status = state.data.status || {};
  const auditionVolume = Math.round(
    (((state.data.settings || {}).audition || {}).volume ?? 0.2) * 100
  );

  const themes = [
    ["system", T("settings.theme_system")],
    ["light", T("settings.theme_light")],
    ["dark", T("settings.theme_dark")],
  ];
  const themeSeg =
    '<div class="seg" id="theme-seg">' +
    themes
      .map(function (item) {
        return (
          '<button class="seg-item' + (common.theme === item[0] ? " is-active" : "") +
          '" type="button" data-theme-value="' + item[0] + '">' + esc(item[1]) + "</button>"
        );
      })
      .join("") +
    "</div>";

  const adaptRow = function (key, label, unit, min, max, step) {
    return settingsRow(
      label,
      T("adaptation.range", { min: min, max: max }),
      '<input class="input" type="number" data-default="' + key + '" value="' +
        esc(adapt[key]) + '" min="' + min + '" max="' + max + '" step="' + step +
        '" style="width:110px"><span class="adapt-unit">' + esc(unit) + "</span>"
    );
  };

  return (
    settingsCard(
      T("settings.appearance"),
      settingsRow(T("settings.theme"), T("settings.theme_hint"), themeSeg) +
        settingsRow(
          T("settings.language"),
          T("settings.language_hint"),
          '<span class="path-text">' + esc(T("language.name")) + "</span>"
        )
    ) +
    settingsCard(
      T("settings.adaptation_defaults"),
      adaptRow("window", T("adaptation.window"), T("adaptation.times"), 10, 1000, 1) +
        adaptRow("min_plays", T("adaptation.min_plays"), T("adaptation.times"), 0, 1000, 1) +
        adaptRow("base", T("adaptation.base"), "", 0, 0.99, 0.01) +
        adaptRow("skip_seconds", T("adaptation.skip_seconds"), T("adaptation.seconds"), 5, 300, 1),
      T("settings.adaptation_hint")
    ) +
    settingsCard(
      T("settings.audition"),
      settingsRow(
        T("settings.audition_volume"),
        T("settings.audition_volume_hint"),
        '<div class="volume-line"><input class="range" id="audition-default" type="range" ' +
          'min="0" max="100" step="1" value="' + auditionVolume + '">' +
          '<span class="volume-value" id="audition-default-value">' + auditionVolume + "%</span></div>"
      )
    ) +
    settingsCard(
      T("settings.paths"),
      settingsRow(
        T("settings.data_dir"),
        status.data_dir || "",
        '<button class="btn ghost small" data-action="data_dir">' +
          esc(T("action.open")) + "</button>",
        "path-text"
      ) +
        settingsRow(
          T("settings.log_dir"),
          status.log_dir || "",
          '<button class="btn ghost small" data-action="log_dir">' +
            esc(T("action.open")) + "</button>",
          "path-text"
        )
    )
  );
}

function settingsImport() {
  const section = (state.data.settings && state.data.settings.import) || {};
  const status = state.data.status || {};
  const ffmpegStatus = status.ffmpeg || { available: false, path: "" };
  const probeStatus = status.ffprobe || { available: false, path: "" };

  const statusLine = function (info, label) {
    return (
      '<span class="status-dot' + (info.available ? " is-ok" : "") + '"></span>' +
      esc(info.available ? T("settings.detected") : T("settings.not_detected")) +
      (info.path ? '<span class="path-text">' + esc(info.path) + "</span>" : "")
    );
  };

  return (
    settingsCard(
      T("settings.import_section"),
      settingsRow(
        T("settings.import_dir"),
        T("settings.import_dir_hint"),
        '<input class="input" id="import-dir" value="' + esc(section.dir || "") +
          '" placeholder="' + esc(T("settings.import_dir_placeholder")) + '">' +
          '<button class="btn ghost small" data-action="browse_import_dir">' +
          esc(T("action.browse")) + "</button>" +
          '<button class="btn ghost small" data-action="clear_import_dir">' +
          esc(T("action.clear_field")) + "</button>"
      ) +
        settingsRow(
          T("settings.clean_audio"),
          T("settings.clean_audio_hint"),
          switchMarkup(
            'data-setting-switch="import.clean_audio"',
            section.clean_audio !== false,
            T("settings.clean_audio")
          )
        )
    ) +
    settingsCard(
      T("settings.ffmpeg"),
      settingsRow(T("settings.ffmpeg_binary"), "", statusLine(ffmpegStatus)) +
        settingsRow(T("settings.ffprobe_binary"), "", statusLine(probeStatus)) +
        '<div class="settings-actions"><button class="btn ghost small" ' +
        'data-action="refresh_status">' + esc(T("settings.refresh")) + "</button></div>"
    )
  );
}

function settingsSimple() {
  const section = (state.data.settings && state.data.settings.simple) || {};
  const volume = Math.round((section.volume === undefined ? 0.2 : section.volume) * 100);
  return settingsCard(
    T("settings.simple_section"),
    settingsRow(
        T("settings.play_order"),
        T("settings.simple_order_hint"),
        selectMarkup(
          'data-setting-select="simple.order"',
          [
            { value: "shuffle", label: T("settings.order_shuffle") },
            { value: "list_loop", label: T("settings.order_list_loop") },
          ],
          section.order || "shuffle",
          ""
        )
      ) +
      settingsRow(
        T("settings.simple_volume"),
        T("settings.simple_volume_hint"),
        '<div class="volume-line"><input class="range" id="simple-volume" type="range" ' +
          'min="0" max="100" step="1" value="' + volume + '">' +
          '<span class="volume-value" id="simple-volume-value">' + volume + "%</span></div>"
      ) +
      settingsRow(
        T("settings.default_playlist"),
        T("settings.default_playlist_hint"),
        '<button class="btn ghost small" data-action="goto_default">' +
          esc(T("settings.goto")) + "</button>"
      ),
    T("settings.simple_hint")
  );
}

function settingsPlayer() {
  const section = (state.data.settings && state.data.settings.player) || {};
  const volume = Math.round((section.volume === undefined ? 0.2 : section.volume) * 100);

  return settingsCard(
    T("settings.player_section"),
    settingsRow(
      T("settings.volume"),
      T("settings.volume_hint"),
      '<div class="volume-line"><input class="range" id="player-volume" type="range" ' +
        'min="0" max="100" step="1" value="' + volume + '">' +
        '<span class="volume-value" id="player-volume-value">' + volume + "%</span></div>"
    ) +
      settingsRow(
        T("settings.play_order"),
        T("settings.player_order_hint"),
        selectMarkup(
          'data-setting-select="player.order"',
          [
            { value: "shuffle", label: T("settings.order_shuffle") },
            { value: "list_loop", label: T("settings.order_list_loop") },
            { value: "repeat_one", label: T("settings.order_repeat_one") },
          ],
          section.order || "shuffle",
          ""
        )
      ) +
      settingsRow(
        T("settings.remember_progress"),
        T("settings.remember_progress_hint"),
        switchMarkup(
          'data-setting-switch="player.remember_progress"',
          section.remember_progress !== false,
          T("settings.remember_progress")
        )
      )
  );
}

function settingsMaintenance() {
  const debugOn = ((state.data.settings || {}).common || {}).debug === true;
  return (
    settingsCard(
      T("settings.debug_section"),
      settingsRow(
        T("settings.debug"),
        T("settings.debug_hint"),
        switchMarkup('data-setting-switch="common.debug"', debugOn, T("settings.debug"))
      )
    ) +
    settingsCard(
      T("settings.maintenance_section"),
      settingsRow(
        T("settings.check"),
        T("settings.check_hint"),
        '<button class="btn ghost small" data-action="integrity">' +
          esc(T("settings.check_quick")) + "</button>" +
          '<button class="btn ghost small" data-action="integrity_deep">' +
          esc(T("settings.check_deep")) + "</button>"
      ) +
        settingsRow(
          T("settings.clean_orphans"),
          T("settings.clean_orphans_hint"),
          '<button class="btn ghost small" data-action="fix_orphans">' +
            esc(T("settings.clean_orphans")) + "</button>"
        ) +
        settingsRow(
          T("settings.clear_stats"),
          T("settings.clear_stats_hint"),
          '<button class="btn danger-ghost small" data-action="clear_stats">' +
            esc(T("settings.clear_stats")) + "</button>"
        ) +
        settingsRow(
          T("settings.dirs"),
          T("settings.dirs_hint"),
          '<button class="btn ghost small" data-action="data_dir">' +
            esc(T("settings.data_dir")) + "</button>" +
            '<button class="btn ghost small" data-action="log_dir">' +
            esc(T("settings.log_dir")) + "</button>"
        )
    )
  );
}

function renderSettings(animate) {
  qsa(".settings-tab").forEach(function (tab) {
    tab.classList.toggle("is-active", tab.dataset.settings === state.settingsTab);
  });
  const body = qs("#settings-body");
  if (!state.data) return;
  if (state.settingsTab === "import") body.innerHTML = settingsImport();
  else if (state.settingsTab === "simple") body.innerHTML = settingsSimple();
  else if (state.settingsTab === "player") body.innerHTML = settingsPlayer();
  else if (state.settingsTab === "maintenance") body.innerHTML = settingsMaintenance();
  else body.innerHTML = settingsGeneral();

  if (animate) {
    body.classList.remove("is-entering");
    void body.offsetWidth;
    body.classList.add("is-entering");
  }
}

function settingValue(path) {
  return path.split(".").reduce(function (node, key) {
    return node && typeof node === "object" ? node[key] : undefined;
  }, state.data.settings);
}

async function patchSetting(path, value) {
  const parts = path.split(".");
  const patch = {};
  let node = patch;
  parts.forEach(function (key, index) {
    if (index === parts.length - 1) node[key] = value;
    else {
      node[key] = {};
      node = node[key];
    }
  });
  const data = await call("update_settings", patch);
  if (!data) return;
  if (data.ok === false) {
    apply(data);
    return;
  }
  // 开关和滑块本身就是最终状态，不需要重绘；重绘会把正在播的过渡直接换掉，
  // 也会把设置页的滚动位置弹回顶部。
  if (data.settings) state.data.settings = data.settings;
  if (data.status) state.data.status = data.status;

  // 后端可能夹取数值（比如 base 上限 0.99），这时输入框要跟着回正。
  let actual = data.settings;
  parts.forEach(function (key) {
    actual = actual && typeof actual === "object" ? actual[key] : undefined;
  });
  if (actual !== value) apply(data);
}

async function browseImportDir() {
  const picked = await call("browse_folder");
  if (!picked || !picked.path) return;
  const data = await call("update_settings", { import: { dir: picked.path } });
  if (data) apply(data);
}

async function refreshStatus() {
  const data = await call("refresh_status");
  if (data) apply(data);
}

function confirmFixOrphans() {
  openModal({
    title: T("settings.clean_orphans"),
    body: '<p class="modal-note">' + esc(T("settings.clean_orphans_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("settings.clean_orphans"),
        danger: true,
        onClick: async function () {
          const data = await call("fix_issues", "orphan_file");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function confirmClearStats() {
  openModal({
    title: T("settings.clear_stats"),
    body: '<p class="modal-note">' + esc(T("settings.clear_stats_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("settings.clear_stats"),
        danger: true,
        onClick: async function () {
          const data = await call("clear_all_stats");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

/* ---------- 菜单 ---------- */

function songMenuItems(music) {
  return [
    {
      label: T("audition.play"),
      onClick: function () {
        auditionPlay(music.md5);
      },
    },
    {
      label: T("action.manage_aliases"),
      onClick: function () {
        openAliasEditor(music);
      },
    },
    {
      label: T("song.replace_source"),
      onClick: function () {
        replaceSource(music);
      },
    },
    {
      label: T("song.delete"),
      onClick: function () {
        confirmDeleteSongs([music.md5]);
      },
    },
  ];
}

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

  const width = menu.offsetWidth;
  const height = menu.offsetHeight;
  let left;
  let top;
  if (anchor && typeof anchor.x === "number") {
    left = anchor.x;
    top = anchor.y;
  } else {
    const rect = anchor.getBoundingClientRect();
    left = rect.right - width;
    top = rect.bottom + 4;
  }
  left = Math.min(Math.max(8, left), window.innerWidth - width - 8);
  top = Math.min(Math.max(8, top), window.innerHeight - height - 8);
  menu.style.left = left + "px";
  menu.style.top = top + "px";

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
let modalTimer = null;

function closeModal() {
  if (!modalDismissible) return;
  const modal = qs("#modal");
  if (modal.hidden) return;
  modalDismissible = true;
  qs("#app").inert = false;
  modal.classList.add("is-closing");
  window.clearTimeout(modalTimer);
  modalTimer = window.setTimeout(function () {
    modal.hidden = true;
    modal.classList.remove("is-closing");
    qs("#modal-body").innerHTML = "";
    qs("#modal-actions").innerHTML = "";
  }, 160);
}

function openModal(options) {
  const modal = qs("#modal");
  const card = qs("#modal-card");
  window.clearTimeout(modalTimer);
  modal.classList.remove("is-closing");
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

function confirmDeleteSongs(md5s) {
  const list = (md5s || []).filter(function (md5) {
    return Boolean(musicByMd5(md5));
  });
  if (!list.length) return;
  const one = list.length === 1 ? musicByMd5(list[0]) : null;
  const text = one
    ? T("song.delete_confirm", { title: one.title })
    : T("song.delete_batch_confirm", { count: list.length });

  openModal({
    title: one ? T("song.delete") : T("song.delete_batch", { count: list.length }),
    body: '<p class="modal-note">' + esc(text) + "</p>",
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

/* ---------- 完整性检查 ---------- */

function integrityBody(report) {
  if (report.ok) {
    return (
      '<div class="empty" style="min-height:200px"><h2>' + esc(T("integrity.ok")) + "</h2></div>"
    );
  }
  return (
    '<p class="modal-note">' + esc(T("integrity.count", { count: report.count })) + "</p>" +
    report.sections
      .map(function (section) {
        const items = section.items
          .map(function (item) {
            return "<li>" + esc(item) + "</li>";
          })
          .join("");
        const fix = section.fixable
          ? '<button class="btn soft small report-fix" data-fix="' + esc(section.key) + '">' +
            esc(T("integrity.fix")) + "</button>"
          : "";
        return (
          '<div class="report-section"><h3 class="report-title">' +
          esc(T("integrity." + section.key)) +
          '<span class="report-count">' + section.items.length + "</span>" +
          fix +
          '</h3><ul class="report-list">' + items + "</ul></div>"
        );
      })
      .join("")
  );
}

async function runDeepCheck() {
  const started = await call("start_integrity", true);
  if (!started || !started.task_id) return null;
  const taskId = started.task_id;

  return new Promise(function (resolve) {
    openModal({
      title: T("integrity.title"),
      body:
        '<p class="progress-text" id="deep-line"></p>' +
        '<div class="progress"><div class="progress-bar" id="deep-bar"></div></div>',
      dismissible: false,
      actions: [
        {
          label: T("integrity.cancel"),
          onClick: function () {
            call("cancel_task", taskId);
          },
        },
      ],
    });

    async function poll() {
      const task = await call("poll_task", taskId);
      if (!task) {
        modalDismissible = true;
        resolve(null);
        return;
      }
      if (task.state === "running") {
        const percent = task.total ? Math.round((task.done / task.total) * 100) : 0;
        const line = qs("#deep-line");
        const bar = qs("#deep-bar");
        if (line) {
          line.textContent = T("integrity.running", {
            done: formatSize(task.done),
            total: formatSize(task.total),
          });
        }
        if (bar) bar.style.width = percent + "%";
        window.setTimeout(poll, 250);
        return;
      }
      modalDismissible = true;
      if (task.state === "cancelled") {
        resolve(null);
        return;
      }
      resolve(task.result || null);
    }

    poll();
  });
}

async function openIntegrity(options) {
  const settings = options || {};
  let report = settings.report || null;
  if (!report) {
    report = settings.deep ? await runDeepCheck() : await call("run_integrity");
  }
  if (!report) {
    closeModal();
    toast(T("integrity.cancelled"));
    return;
  }

  const fixable = report.sections.some(function (section) {
    return section.fixable;
  });
  const actions = [];
  if (fixable) {
    actions.push({
      label: T("integrity.fix_all"),
      primary: true,
      onClick: function () {
        fixIssues("");
      },
    });
  }
  actions.push({
    label: T("integrity.deep"),
    onClick: function () {
      openIntegrity({ deep: true });
    },
  });
  actions.push({ label: T("action.close"), primary: !fixable, onClick: closeModal });

  openModal({
    title: T("integrity.title"),
    body: integrityBody(report),
    wide: true,
    actions: actions,
    onMount: function () {
      qsa("[data-fix]").forEach(function (button) {
        button.addEventListener("click", function () {
          fixIssues(button.dataset.fix);
        });
      });
    },
  });
}

async function fixIssues(kind) {
  const data = await call("fix_issues", kind);
  if (!data) return;
  apply(data);
  toast(data.message || T("integrity.fixed", { count: 0 }), true);
  openIntegrity();
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
      else if (name === "log_dir") call("open_log_dir");
      else if (name === "integrity") openIntegrity();
      else if (name === "integrity_deep") openIntegrity({ deep: true });
      else if (name === "fix_orphans") confirmFixOrphans();
      else if (name === "clear_stats") confirmClearStats();
      else if (name === "browse_import_dir") browseImportDir();
      else if (name === "clear_import_dir") patchSetting("import.dir", "");
      else if (name === "refresh_status") refreshStatus();
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
      const value = key === "base" ? Number(field.value) : parseInt(field.value, 10);
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

  /* ---------- 标签页 ---------- */

  qs("#btn-new-tag-group").addEventListener("click", openCreateTagGroup);

  qs("#tag-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-tag-group]");
    if (row) selectTagGroup(row.dataset.tagGroup);
  });

  qs("#tag-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-tag-group]");
    if (!row) return;
    event.preventDefault();
    const group = tagGroupByUid(row.dataset.tagGroup);
    if (!group) return;
    if (state.active !== group.uid) selectTagGroup(group.uid);
    openMenu({ x: event.clientX, y: event.clientY }, [
      {
        label: T("tag.delete_group"),
        onClick: function () {
          confirmDeleteTagGroup(group);
        },
      },
    ]);
  });

  const tagSearch = qs("#tags-search");
  tagSearch.addEventListener("input", function () {
    state.tagQuery = tagSearch.value;
    qs("#tags-search-clear").hidden = !tagSearch.value;
    renderTagList();
  });
  qs("#tags-search-clear").addEventListener("click", function () {
    tagSearch.value = "";
    state.tagQuery = "";
    qs("#tags-search-clear").hidden = true;
    renderTagList();
    tagSearch.focus();
  });

  const tagDetail = qs("#tag-detail");

  tagDetail.addEventListener("change", async function (event) {
    const group = tagGroupByUid(state.active);
    if (!group) return;
    if (event.target.id === "tag-group-name") {
      const value = event.target.value.trim();
      if (!value || value === group.name) {
        event.target.value = group.name;
        return;
      }
      const data = await call("update_tag_group", group.uid, { name: value });
      if (data) apply(data);
      return;
    }
    const tagInput = event.target.closest("[data-tag-name]");
    if (tagInput) {
      const value = tagInput.value.trim();
      if (!value || value === tagInput.dataset.tagOriginal) {
        tagInput.value = tagInput.dataset.tagOriginal;
        return;
      }
      const data = await call("rename_tag", group.uid, tagInput.dataset.tagName, value);
      if (data) apply(data);
    }
  });

  tagDetail.addEventListener("submit", async function (event) {
    if (event.target.id !== "tag-add-form") return;
    event.preventDefault();
    const group = tagGroupByUid(state.active);
    if (!group) return;
    const input = qs("#tag-new");
    const name = input.value.trim();
    if (!name) return;
    const data = await call("add_tag", group.uid, name);
    if (data) {
      apply(data);
      const again = qs("#tag-new");
      if (again) again.focus();
    }
  });

  tagDetail.addEventListener("click", async function (event) {
    const group = tagGroupByUid(state.active);
    if (!group) return;

    const toggle = event.target.closest("[data-switch]");
    if (toggle) {
      const next = toggle.getAttribute("aria-checked") !== "true";
      toggle.setAttribute("aria-checked", next ? "true" : "false");
      const patch = {};
      patch[toggle.dataset.switch] = next;
      const data = await call("update_tag_group", group.uid, patch);
      if (!data) return;
      await delay(170);
      apply(data);
      return;
    }

    const remove = event.target.closest("[data-tag-remove]");
    if (remove) {
      const data = await call("remove_tag", group.uid, remove.dataset.tagRemove);
      if (data) apply(data);
      return;
    }

    const menu = event.target.closest("[data-menu='tag']");
    if (menu) {
      openMenu(menu, [
        {
          label: T("tag.delete_group"),
          onClick: function () {
            confirmDeleteTagGroup(group);
          },
        },
      ]);
    }
  });

  /* ---------- 作者页 ---------- */

  qs("#btn-new-author").addEventListener("click", openCreateAuthor);

  qs("#author-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (row) selectAuthor(row.dataset.authorUid);
  });

  qs("#author-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (!row) return;
    event.preventDefault();
    const author = authorByUid(row.dataset.authorUid);
    if (!author) return;
    if (state.active !== author.uid) selectAuthor(author.uid);
    openMenu({ x: event.clientX, y: event.clientY }, [
      {
        label: T("author.move_up"),
        onClick: function () {
          moveAuthor(author.uid, -1);
        },
      },
      {
        label: T("author.move_down"),
        onClick: function () {
          moveAuthor(author.uid, 1);
        },
      },
      {
        label: T("author.delete"),
        onClick: function () {
          confirmDeleteAuthor(author);
        },
      },
    ]);
  });

  const authorSearch = qs("#authors-search");
  authorSearch.addEventListener("input", function () {
    state.authorQuery = authorSearch.value;
    qs("#authors-search-clear").hidden = !authorSearch.value;
    renderAuthorList();
  });
  qs("#authors-search-clear").addEventListener("click", function () {
    authorSearch.value = "";
    state.authorQuery = "";
    qs("#authors-search-clear").hidden = true;
    renderAuthorList();
    authorSearch.focus();
  });

  const authorList = qs("#author-list");

  authorList.addEventListener("dragstart", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (!row) return;
    state.dragAuthor = row.dataset.authorUid;
    row.classList.add("is-dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", state.dragAuthor);
    }
  });

  authorList.addEventListener("dragover", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (!row || !state.dragAuthor) return;
    event.preventDefault();
    qsa("[data-author-uid]", authorList).forEach(function (node) {
      node.classList.remove("drop-before", "drop-after");
    });
    const rect = row.getBoundingClientRect();
    row.classList.add(event.clientY > rect.top + rect.height / 2 ? "drop-after" : "drop-before");
  });

  authorList.addEventListener("drop", async function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (!row || !state.dragAuthor) return;
    event.preventDefault();
    const after = row.classList.contains("drop-after");
    const order = qsa("[data-author-uid]", authorList).map(function (node) {
      return node.dataset.authorUid;
    });
    const from = order.indexOf(state.dragAuthor);
    if (from === -1) return;
    order.splice(from, 1);
    let index = order.indexOf(row.dataset.authorUid);
    if (index === -1) index = order.length;
    if (after) index += 1;
    order.splice(index, 0, state.dragAuthor);
    state.dragAuthor = null;
    const data = await call("reorder_authors", order);
    if (data) apply(data);
  });

  authorList.addEventListener("dragend", function () {
    state.dragAuthor = null;
    qsa("[data-author-uid]", authorList).forEach(function (node) {
      node.classList.remove("is-dragging", "drop-before", "drop-after");
    });
  });

  const authorDetail = qs("#author-detail");

  authorDetail.addEventListener("change", async function (event) {
    const author = authorByUid(state.active);
    if (!author) return;
    if (event.target.id === "author-name") {
      const value = event.target.value.trim();
      if (!value || value === author.name) {
        event.target.value = author.name;
        return;
      }
      const data = await call("update_author", author.uid, { name: value });
      if (data) apply(data);
      return;
    }
    if (event.target.id === "author-description") {
      const value = event.target.value.trim();
      if (value === (author.description || "")) return;
      const data = await call("update_author", author.uid, { description: value });
      if (data) apply(data);
    }
  });

  authorDetail.addEventListener("click", function (event) {
    const author = authorByUid(state.active);
    if (!author) return;

    const song = event.target.closest("[data-author-song]");
    if (song) {
      selectMusic(song.dataset.authorSong);
      return;
    }

    const menu = event.target.closest("[data-menu='author']");
    if (menu) {
      openMenu(menu, [
        {
          label: T("author.move_up"),
          onClick: function () {
            moveAuthor(author.uid, -1);
          },
        },
        {
          label: T("author.move_down"),
          onClick: function () {
            moveAuthor(author.uid, 1);
          },
        },
        {
          label: T("author.delete"),
          onClick: function () {
            confirmDeleteAuthor(author);
          },
        },
      ]);
    }
  });

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
    state.settingsTab = tab.dataset.settings;
    renderSettings(true);
  });

  const settingsBody = qs("#settings-body");

  settingsBody.addEventListener("click", async function (event) {
    const theme = event.target.closest("[data-theme-value]");
    if (theme) {
      const data = await call("set_theme", theme.dataset.themeValue);
      if (data) apply(data);
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
    if (event.target.id === "simple-volume") {
      await patchSetting("simple.volume", Number(event.target.value) / 100);
      return;
    }
    if (event.target.id === "audition-default") {
      await patchSetting("audition.volume", Number(event.target.value) / 100);
      return;
    }
    const field = event.target.closest("[data-default]");
    if (field) {
      const value = Number(field.value);
      if (!Number.isFinite(value)) {
        renderSettings();
        return;
      }
      await patchSetting("common.adaptation." + field.dataset.default, value);
    }
  });

  settingsBody.addEventListener("input", function (event) {
    if (event.target.id === "player-volume") {
      const label = qs("#player-volume-value");
      if (label) label.textContent = event.target.value + "%";
      return;
    }
    if (event.target.id === "simple-volume") {
      const label = qs("#simple-volume-value");
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

  qs("#drawer-close").addEventListener("click", closeDrawer);

  qs("#drawer-body").addEventListener("click", async function (event) {
    if (!state.drawer) return;
    if (event.target.closest("[data-reset-all]")) {
      confirmClearPlaylistStats();
      return;
    }
    const one = event.target.closest("[data-reset-md5]");
    if (one) {
      const data = await call("reset_stats", state.drawer, one.dataset.resetMd5);
      if (data) apply(data);
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
        toast(String(error), false);
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
