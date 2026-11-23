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
  pickerOpen: false,
  pickerItems: [],
  pickerIndex: 0,
  pickerTimer: null,
  pickerCloseTimer: null,
  lastCurrent: null,
  //: 番茄钟详情里「只对本次生效」的改动；换一个番茄钟就清空。
  pomoOverrides: {},
  pomoDetailUid: null,
  pomoView: null,
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

/* ---------- 状态栏 ----------
   底部居中的圆角黑条，界面上唯一的临时提示出口。容器底边固定、条目往上堆，
   所以新的一条从下面出来时，已有的会自己上移一格；最多同时三条。 */

/** 记下每条现在的位置，等 DOM 改完再按位移补动画。 */
function toastSnapshot(root) {
  const map = new Map();
  for (const node of root.children) map.set(node, node.getBoundingClientRect().top);
  return map;
}

/** 把「被顶上去」的位移反向补回来再归零：看起来是往上挪了一格，而不是跳一格。 */
function toastSettle(map) {
  for (const entry of map) {
    const node = entry[0];
    if (!node.isConnected) continue;
    const delta = entry[1] - node.getBoundingClientRect().top;
    if (!delta) continue;
    node.style.transition = "none";
    node.style.transform = "translateY(" + delta + "px)";
    // 强制回流：否则下一帧的 transition 会从同一个值开始，等于没动。
    void node.offsetHeight;
    node.style.transition = "transform 0.2s var(--ease)";
    node.style.transform = "";
  }
}

/** 让一条原地脱离文档流再飘走，后面的条目不会跟着往下掉。 */
function toastRetire(node) {
  if (!node.isConnected) return;
  const rect = node.getBoundingClientRect();
  const ghost = node.cloneNode(true);
  ghost.classList.remove("is-entering", "is-leaving");
  ghost.style.position = "fixed";
  ghost.style.left = rect.left + "px";
  ghost.style.top = rect.top + "px";
  // 量出来的宽高要写死：离开容器后它是一块普通的 div，会撑满整行。
  ghost.style.width = rect.width + "px";
  ghost.style.height = rect.height + "px";
  ghost.style.margin = "0";
  ghost.style.pointerEvents = "none";
  ghost.style.animation = "toast-out 0.2s ease forwards";
  document.body.appendChild(ghost);
  window.setTimeout(function () {
    ghost.remove();
  }, 240);
  node.remove();
}

function toastDismiss(node) {
  if (!node.isConnected || node.classList.contains("is-leaving")) return;
  const map = toastSnapshot(node.parentElement);
  toastRetire(node);
  toastSettle(map);
}

/** 弹一条状态。``ok`` 为 false 时是错误样式，停留更久。 */
function toast(message, ok) {
  const root = qs("#toastRoot");
  const text = String(message === undefined || message === null ? "" : message).trim();
  if (!root || !text) return;

  const map = toastSnapshot(root);
  while (root.children.length >= 3) toastRetire(root.firstElementChild);

  const node = document.createElement("div");
  node.className = "toast" + (ok === false ? " error" : "");
  node.textContent = text;
  node.classList.add("is-entering");
  root.appendChild(node);
  toastSettle(map);

  window.setTimeout(function () {
    toastDismiss(node);
  }, ok === false ? 4200 : 2600);
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
/* ---------- 交互 ---------- */

/* 滚轮调音量：每格 1%。range 自己不吃滚轮，这里补上并挡掉页面滚动；
   停手 400ms 后补一次 change，复用控件原有的「写回配置」逻辑。 */
function bindWheelVolume(input) {
  if (!input) return;
  let timer = null;
  input.addEventListener(
    "wheel",
    function (event) {
      event.preventDefault();
      const step = event.deltaY < 0 ? 1 : -1;
      const min = Number(input.min) || 0;
      const max = Number(input.max) || 100;
      const next = Math.min(max, Math.max(min, Number(input.value) + step));
      if (next === Number(input.value)) return;
      input.value = String(next);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }, 400);
    },
    { passive: false }
  );
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

