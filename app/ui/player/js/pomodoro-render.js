/* 番茄钟的列表与详情渲染。计时层在 pomodoro.js 里。 */
/* ---------- 数据 ---------- */

function pomodoroData() {
  return (state.data && state.data.pomodoros) || {};
}

function pomodoroItems() {
  return pomodoroData().items || [];
}

function pomodoroSelected() {
  return pomodoroData().selected || null;
}

function pomodoroOptions() {
  return pomodoroData().options || {};
}

function pomodoroPreferences() {
  return pomodoroData().preferences || {};
}

function pomodoroSelectedUid() {
  const selected = pomodoroSelected();
  return selected ? selected.uid : null;
}

/* ---------- 列表 ---------- */

function renderPomodoros() {
  const head = qs("#pomodoro-head");
  const list = qs("#pomodoros");
  if (!head || !list) return;
  const items = pomodoroItems();
  head.hidden = !items.length;
  list.hidden = !items.length;
  if (!items.length) {
    list.innerHTML = "";
    return;
  }
  const selected = pomodoroSelectedUid();
  const locked = pomo.active;
  list.innerHTML = items
    .map(function (item) {
      const active = item.uid === selected || item.active;
      return (
        '<button type="button" role="listitem" class="playlist-item pomo-item' +
        (active ? " is-active" : "") + (locked ? " is-locked" : "") +
        '" data-pomodoro-uid="' + esc(item.uid) + '">' +
        '<span class="name">' + esc(item.name) + "</span>" +
        '<span class="count">' + esc(item.summary || "") + "</span></button>"
      );
    })
    .join("");
}

/* ---------- 详情 ---------- */

function pomoOverrideValue(key, fallback) {
  return state.pomoOverrides && state.pomoOverrides[key] !== undefined
    ? state.pomoOverrides[key]
    : fallback;
}

function pomoPhaseValue(phase, key, fallback) {
  const overrides = state.pomoOverrides || {};
  const nested = overrides[phase] || {};
  return nested[key] !== undefined ? nested[key] : fallback;
}

function pomoSelect(attr, options, value, disabled) {
  const current = options.find(function (option) {
    return option.value === value;
  });
  const menu = options
    .map(function (option) {
      return (
        '<button class="pomo-option' + (option.value === value ? " is-active" : "") +
        '" type="button" role="option" data-value="' + esc(option.value) + '">' +
        esc(option.label) + "</button>"
      );
    })
    .join("");
  return (
    '<div class="pomo-select' + (disabled ? " is-disabled" : "") + '" ' + attr +
    ' role="combobox" tabindex="0" aria-expanded="false" aria-haspopup="listbox" data-value="' +
    esc(value) + '"><span class="pomo-select-value">' +
    esc(current ? current.label : "") +
    '</span><svg class="pomo-select-arrow" viewBox="0 0 12 12" aria-hidden="true">' +
    '<path d="M2.5 4.5L6 8l3.5-3.5"/></svg>' +
    '<div class="pomo-select-menu" role="listbox">' + menu + "</div></div>"
  );
}

function pomoSetSelectValue(select, value, notify) {
  select.dataset.value = value;
  const option = select.querySelector('.pomo-option[data-value="' + value + '"]');
  const label = select.querySelector(".pomo-select-value");
  if (label) label.textContent = option ? option.textContent : value;
  select.querySelectorAll(".pomo-option").forEach(function (node) {
    node.classList.toggle("is-active", node.dataset.value === value);
  });
  if (notify) {
    select.dispatchEvent(
      new CustomEvent("selectchange", { bubbles: true, detail: { value: value } })
    );
  }
}

function pomoCloseSelects(except) {
  qsa(".pomo-select.open").forEach(function (select) {
    if (select === except) return;
    select.classList.remove("open");
    select.setAttribute("aria-expanded", "false");
  });
}

function pomoToggleSelect(select) {
  const open = select.classList.contains("open");
  pomoCloseSelects(select);
  select.classList.toggle("open", !open);
  select.setAttribute("aria-expanded", String(!open));
}

function pomoStepSelect(select, delta) {
  const options = qsa(".pomo-option", select);
  if (!options.length) return;
  let index = options.findIndex(function (node) {
    return node.dataset.value === select.dataset.value;
  });
  if (index === -1) index = 0;
  index = Math.min(options.length - 1, Math.max(0, index + delta));
  pomoSetSelectValue(select, options[index].dataset.value, true);
}

