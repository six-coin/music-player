/* 概览页与总渲染入口：快照进来，先切视图，再把概览画出来。 */

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
  else if (section === "pomodoro") showView("pomodoro");
  else if (section === "settings") showView("settings");
  else showView("pending");
  if (section === "settings") renderSettings();
  if (section !== "playlists") closeDrawer();
  // 离开番茄分区时把内嵌试听停掉：它不属于底部试听条，没人会替它收尾。
  if (section !== "pomodoro") stopPomodoroAudition();
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
/* ---------- 总渲染 ---------- */

function apply(data) {
  if (!data) return;
  const previousLanguage = state.data ? state.data.language : null;
  state.data = data;

  if (data.language) document.documentElement.lang = data.language;
  // 语言变了：下拉框的选项文案是建菜单时写进去的，必须跟着重建一次。
  if (data.language && data.language !== previousLanguage) refreshSortSelect();
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
  else if (data.section === "pomodoro") renderPomodoros();
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
  if (kind === "pomodoro") return pomodoroItemByUid(uid);
  if (kind === "duration_mode") return pomodoroModeByUid(uid);
  if (kind === "background") return pomodoroBackgroundByUid(uid);
  if (kind === "ring") return pomodoroRingByUid(uid);
  if (kind === "environment") return pomodoroEnvironmentByUid(uid);
  return null;
}
