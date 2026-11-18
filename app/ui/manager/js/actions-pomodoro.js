/* 番茄钟的动作：新建、删除、导入、段编辑、内嵌试听。 */
/* ---------- 名称 ---------- */

function schedulePomodoroNameSave(input) {
  input.classList.remove("invalid");
  window.clearTimeout(state.pomoNameTimer);
  state.pomoNameTimer = window.setTimeout(function () {
    state.pomoNameTimer = null;
    savePomodoroName(input);
  }, 420);
}

async function savePomodoroName(input) {
  if (!input) return;
  const value = input.value.trim();
  let result = null;
  if (input.dataset.pomoName) {
    result = await call("rename_pomodoro", input.dataset.pomoName, value);
  } else if (input.dataset.pomoModeName) {
    result = await call("rename_duration_mode", input.dataset.pomoModeName, value);
  } else if (input.dataset.pomoAssetName) {
    const kind = input.dataset.pomoAssetKind;
    const uid = input.dataset.pomoAssetName;
    const method = {
      background: "rename_background",
      ring: "rename_ring",
      environment: "rename_environment",
    }[kind];
    if (method) result = await call(method, uid, value);
  }
  if (!result || !result.ok) {
    input.classList.add("invalid");
    return;
  }
  const uid =
    input.dataset.pomoName || input.dataset.pomoModeName || input.dataset.pomoAssetName;
  const row = qs('.pomo-row[data-pomo-uid="' + uid + '"] .pomo-row-name');
  if (row) row.textContent = value;
}

async function flushPomodoroNameSave() {
  if (!state.pomoNameTimer) return;
  window.clearTimeout(state.pomoNameTimer);
  state.pomoNameTimer = null;
  const input = qs(
    "#pomodoro-name, #pomodoro-mode-name, #pomodoro-asset-name"
  );
  if (input) await savePomodoroName(input);
}

/* ---------- 新建 ---------- */

function openCreatePomodoro() {
  openModal({
    title: T("pomodoro.create_item_title"),
    body:
      '<div class="field-row"><span class="field-label">' + esc(T("pomodoro.item.name")) +
      '</span><div class="field-body"><input class="input" id="new-pomodoro-name" maxlength="120" placeholder="' +
      esc(T("pomodoro.item_name_placeholder")) + '"></div></div>',
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("pomodoro.create_item"),
        primary: true,
        onClick: async function () {
          const input = qs("#new-pomodoro-name");
          const name = input.value.trim();
          if (!name) {
            input.classList.add("invalid");
            return;
          }
          const data = await call("create_pomodoro", name);
          if (data && data.ok) {
            closeModal();
            apply(data);
          } else if (data) {
            toast(data.message || T("pomodoro.invalid"), false);
          }
        },
      },
    ],
    onMount: function () {
      qs("#new-pomodoro-name").focus();
    },
  });
}

function openCreateDurationMode() {
  openModal({
    title: T("pomodoro.mode.create_title"),
    body:
      '<div class="field-row"><span class="field-label">' + esc(T("pomodoro.mode.name")) +
      '</span><div class="field-body"><input class="input" id="new-mode-name" maxlength="120" placeholder="' +
      esc(T("pomodoro.mode.name_placeholder")) + '"></div></div>' +
      '<p class="modal-note">' + esc(T("pomodoro.mode.create_note")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("pomodoro.mode.create"),
        primary: true,
        onClick: async function () {
          const input = qs("#new-mode-name");
          const name = input.value.trim();
          if (!name) {
            input.classList.add("invalid");
            return;
          }
          const data = await call("create_duration_mode", name, [25, 5, 25, 5, 25, 5, 25]);
          if (data && data.ok) {
            closeModal();
            apply(data);
          } else if (data) {
            toast(data.message || T("pomodoro.invalid"), false);
          }
        },
      },
    ],
    onMount: function () {
      qs("#new-mode-name").focus();
    },
  });
}

/* ---------- 段编辑 ---------- */

async function pomodoroAddSegment() {
  const mode = state.activeKind === "duration_mode" ? pomodoroModeByUid(state.active) : null;
  if (!mode) return;
  const last = mode.segments.length ? mode.segments[mode.segments.length - 1] : 25;
  const nextFocus = mode.segments.length % 2 === 0;
  const segments = mode.segments.concat([nextFocus ? 25 : Math.max(1, Math.min(180, last))]);
  const data = await call("update_duration_mode", mode.uid, { segments: segments });
  if (data) apply(data);
}