function pomoInitSelects() {
  document.addEventListener("click", function (event) {
    const option = event.target.closest(".pomo-option");
    if (option) {
      const select = option.closest(".pomo-select");
      if (select) {
        pomoSetSelectValue(select, option.dataset.value, true);
        pomoCloseSelects();
      }
      return;
    }
    const select = event.target.closest(".pomo-select");
    if (select) {
      if (select.classList.contains("is-disabled")) return;
      pomoToggleSelect(select);
      return;
    }
    pomoCloseSelects();
  });

  document.addEventListener("keydown", function (event) {
    const select = event.target.closest(".pomo-select");
    if (!select) return;
    if (select.classList.contains("is-disabled")) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      pomoToggleSelect(select);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      pomoStepSelect(select, event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      pomoCloseSelects();
      select.blur();
    }
  });
}

function pomoPlaylistOptions() {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    (pomodoroOptions().playlists || []).map(function (playlist) {
      return { value: playlist.uid, label: playlist.title };
    })
  );
}

function pomoAssetOptions(list) {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    (list || []).map(function (item) {
      return { value: item.uid, label: item.name };
    })
  );
}

function pomoModeOptions() {
  return (pomodoroOptions().duration_modes || []).map(function (mode) {
    return { value: mode.uid, label: mode.name + " · " + mode.summary };
  });
}

function pomoValueOptions(prefix, values) {
  return (values || []).map(function (value) {
    return { value: value, label: T(prefix + "." + value) };
  });
}

function pomoDetailRow(label, control) {
  return (
    '<div class="pomo-detail-row"><span class="pomo-detail-label">' + esc(label) +
    "</span>" + control + "</div>"
  );
}

function pomoSwitch(attr, on, label) {
  return (
    '<button class="pomo-switch" type="button" role="switch" ' + attr +
    ' aria-checked="' + (on ? "true" : "false") + '" aria-label="' + esc(label) +
    '"><span class="pomo-switch-knob"></span></button>'
  );
}

function pomoPhaseBlock(selected, phase, title) {
  const config = selected[phase] || {};
  const play = pomoPhaseValue(phase, "play", !!config.play);
  return (
    '<div class="pomo-detail-section"><h3>' + esc(title) + "</h3>" +
    pomoDetailRow(
      T("pomodoro.item.play"),
      pomoSwitch(
        'data-pomo-phase="' + phase + '" data-pomo-override="play"',
        play,
        T("pomodoro.item.play")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.playlist"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-override="playlist"',
        pomoPlaylistOptions(),
        pomoPhaseValue(phase, "playlist", config.playlist || ""),
        !play
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.order"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-override="order"',
        pomoValueOptions("pomodoro.order", pomodoroOptions().orders || []),
        pomoPhaseValue(phase, "order", config.order || "shuffle"),
        !play
      )
    ) +
    "</div>"
  );
}

/* 左下角计时器的整体比例。语言文件这一轮不写，标签先固定中文。 */
function pomoScaleRow() {
  const scale = Number(pomodoroPreferences().hud_scale) || 1.5;
  const percent = Math.round(scale * 100);
  return (
    '<div class="pomo-detail-row"><span class="pomo-detail-label">计时器大小</span>' +
    '<div class="pomo-scale"><input class="slider" id="pomo-hud-scale" type="range" ' +
    'min="80" max="250" step="5" value="' + percent + '">' +
    '<span class="pomo-scale-value" id="pomo-hud-scale-value">' + percent +
    "%</span></div></div>"
  );
}

