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
