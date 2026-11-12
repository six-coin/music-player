/* 管理器的前端。没有框架、没有构建步骤：拉一次文案与快照，整体重绘。 */

const state = {
  data: null,
  strings: {},
  tab: "imported",
  sort: "title",
  query: "",
  active: null,
  serverSelection: null,
  selection: new Set(),
  anchor: null,
  taskId: null,
  nameTimer: null,
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
  else showView("pending");
  if (section !== "overview" && section !== "songs") {
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
  const music = state.active ? musicByMd5(state.active) : null;

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
    '<div class="field-row"><span class="field-label">' + esc(T("song.tags")) + "</span>" +
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

/* ---------- 总渲染 ---------- */

function apply(data) {
  if (!data) return;
  state.data = data;

  if (data.language) document.documentElement.lang = data.language;
  applyTheme(data.theme);
  applyNav(data.section || "overview");

  // 后端的选择变化（点击最近导入、导入后自动选中）要反映到详情区；
  // 同一份选择重复下发时不能覆盖前端的多选。
  const incoming =
    data.selection && data.selection.kind === "music" ? data.selection.uid : null;
  if (incoming !== state.serverSelection) {
    state.active = incoming;
    if (incoming) state.selection = new Set([incoming]);
  }
  state.serverSelection = incoming;

  if (!state.active || !musicByMd5(state.active)) {
    state.active = incoming && musicByMd5(incoming) ? incoming : null;
  }
  state.selection.forEach(function (md5) {
    if (!musicByMd5(md5)) state.selection.delete(md5);
  });

  if (data.section === "overview") renderOverview(data);
  else if (data.section === "songs") renderSongs();

  if (data.message) toast(data.message, data.ok !== false);
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
}

async function selectMusic(md5) {
  state.active = md5;
  state.selection = new Set([md5]);
  state.anchor = md5;
  renderSongs();
  const data = await call("select_item", "music", md5);
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
  modalDismissible = true;
}

function openModal(options) {
  const modal = qs("#modal");
  const card = qs("#modal-card");
  qs("#modal-title").textContent = options.title || "";
  qs("#modal-body").innerHTML = options.body || "";
  qs("#modal-body").onclick = null;
  qs("#modal-actions").innerHTML = "";

  (options.actions || []).forEach(function (action) {
    const button = document.createElement("button");
    button.className = "btn" + (action.primary ? " primary" : "");
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
  const started = await call("start_import", result.paths);
  if (!started || !started.task_id) return;
  state.taskId = started.task_id;
  openImportModal(started.task_id);
}

function openImportModal(taskId) {
  openModal({
    title: T("import.title"),
    body:
      '<p class="progress-text" id="import-line"></p>' +
      '<div class="progress"><div class="progress-bar" id="import-bar"></div></div>' +
      '<div id="import-errors"></div>',
    dismissible: false,
    actions: [],
  });

  async function poll() {
    const task = await call("poll_task", taskId);
    if (!task) return;

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

    qs("#import-line").textContent = T("import.done");
    qs("#import-bar").style.width = "100%";
    const failed = task.errors.length;
    const okCount = task.imported.length;
    const summary = document.createElement("p");
    summary.className = "modal-note";
    summary.textContent = T("import.summary", { ok: okCount, failed: failed });
    qs("#import-errors").appendChild(summary);

    if (failed) {
      const list = document.createElement("ul");
      list.className = "report-list";
      task.errors.forEach(function (item) {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
      qs("#import-errors").appendChild(list);
    }

    const actions = qs("#modal-actions");
    const button = document.createElement("button");
    button.className = "btn primary";
    button.textContent = T("action.close");
    button.addEventListener("click", closeModal);
    actions.appendChild(button);
    modalDismissible = true;
    qs("#modal-close").hidden = false;

    const data = await call("get_state");
    if (data) apply(data);

    if (task.imported.length) {
      const selected = await call("select_item", "music", task.imported[0]);
      if (selected) apply(selected);
    }
  }

  poll();
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

  qs("#songs-sort").addEventListener("change", function (event) {
    state.sort = event.target.value;
    renderSongList();
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
  await loadStrings();
  applyStrings();
  apply(await call("get_state"));
}

if (bridge()) {
  init();
} else {
  window.addEventListener("pywebviewready", init, { once: true });
}