async function pomodoroRemoveSegment(index) {
  const mode = state.activeKind === "duration_mode" ? pomodoroModeByUid(state.active) : null;
  if (!mode) return;
  if (mode.segments.length <= 1) {
    toast(T("pomodoro.mode.keep_one"), false);
    return;
  }
  const segments = mode.segments.filter(function (_value, position) {
    return position !== index;
  });
  const data = await call("update_duration_mode", mode.uid, { segments: segments });
  if (data) apply(data);
}

async function pomodoroUpdateSegment(index, minutes) {
  const mode = state.activeKind === "duration_mode" ? pomodoroModeByUid(state.active) : null;
  if (!mode) return;
  const value = Math.max(1, Math.min(180, Math.round(minutes) || 1));
  const segments = mode.segments.slice();
  segments[index] = value;
  const data = await call("update_duration_mode", mode.uid, { segments: segments });
  if (data) apply(data);
}

async function pomodoroReorderSegments(order) {
  const mode = state.activeKind === "duration_mode" ? pomodoroModeByUid(state.active) : null;
  if (!mode) return;
  const segments = order.map(function (index) {
    return mode.segments[Number(index)];
  });
  const data = await call("update_duration_mode", mode.uid, { segments: segments });
  if (data) apply(data);
}

/* ---------- 删除 ---------- */

function pomodoroReferrers(kind, uid) {
  return pomodoroItems().filter(function (item) {
    if (kind === "duration_mode") return item.duration_mode === uid;
    if (kind === "background") return item.background === uid;
    if (kind === "ring") return item.ring === uid;
    if (kind === "environment") return item.environment === uid;
    return false;
  });
}

function pomodoroDeps(items) {
  return items.map(function (item) {
    return { kind: T("pomodoro.group.items"), name: item.name };
  });
}

function pomodoroDeleteLabel(kind) {
  return T("pomodoro.delete." + kind);
}

function confirmDeletePomodoroThing(kind, uid) {
  const item =
    kind === "pomodoro"
      ? pomodoroItemByUid(uid)
      : kind === "duration_mode"
        ? pomodoroModeByUid(uid)
        : kind === "background"
          ? pomodoroBackgroundByUid(uid)
          : kind === "ring"
            ? pomodoroRingByUid(uid)
            : pomodoroEnvironmentByUid(uid);
  if (!item) return;
  const referrers = kind === "pomodoro" ? [] : pomodoroReferrers(kind, uid);
  const body =
    '<p class="modal-note">' +
    esc(T("pomodoro.delete.confirm", { name: item.name })) +
    "</p>" +
    (referrers.length
      ? '<p class="modal-note">' +
        esc(
          T(
            kind === "duration_mode"
              ? "pomodoro.delete.referenced_mode"
              : "pomodoro.delete.referenced"
          )
        ) +
        "</p>" +
        dependencyMarkup(pomodoroDeps(referrers))
      : "");
  const method = {
    pomodoro: "delete_pomodoro",
    duration_mode: "delete_duration_mode",
    background: "delete_background",
    ring: "delete_ring",
    environment: "delete_environment",
  }[kind];
  openModal({
    title: pomodoroDeleteLabel(kind),
    body: body,
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: pomodoroDeleteLabel(kind),
        danger: true,
        onClick: async function () {
          const data = await call(method, uid);
          if (!data) return;
          closeModal();
          if (data.ok === false) {
            toast(data.message || T("pomodoro.invalid"), false);
            return;
          }
          apply(data);
        },
      },
    ],
  });
}

function openPomodoroMenu(kind, uid, anchor) {
  openMenu(anchor, [
    {
      label: pomodoroDeleteLabel(kind),
      onClick: function () {
        confirmDeletePomodoroThing(kind, uid);
      },
    },
  ]);
}

/* ---------- 导入 ---------- */

function pomodoroAssetLabel(kind) {
  return T(
    kind === "background"
      ? "pomodoro.import_background"
      : kind === "ring"
        ? "pomodoro.import_ring"
        : "pomodoro.import_environment"
  );
}

