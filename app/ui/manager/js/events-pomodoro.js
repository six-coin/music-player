/* 番茄分区的事件绑定：分组列表、详情、拖拽、内嵌试听。 */
/* 三处描述框（番茄钟 / 时长模式 / 资源）共用一套保存逻辑。 */
function isPomodoroDescription(node) {
  if (!node || !node.matches) return false;
  return node.matches(
    "[data-pomo-description], [data-pomo-mode-description], [data-pomo-asset-description]"
  );
}

function bindPomodoroEvents() {
  const nav = qs("#pomodoro-nav");
  const detail = qs("#pomodoro-detail");
  if (!nav || !detail) return;

  nav.addEventListener("click", function (event) {
    if (event.target.closest("[data-pomodoro-overview]")) {
      selectPomodoroOverview();
      return;
    }
    const toggle = event.target.closest("[data-pomo-toggle]");
    if (toggle) {
      const kind = toggle.dataset.pomoToggle;
      state.pomoCollapsed[kind] = !state.pomoCollapsed[kind];
      renderPomodoroNav();
      return;
    }
    const add = event.target.closest("[data-pomo-add]");
    if (add) {
      const kind = add.dataset.pomoAdd;
      if (kind === "pomodoro") openCreatePomodoro();
      else if (kind === "duration_mode") openCreateDurationMode();
      else importPomodoroAsset(kind);
      return;
    }
    const row = event.target.closest("[data-pomo-row]");
    if (row) {
      selectPomodoroItem(row.dataset.pomoKind, row.dataset.pomoUid);
    }
  });

  nav.addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-pomo-row]");
    if (!row) return;
    event.preventDefault();
    const kind = row.dataset.pomoKind;
    const uid = row.dataset.pomoUid;
    if (state.active !== uid || state.activeKind !== kind) {
      selectPomodoroItem(kind, uid);
    }
    openPomodoroMenu(kind, uid, { x: event.clientX, y: event.clientY });
  });

  nav.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest("[data-pomo-row]");
    if (!row) return;
    event.preventDefault();
    selectPomodoroItem(row.dataset.pomoKind, row.dataset.pomoUid);
  });

  detail.addEventListener("click", function (event) {
    const menu = event.target.closest("[data-menu='pomodoro']");
    if (menu) {
      openPomodoroMenu(menu.dataset.pomoMenuKind, menu.dataset.pomoMenuUid, menu);
      return;
    }
    const goto = event.target.closest("[data-pomo-goto]");
    if (goto) {
      selectPomodoroItem("pomodoro", goto.dataset.pomoGoto);
      return;
    }
    if (event.target.closest("[data-pomo-add-segment]")) {
      pomodoroAddSegment();
      return;
    }
    const remove = event.target.closest("[data-pomo-remove-segment]");
    if (remove) {
      pomodoroRemoveSegment(Number(remove.dataset.pomoRemoveSegment));
      return;
    }
    if (event.target.closest("[data-pomo-audition-toggle]")) {
      togglePomodoroAudition();
      return;
    }
    const toggle = event.target.closest("button[role='switch'][data-pomo-field]");
    if (toggle) {
      const next = toggle.getAttribute("aria-checked") !== "true";
      toggle.setAttribute("aria-checked", next ? "true" : "false");
      pomodoroPatchField(toggle.dataset.pomoPhase, toggle.dataset.pomoField, next);
    }
  });

  detail.addEventListener("selectchange", function (event) {
    const select = event.target.closest("[data-pomo-field]");
    if (!select) return;
    pomodoroPatchField(
      select.dataset.pomoPhase,
      select.dataset.pomoField,
      event.detail.value
    );
  });

  detail.addEventListener("change", function (event) {
    const segment = event.target.closest("[data-pomo-segment-minutes]");
    if (segment) {
      pomodoroUpdateSegment(
        Number(segment.dataset.pomoSegmentMinutes),
        Number(segment.value)
      );
      return;
    }
    if (isPomodoroDescription(event.target)) {
      savePomodoroDescription(event.target);
      return;
    }
    if (event.target.matches("[data-pomo-audition-seek]")) {
      seekPomodoroAudition(event.target.value);
    }
  });

  detail.addEventListener("input", function (event) {
    if (
      event.target.id === "pomodoro-name" ||
      event.target.id === "pomodoro-mode-name" ||
      event.target.id === "pomodoro-asset-name"
    ) {
      schedulePomodoroNameSave(event.target);
      return;
    }
    if (isPomodoroDescription(event.target)) {
      schedulePomodoroDescriptionSave(event.target);
      return;
    }
    if (event.target.matches("[data-pomo-audition-seek]")) {
      seekPomodoroAudition(event.target.value);
    }
  });

  detail.addEventListener(
    "blur",
    function (event) {
      if (
        event.target.id === "pomodoro-name" ||
        event.target.id === "pomodoro-mode-name" ||
        event.target.id === "pomodoro-asset-name"
      ) {
        flushPomodoroNameSave();
      }
      if (isPomodoroDescription(event.target)) {
        savePomodoroDescription(event.target);
      }
    },
    true
  );

  bindPomodoroGroupDrag(nav);

  // 段编辑：按住左边的手柄拖，顺序写回 segments。
  bindDragSort(detail, {
    row: "[data-pomo-segment-row]",
    handle: "[data-pomo-segment-grip]",
    key: function (node) {
      return node.dataset.pomoSegment;
    },
    commit: pomodoroReorderSegments,
  });

  const audio = qs("#pomo-audition");
  if (audio) {
    ["play", "pause", "ended", "timeupdate", "loadedmetadata", "emptied"].forEach(function (name) {
      audio.addEventListener(name, syncPomodoroAudition);
    });
  }
}

