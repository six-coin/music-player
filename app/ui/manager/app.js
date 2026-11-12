/* 管理器的前端。没有框架、没有构建步骤：拉一次文案与快照，整体重绘。 */

const state = {
  data: null,
  strings: {},
  tab: "imported",
};

function qs(selector, root) {
  return (root || document).querySelector(selector);
}

function qsa(selector, root) {
  return Array.prototype.slice.call((root || document).querySelectorAll(selector));
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

function formatTime(at, now) {
  if (!at) return "";
  const diff = Math.max(0, (now || Math.floor(Date.now() / 1000)) - at);
  if (diff < 60) return T("time.just_now");
  if (diff < 3600) return T("time.minutes_ago", { count: Math.floor(diff / 60) });
  if (diff < 86400) return T("time.hours_ago", { count: Math.floor(diff / 3600) });
  if (diff < 86400 * 7) return T("time.days_ago", { count: Math.floor(diff / 86400) });
  const date = new Date(at * 1000);
  return date.getFullYear() + "/" + pad(date.getMonth() + 1) + "/" + pad(date.getDate());
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

function applyNav(section) {
  qsa(".rail-item").forEach(function (item) {
    item.classList.toggle("is-active", item.dataset.section === section);
  });

  const overview = qs('[data-view="overview"]');
  const pending = qs('[data-view="pending"]');
  const isOverview = section === "overview";
  overview.classList.toggle("is-hidden", !isOverview);
  pending.classList.toggle("is-hidden", isOverview);
  if (!isOverview) {
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
    const empty = document.createElement("li");
    empty.className = "row-empty";
    empty.textContent = T("overview.recent_empty");
    list.appendChild(empty);
    return;
  }

  items.forEach(function (item) {
    const row = document.createElement("li");
    row.className = "row";

    const body = document.createElement("div");
    body.className = "row-body";

    const title = document.createElement("span");
    title.className = "row-title";
    title.textContent = item.title || "";

    const sub = document.createElement("span");
    sub.className = "row-sub";
    sub.textContent = item.subtitle || "";

    body.appendChild(title);
    if (item.subtitle) body.appendChild(sub);

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
    const empty = document.createElement("li");
    empty.className = "row-empty";
    empty.textContent = T("overview.issues_clear");
    list.appendChild(empty);
    return;
  }

  issues.forEach(function (issue) {
    const row = document.createElement("li");
    row.className = "row";

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
  qs("#stats").hidden = false;
}

function apply(data) {
  if (!data) return;
  state.data = data;

  if (data.language) document.documentElement.lang = data.language;
  applyTheme(data.theme);
  applyNav(data.section || "overview");
  renderSummary(data);
  renderStats(data);
  renderRecent(data);
  renderIssues(data);
  renderEmpty(data);

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

function bindEvents() {
  qsa(".rail-item").forEach(function (item) {
    item.addEventListener("click", async function () {
      const section = item.dataset.section;
      applyNav(section);
      const data = await call("select_section", section);
      if (data) apply(data);
    });
  });

  qsa(".stat").forEach(function (card) {
    card.addEventListener("click", async function () {
      const section = card.dataset.target;
      applyNav(section);
      const data = await call("select_section", section);
      if (data) apply(data);
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