async function importPomodoroAsset(kind) {
  const picked = await call("browse_pomodoro_asset", kind);
  if (!picked || !picked.path) return;
  const info = await call("probe_pomodoro_source", picked.path);
  if (!info || !info.ok) {
    toast((info && info.message) || T("pomodoro.import.probe_failed"), false);
    return;
  }
  if (kind === "ring" || (kind === "background" && info.kind === "image")) {
    const started = await call("start_pomodoro_import", kind, picked.path, null);
    if (started && started.task_id) openPomodoroImportModal(started.task_id);
    return;
  }
  openPomodoroSegmentModal(kind, picked.path, info);
}

function pomodoroSegmentBody(kind, info) {
  const seconds = Math.max(0, Math.round((info.duration_ms || 0) / 100) / 10);
  const note =
    kind === "environment" && (info.ext === "mp4" || info.ext === "m4a")
      ? '<p class="modal-note">' + esc(T("pomodoro.import.mp4_to_mp3")) + "</p>"
      : "";
  return (
    '<p class="modal-note">' +
    esc(T("pomodoro.import.file", { name: info.name, duration: formatDuration(info.duration_ms) })) +
    "</p>" +
    note +
    '<div class="pomo-import-grid">' +
    '<label class="pomo-import-field"><span>' + esc(T("pomodoro.import.start_ms")) +
    '</span><input class="input" id="pomo-start" type="number" min="0" step="0.1" value="0"></label>' +
    '<label class="pomo-import-field"><span>' + esc(T("pomodoro.import.end_ms")) +
    '</span><input class="input" id="pomo-end" type="number" min="0" step="0.1" value="' +
    seconds + '"></label>' +
    "</div>" +
    '<label class="check"><input type="checkbox" id="pomo-strip-only"><span>' +
    esc(T("pomodoro.import.strip_only")) + "</span></label>" +
    '<p class="detail-hint">' + esc(T("pomodoro.import.strip_only_hint")) + "</p>" +
    '<div id="pomo-trim-options">' +
    '<label class="check"><input type="checkbox" id="pomo-crossfade" checked><span>' +
    esc(T("pomodoro.import.crossfade")) + "</span></label>" +
    '<p class="detail-hint">' + esc(T("pomodoro.import.crossfade_hint")) + "</p>" +
    '<label class="pomo-import-field pomo-import-field--inline"><span>' +
    esc(T("pomodoro.import.fade")) + '</span><input class="input" id="pomo-fade" type="number" ' +
    'min="0.1" max="30" step="0.1" value="3"><span>' +
    esc(T("pomodoro.import.seconds")) + "</span></label></div>"
  );
}

function openPomodoroSegmentModal(kind, path, info) {
  openModal({
    title: pomodoroAssetLabel(kind),
    wide: true,
    body: pomodoroSegmentBody(kind, info),
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("pomodoro.import.start"),
        primary: true,
        onClick: async function () {
          const stripOnly = qs("#pomo-strip-only").checked;
          const start = Number(qs("#pomo-start").value) || 0;
          const end = Number(qs("#pomo-end").value) || 0;
          const fade = Number(qs("#pomo-fade").value) || 3;
          const options = {
            start_ms: Math.max(0, Math.round(start * 1000)),
            end_ms: Math.max(0, Math.round(end * 1000)),
            crossfade: qs("#pomo-crossfade").checked,
            fade_ms: Math.max(100, Math.round(fade * 1000)),
            strip_only: stripOnly,
          };
          const started = await call("start_pomodoro_import", kind, path, options);
          if (started && started.task_id) openPomodoroImportModal(started.task_id);
        },
      },
    ],
    onMount: function () {
      const strip = qs("#pomo-strip-only");
      const trim = qs("#pomo-trim-options");
      const fields = qs(".pomo-import-grid");
      strip.addEventListener("change", function () {
        [trim, fields].forEach(function (container) {
          if (!container) return;
          container.classList.toggle("is-disabled", strip.checked);
          qsa("input", container).forEach(function (node) {
            node.disabled = strip.checked;
          });
        });
      });
    },
  });
}

function openPomodoroImportModal(taskId) {
  openModal({
    title: T("pomodoro.import.title"),
    body:
      '<p class="progress-text" id="pomo-import-line"></p>' +
      '<div class="progress"><div class="progress-bar" id="pomo-import-bar"></div></div>' +
      '<div id="pomo-import-errors"></div>',
    dismissible: false,
    backdropDismissible: false,
    actions: [],
  });
  runPomodoroImportTask(taskId);
}

