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
  //: 番茄分区：分组折叠状态、正在试听的资源、名称防抖。
  pomoCollapsed: {},
  pomoAuditionUid: null,
  pomoNameTimer: null,
  //: 正在录制快捷键的那一行；非空时全局按键只服务录制。
  recording: null,
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

/* 播放记录要看到几点几分：只给日期分不清上午与下午的两轮。 */
function formatDateTime(seconds) {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  return formatDate(seconds) + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
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

/* 详情区整块重绘会顺手丢掉滚动位置和焦点：调一下设置页就跳回顶部、
   输入框失焦，看起来像整页蹦了一下。重绘前后把这些状态接回去。 */
function setPaneHTML(pane, html) {
  if (!pane) return;
  if (pane.__html === html) return; // 快照变了但这一屏没变：连重绘都省了
  pane.__html = html;
  const scroll = pane.scrollTop;
  pane.innerHTML = html;
  if (scroll && pane.scrollTop !== scroll) pane.scrollTop = scroll;
}

function focusSelector(node) {
  if (!node || node === document.body || !node.getAttribute) return null;
  if (node.id) return "#" + node.id;
  const attrs = Array.prototype.slice.call(node.attributes || []);
  for (let index = 0; index < attrs.length; index += 1) {
    const attr = attrs[index];
    if (attr.name.indexOf("data-") !== 0 || !attr.value) continue;
    const selector = "[" + attr.name + '="' + attr.value.replace(/["\\]/g, "\\$&") + '"]';
    let found;
    try {
      found = document.querySelectorAll(selector);
    } catch (error) {
      continue;
    }
    if (found.length === 1) return selector;
  }
  return null;
}

function captureView() {
  const active = document.activeElement;
  const focus =
    active && active !== document.body
      ? {
          selector: focusSelector(active),
          start: typeof active.selectionStart === "number" ? active.selectionStart : null,
          end: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
        }
      : null;
  const scrolls = qsa(
    ".detail-pane, .list-pane, .song-list, .view, .settings-body, .pomodoro-nav"
  ).map(function (node) {
    return [node, node.scrollTop];
  });
  return { focus: focus, scrolls: scrolls };
}

function restoreView(snapshot, keepFocus) {
  if (!snapshot) return;
  snapshot.scrolls.forEach(function (entry) {
    if (entry[0].isConnected && entry[0].scrollTop !== entry[1]) entry[0].scrollTop = entry[1];
  });
  const focus = keepFocus ? snapshot.focus : null;
  if (!focus || !focus.selector) return;
  const node = qs(focus.selector);
  if (!node || node === document.activeElement) return;
  node.focus({ preventScroll: true });
  if (focus.start !== null && node.setSelectionRange) {
    try {
      node.setSelectionRange(focus.start, focus.end);
    } catch (error) {
      /* number 输入不支持选区，忽略 */
    }
  }
}

function applyTheme(theme) {
  if (!theme) return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem("theme", theme);
  } catch (error) {
    /* 隐私模式下写不了，忽略 */
  }
}
/* ---------- 快捷键 ---------- */

/* 写法与 app/keymap.py 一致：Ctrl → Alt → Shift → 主键。设置页录下来的组合
   原样交给后端，后端用同一个函数认，所以两边不会各说各话。 */
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

/* 管理器自己的按键：跟着设置走，缺了就不响应。 */
function managerKeys() {
  const section = (state.data && state.data.settings && state.data.settings.manager) || {};
  return section.keys || {};
}
/* ---------- 交互 ---------- */

/* 状态栏：底部居中的圆角黑条，界面上唯一的临时提示出口。容器底边固定、条目
   往上堆，所以新的一条从下面出来时，已有的会自己上移一格；最多同时三条。 */

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