function pomodoroDetailMarkup(selected) {
  const stats = selected.stats || {};
  return (
    '<div class="pomo-detail-wrap">' +
    '<header class="pomo-detail-head"><div><h1 class="pomo-detail-title">' +
    esc(selected.name) + '</h1><p class="pomo-detail-sub">' +
    esc(selected.summary || "") + " · " +
    esc(T("pomodoro.minutes", { count: selected.total_minutes || 0 })) +
    (selected.description ? " · " + esc(selected.description) : "") +
    "</p></div></header>" +
    '<div class="pomo-detail-card">' +
    pomoDetailRow(
      T("pomodoro.item.duration_mode"),
      pomoSelect(
        'data-pomo-override="duration_mode"',
        pomoModeOptions(),
        pomoOverrideValue("duration_mode", selected.duration_mode)
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.background"),
      pomoSelect(
        'data-pomo-override="background"',
        pomoAssetOptions(pomodoroOptions().backgrounds),
        pomoOverrideValue("background", selected.background || "")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.background_mode"),
      pomoSelect(
        'data-pomo-override="background_mode"',
        pomoValueOptions("pomodoro.bg_mode", pomodoroOptions().background_modes || []),
        pomoOverrideValue("background_mode", selected.background_mode || "cover")
      )
    ) +
    pomoPhaseBlock(selected, "focus", T("pomodoro.item.focus_section")) +
    pomoPhaseBlock(selected, "rest", T("pomodoro.item.rest_section")) +
    '<div class="pomo-detail-section"><h3>' + esc(T("pomodoro.item.sound")) + "</h3>" +
    pomoDetailRow(
      T("pomodoro.item.ring"),
      pomoSelect(
        'data-pomo-override="ring"',
        pomoAssetOptions(pomodoroOptions().rings),
        pomoOverrideValue("ring", selected.ring || "")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.environment"),
      pomoSelect(
        'data-pomo-override="environment"',
        pomoAssetOptions(pomodoroOptions().environments),
        pomoOverrideValue("environment", selected.environment || "")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.environment_enabled"),
      pomoSwitch(
        'data-pomo-override="environment_enabled"',
        pomoOverrideValue("environment_enabled", !!selected.environment_enabled),
        T("pomodoro.item.environment_enabled")
      )
    ) +
    "</div>" +
    '<div class="pomo-detail-section"><h3>' + esc(T("pomodoro.item.appearance")) + "</h3>" +
    pomoDetailRow(
      T("pomodoro.item.font"),
      pomoSelect(
        'data-pomo-override="font"',
        pomoValueOptions("pomodoro.font", pomodoroOptions().fonts || []),
        pomoOverrideValue("font", selected.font || "system")
      )
    ) +
    pomoScaleRow() +
    "</div>" +
    "</div>" +
    '<div class="pomo-detail-stats">' +
    '<span>' + esc(T("pomodoro.stat.focus")) + " · " + esc(formatDuration(stats.focus_ms)) + "</span>" +
    '<span>' + esc(T("pomodoro.stat.rest")) + " · " + esc(formatDuration(stats.rest_ms)) + "</span>" +
    '<span>' + esc(T("pomodoro.stat.sessions")) + " · " + esc(String(stats.sessions || 0)) + "</span>" +
    "</div>" +
    '<div class="pomo-detail-actions">' +
    '<button class="btn primary" id="pomo-start" type="button">' + esc(T("pomodoro.start")) + "</button>" +
    '<button class="btn ghost" id="pomo-reset" type="button">' + esc(T("pomodoro.reset")) + "</button>" +
    "</div>" +
    '<p class="pomo-detail-note">' + esc(T("pomodoro.override_note")) + "</p>" +
    "</div>"
  );
}

function renderPomodoroDetail() {
  const detail = qs("#pomodoro-detail");
  const body = qs("#now-body");
  const app = qs("#app");
  if (!detail || !body || !app) return;
  const selected = pomodoroSelected();
  const uid = selected ? selected.uid : null;
  if (uid !== state.pomoDetailUid) {
    state.pomoDetailUid = uid;
    state.pomoOverrides = {};
  }
  const view = selected ? "pomodoro" : "music";
  if (state.pomoView !== view) {
    state.pomoView = view;
    const target = selected ? detail : body;
    target.classList.remove("pomo-view-in");
    void target.offsetWidth;
    target.classList.add("pomo-view-in");
  }
  if (!selected) {
    detail.hidden = true;
    detail.innerHTML = "";
    body.hidden = false;
    app.classList.remove("pomodoro-view");
    return;
  }
  detail.hidden = false;
  body.hidden = true;
  app.classList.add("pomodoro-view");
  detail.innerHTML = pomodoroDetailMarkup(selected);
}

function pomoOverridesPayload() {
  const selected = pomodoroSelected();
  if (!selected) return {};
  return {
    duration_mode: pomoOverrideValue("duration_mode", selected.duration_mode),
    background: pomoOverrideValue("background", selected.background || ""),
    background_mode: pomoOverrideValue("background_mode", selected.background_mode),
    ring: pomoOverrideValue("ring", selected.ring || ""),
    environment: pomoOverrideValue("environment", selected.environment || ""),
    environment_enabled: pomoOverrideValue(
      "environment_enabled",
      !!selected.environment_enabled
    ),
    font: pomoOverrideValue("font", selected.font),
    focus: {
      playlist: pomoPhaseValue("focus", "playlist", selected.focus.playlist || ""),
      play: pomoPhaseValue("focus", "play", !!selected.focus.play),
      order: pomoPhaseValue("focus", "order", selected.focus.order),
    },
    rest: {
      playlist: pomoPhaseValue("rest", "playlist", selected.rest.playlist || ""),
      play: pomoPhaseValue("rest", "play", !!selected.rest.play),
      order: pomoPhaseValue("rest", "order", selected.rest.order),
    },
  };
}

function renderPomodoroView() {
  renderPomodoros();
  renderPomodoroDetail();
}