function runPomodoroImportTask(taskId) {
  let misses = 0;
  async function poll() {
    const task = await call("poll_task", taskId);
    if (!task) {
      misses += 1;
      if (misses < 3) {
        window.setTimeout(poll, 500);
        return;
      }
      qs("#pomo-import-line").textContent = T("pomodoro.import.failed");
      modalDismissible = true;
      qs("#modal-close").hidden = false;
      return;
    }
    if (task.state === "running") {
      const percent = task.total ? Math.round((task.done / task.total) * 100) : 0;
      qs("#pomo-import-line").textContent = T("pomodoro.import.running", {
        current: task.current || "",
      });
      qs("#pomo-import-bar").style.width = Math.max(8, percent) + "%";
      window.setTimeout(poll, 300);
      return;
    }
    qs("#pomo-import-bar").style.width = "100%";
    qs("#pomo-import-line").textContent = T(
      task.state === "failed" ? "pomodoro.import.failed" : "pomodoro.import.done"
    );
    const errors = task.errors || [];
    if (errors.length) {
      const list = document.createElement("ul");
      list.className = "report-list";
      errors.forEach(function (item) {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
      qs("#pomo-import-errors").appendChild(list);
    }
    const actions = qs("#modal-actions");
    const button = document.createElement("button");
    button.className = "btn primary";
    button.textContent = T("action.close");
    button.addEventListener("click", closeModal);
    actions.appendChild(button);
    modalDismissible = true;
    qs("#modal-close").hidden = false;
    if (task.state !== "failed") {
      const data = await call("get_state");
      if (data) apply(data);
    }
  }
  poll();
}

/* ---------- 内嵌试听 ---------- */

function pomoAuditionAudio() {
  return qs("#pomo-audition");
}

function stopPomodoroAuditionIfChanged(kind, uid) {
  if (!state.pomoAuditionUid) return;
  if ((kind === "ring" || kind === "environment") && state.pomoAuditionUid === uid) return;
  stopPomodoroAudition();
}

function stopPomodoroAudition() {
  const audio = pomoAuditionAudio();
  state.pomoAuditionUid = null;
  if (!audio) return;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  paintPomodoroAudition(false);
}

function paintPomodoroAudition(playing) {
  const button = qs("[data-pomo-audition-toggle]");
  if (!button) return;
  button.dataset.playing = playing ? "true" : "false";
  button.setAttribute("aria-label", T(playing ? "pomodoro.audition.pause" : "pomodoro.audition.play"));
}

function togglePomodoroAudition() {
  const host = qs(".pomo-audition");
  const audio = pomoAuditionAudio();
  if (!host || !audio) return;
  const url = host.dataset.auditionUrl;
  if (!url) {
    toast(T("pomodoro.asset.missing"), false);
    return;
  }
  if (audio.getAttribute("src") !== url) {
    audio.src = url;
    audio.currentTime = 0;
  }
  state.pomoAuditionUid = host.dataset.auditionUid || null;
  if (audio.paused) {
    audio.play().catch(function () {
      toast(T("pomodoro.audition.failed"), false);
    });
  } else {
    audio.pause();
  }
}

function syncPomodoroAudition() {
  const audio = pomoAuditionAudio();
  const host = qs(".pomo-audition");
  if (!audio || !host) return;
  const duration = Number.isFinite(audio.duration) && audio.duration ? audio.duration : 0;
  const current = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
  const seek = host.querySelector("[data-pomo-audition-seek]");
  if (seek && duration) seek.value = String(Math.round((current / duration) * 1000));
  const currentLabel = host.querySelector("[data-pomo-audition-current]");
  if (currentLabel) currentLabel.textContent = formatDuration(current * 1000);
  const totalLabel = host.querySelector("[data-pomo-audition-total]");
  if (totalLabel && duration) totalLabel.textContent = formatDuration(duration * 1000);
  paintPomodoroAudition(!audio.paused);
}

function seekPomodoroAudition(value) {
  const audio = pomoAuditionAudio();
  if (!audio || !Number.isFinite(audio.duration) || !audio.duration) return;
  audio.currentTime = (Number(value) / 1000) * audio.duration;
  syncPomodoroAudition();
}