async function selectPomodoroOverview() {
  const same = state.activeKind === "pomodoro_overview";
  const data = await call("select_pomodoro_overview");
  if (!data) return;
  apply(data);
  if (!same) animateDetail("pomodoro-detail");
}

async function selectPomodoroItem(kind, uid) {
  const same = state.activeKind === kind && state.active === uid;
  const data = await call("select_item", kind, uid);
  if (!data) return;
  apply(data);
  if (!same) animateDetail("pomodoro-detail");
}

function pomodoroPatchField(phase, field, value) {
  if (!state.active || state.activeKind !== "pomodoro") return;
  const patch = {};
  if (phase) {
    patch[phase] = {};
    patch[phase][field] = value;
  } else {
    patch[field] = value;
  }
  call("update_pomodoro", state.active, patch).then(function (data) {
    if (data) apply(data);
  });
}

let pomodoroDescriptionTimer = null;
let pomodoroDescriptionInput = null;

function schedulePomodoroDescriptionSave(input) {
  window.clearTimeout(pomodoroDescriptionTimer);
  pomodoroDescriptionInput = input;
  pomodoroDescriptionTimer = window.setTimeout(function () {
    pomodoroDescriptionTimer = null;
    pomodoroDescriptionInput = null;
    savePomodoroDescription(input);
  }, 420);
}

/* 关窗时调用：把还在防抖窗口里的那段描述写下去。 */
function flushPomodoroDescriptionSave() {
  if (!pomodoroDescriptionTimer) return;
  window.clearTimeout(pomodoroDescriptionTimer);
  pomodoroDescriptionTimer = null;
  const input = pomodoroDescriptionInput;
  pomodoroDescriptionInput = null;
  if (input) savePomodoroDescription(input);
}

async function savePomodoroDescription(input) {
  if (!input) return;
  window.clearTimeout(pomodoroDescriptionTimer);
  pomodoroDescriptionTimer = null;
  pomodoroDescriptionInput = null;
  const value = input.value;
  if (input.dataset.pomoDescription) {
    await call("update_pomodoro", input.dataset.pomoDescription, { description: value });
  } else if (input.dataset.pomoModeDescription) {
    await call("update_duration_mode", input.dataset.pomoModeDescription, {
      description: value,
    });
  } else if (input.dataset.pomoAssetDescription) {
    await call(
      "update_pomodoro_asset",
      input.dataset.pomoAssetKind,
      input.dataset.pomoAssetDescription,
      { description: value }
    );
  }
}

/* 分组内拖拽：只允许同组，松手时把这一组的 uid 顺序交给后端。 */
function bindPomodoroGroupDrag(host) {
  let dragKind = null;
  let dragUid = null;
  let dragRow = null;

  const clear = function () {
    dragKind = null;
    dragUid = null;
    dragRow = null;
    qsa("[data-pomo-row]", host).forEach(function (node) {
      node.classList.remove("is-dragging", "drop-before", "drop-after");
    });
  };

  host.addEventListener("dragstart", function (event) {
    const row = event.target.closest("[data-pomo-row]");
    if (!row) return;
    dragKind = row.dataset.pomoKind;
    dragUid = row.dataset.pomoUid;
    dragRow = row;
    row.classList.add("is-dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", dragUid);
    }
  });

  host.addEventListener("dragover", function (event) {
    const row = event.target.closest("[data-pomo-row]");
    if (!row || !dragKind || row.dataset.pomoKind !== dragKind) return;
    event.preventDefault();
    qsa("[data-pomo-row]", host).forEach(function (node) {
      node.classList.remove("drop-before", "drop-after");
    });
    const rect = row.getBoundingClientRect();
    row.classList.add(event.clientY > rect.top + rect.height / 2 ? "drop-after" : "drop-before");
  });

  host.addEventListener("drop", function (event) {
    const row = event.target.closest("[data-pomo-row]");
    if (!row || !dragKind || row.dataset.pomoKind !== dragKind) return;
    event.preventDefault();
    const after = row.classList.contains("drop-after");
    const group = row.closest("[data-pomo-group]");
    const nodes = group ? qsa("[data-pomo-row]", group) : [];
    const from = nodes.indexOf(dragRow);
    const target = nodes.indexOf(row);
    if (from === -1 || target === -1 || from === target) {
      clear();
      return;
    }
    let index = target + (after ? 1 : 0);
    if (from < index) index -= 1;
    if (index === from) {
      clear();
      return;
    }
    const order = nodes.map(function (node) {
      return node.dataset.pomoUid;
    });
    const moved = order.splice(from, 1)[0];
    order.splice(index, 0, moved);
    const kind = dragKind;
    clear();
    const method = {
      pomodoro: "reorder_pomodoros",
      duration_mode: "reorder_duration_modes",
      background: "reorder_backgrounds",
      ring: "reorder_rings",
      environment: "reorder_environments",
    }[kind];
    if (!method) return;
    call(method, order).then(function (data) {
      if (data) apply(data);
    });
  });

  host.addEventListener("dragend", clear);
}
