/* 基础设施：状态、<audio> 引用、DOM 选择器、JS 桥、文案、格式化、主题。 */
const state = {
  data: null,
  strings: {},
  commandSeq: 0,
  noticeSeq: 0,
  playedMs: 0,
  lastTick: 0,
  ticks: 0,
  draggingSeek: false,
  autoplay: false,
  pendingSeek: null,
  failedFor: null,
  trackMd5: null,
  startTimer: null,
  noticeTimer: null,
  pickerOpen: false,
  pickerItems: [],
  pickerIndex: 0,
  pickerTimer: null,
  pickerCloseTimer: null,
  lastCurrent: null,
  //: 番茄钟详情里「只对本次生效」的改动；换一个番茄钟就清空。
  pomoOverrides: {},
  pomoDetailUid: null,
};

const audio = document.getElementById("audio");
/* ---------- 基础 ---------- */

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
    return null;
  }
}
/* ---------- 文案 ---------- */

function T(key, values) {
  const template = state.strings[key];
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
/* ---------- 快捷键 ---------- */

/* 与 app/keymap.py 的 DEFAULTS["player"] 对应。快照总会带上设置里的真实绑定，
   这张表只是桥接就绪之前那一下的兜底。写法必须与 Python 侧一致（规范形式）。 */
const KEY_DEFAULTS = {
  play_pause: "Space",
  next: "Ctrl+C",
  prev: "Ctrl+ArrowLeft",
  seek_back: "ArrowLeft",
  seek_forward: "ArrowRight",
  volume_up: "ArrowUp",
  volume_down: "ArrowDown",
  queue: "Escape",
  pick_loop: "Ctrl+L",
};

const KEY_PRETTY = {
  ArrowLeft: "←",
  ArrowRight: "→",
  ArrowUp: "↑",
  ArrowDown: "↓",
  Escape: "Esc",
  Delete: "Del",
  PageUp: "PgUp",
  PageDown: "PgDn",
};

const MODIFIER_KEYS = ["Control", "Shift", "Alt", "Meta"];

function playerKeys() {
  const saved = (state.data && state.data.keys) || {};
  const table = {};
  Object.keys(KEY_DEFAULTS).forEach(function (id) {
    table[id] = saved[id] || KEY_DEFAULTS[id];
  });
  return table;
}

/* 一次按键压成与设置文件同一种写法：Ctrl → Alt → Shift → 主键。 */
function keySpec(event) {
  const raw = event.key === " " || event.key === "Spacebar" ? "Space" : event.key;
  if (!raw || MODIFIER_KEYS.indexOf(raw) !== -1) return "";
  const parts = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  parts.push(raw.length === 1 && /[a-z]/i.test(raw) ? raw.toUpperCase() : raw);
  return parts.join("+");
}

function prettyKey(spec) {
  return String(spec || "")
    .split("+")
    .map(function (part) {
      return KEY_PRETTY[part] || part;
    })
    .join("+");
}

function matchKey(event, spec) {
  return !!spec && keySpec(event) === spec;
}
/* ---------- 主题 ---------- */

function applyTheme(theme) {
  if (!theme) return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem("theme", theme);
  } catch (error) {
    /* 写不了就只影响下次首帧，忽略 */
  }
}

