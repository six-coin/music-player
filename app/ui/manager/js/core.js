/* 基础设施：全局状态、DOM 选择器、JS 桥、文案、格式化、主题、Toast。 */
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
    // 异常路径不走语言包：这里看到的是 Python 抛出来的原始原因，中文前缀够定位了。
    console.error(method, error);
    toast("操作失败：" + String(error), false);
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

/* 作者不提供手动排序，展示时一律按名称。后端已经按名称排过一遍，这里再用
   界面语言的规则排一次：中文按拼音走，与歌曲列表用的是同一条规则。 */
function sortedAuthors() {
  return ((state.data && state.data.library.authors) || []).slice().sort(function (a, b) {
    return a.name.localeCompare(b.name, "zh-CN");
  });
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
