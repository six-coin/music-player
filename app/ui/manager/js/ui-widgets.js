/* 通用控件：自绘下拉框、右键菜单、弹窗。 */
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
  refreshSortSelect();
  if (select.dataset.bound === "1") return;
  select.dataset.bound = "1";
  select.addEventListener("selectchange", function (event) {
    state.sort = event.detail.value;
    renderSongList();
  });
}

function sortOptions() {
  return [
    { value: "title", label: T("songs.sort_title") },
    { value: "created", label: T("songs.sort_created") },
    { value: "duration", label: T("songs.sort_duration") },
    { value: "author", label: T("songs.sort_author") },
  ];
}

/* 只重建文案，不动事件绑定：切换语言时要能再调一次，否则下拉框会一直停在
   建它时那种语言里。 */
function refreshSortSelect() {
  const select = qs("#songs-sort");
  if (!select) return;
  const options = sortOptions();
  select.querySelector(".select-menu").innerHTML = options
    .map(function (option) {
      return (
        '<button class="select-option' + (option.value === state.sort ? " active" : "") +
        '" type="button" role="option" data-value="' + esc(option.value) + '">' +
        esc(option.label) + "</button>"
      );
    })
    .join("");
  const current = options.find(function (option) {
    return option.value === state.sort;
  }) || options[0];
  select.dataset.value = current.value;
  select.querySelector(".select-value").textContent = current.label;
}
/* ---------- 拖拽排序 ---------- */

/* 列表拖拽排序：命中 options.row 的行可以互相拖动，松手时把新顺序交给
   options.commit。传了 options.handle 时只有按住手柄才能拖——行里有输入框
   时，整行可拖会把「选中文字」变成「拖走这一行」。 */
function bindDragSort(list, options) {
  if (!list) return;
  const selector = options.row;
  const keyOf = options.key;
  const commit = options.commit;
  const handle = options.handle || "";
  const allow = options.allow || null;
  let dragging = null;

  const clear = function () {
    qsa(selector, list).forEach(function (node) {
      node.classList.remove("is-dragging", "drop-before", "drop-after");
      if (handle) node.draggable = false;
    });
  };

  if (handle) {
    list.addEventListener("mousedown", function (event) {
      const grip = event.target.closest(handle);
      const row = grip ? grip.closest(selector) : null;
      if (row) row.draggable = true;
    });
    list.addEventListener("mouseup", clear);
  }

  list.addEventListener("dragstart", function (event) {
    const row = event.target.closest(selector);
    // 列表被搜索过滤过时不允许拖：这时 DOM 里只有一部分行，按它排会把
    // 没显示出来的那些甩到末尾去。
    if (!row || (allow && !allow())) {
      event.preventDefault();
      return;
    }
    dragging = keyOf(row);
    row.classList.add("is-dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", dragging);
    }
  });

  list.addEventListener("dragover", function (event) {
    const row = event.target.closest(selector);
    if (!row || dragging === null) return;
    event.preventDefault();
    qsa(selector, list).forEach(function (node) {
      node.classList.remove("drop-before", "drop-after");
    });
    const rect = row.getBoundingClientRect();
    row.classList.add(event.clientY > rect.top + rect.height / 2 ? "drop-after" : "drop-before");
  });

  list.addEventListener("drop", function (event) {
    const row = event.target.closest(selector);
    if (!row || dragging === null) return;
    event.preventDefault();
    const after = row.classList.contains("drop-after");
    const moved = dragging;
    dragging = null;
    const keys = qsa(selector, list).map(function (node) {
      return keyOf(node);
    });
    const from = keys.indexOf(moved);
    if (from === -1) return;
    keys.splice(from, 1);
    let index = keys.indexOf(keyOf(row));
    if (index === -1) index = keys.length;
    if (after) index += 1;
    keys.splice(index, 0, moved);
    commit(keys);
  });

  list.addEventListener("dragend", clear);
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
/* 点遮罩是否关闭：导入这类「正在干活」的弹窗必须由用户按按钮关，不能误触空白。 */
let modalBackdropClosable = true;
let modalTimer = null;

function closeModal(after) {
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
    // 关完再开下一个弹窗：先让淡出走完，接上的那个才会重新播一遍入场。
    if (typeof after === "function") after();
  }, 160);
}

function openModal(options) {
  const modal = qs("#modal");
  const card = qs("#modal-card");
  const body = qs("#modal-body");
  window.clearTimeout(modalTimer);
  modal.classList.remove("is-closing");
  closeMenu();
  qs("#app").inert = true;
  qs("#modal-title").textContent = options.title || "";
  body.innerHTML = options.body || "";
  // 上一步挂在这两个元素上的处理器必须一起清掉：批量导入向导换到第 3 步时，
  // 第 1 步的「删除某一行」处理器还留在 body 上，点哪都会跑一遍旧逻辑。
  body.onclick = null;
  body.oninput = null;
  qs("#modal-actions").innerHTML = "";

  (options.actions || []).forEach(function (action) {
    const button = document.createElement("button");
    button.className =
      "btn" + (action.primary ? " primary" : "") + (action.danger ? " danger" : "");
    button.textContent = action.label;
    button.addEventListener("click", function (event) {
      // 按钮是显式动作：弹窗不允许 Esc 关闭时，按钮仍然要能把它关掉。
      // 否则「必须读完的使用说明」会把首次运行卡死在这一屏。
      modalDismissible = true;
      action.onClick(event);
    });
    qs("#modal-actions").appendChild(button);
  });

  card.classList.toggle("wide", Boolean(options.wide));
  modalDismissible = options.dismissible !== false;
  modalBackdropClosable = options.backdropDismissible !== false;
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
