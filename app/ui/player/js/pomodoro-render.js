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

function pomoSelect(attr, options, value) {
  return (
    '<select class="pomo-select" ' + attr + ">" +
    options
      .map(function (option) {
        return (
          '<option value="' + esc(option.value) + '"' +
          (option.value === value ? " selected" : "") + ">" +
          esc(option.label) + "</option>"
        );
      })
      .join("") +
    "</select>"
  );
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
  return (
    '<div class="pomo-detail-section"><h3>' + esc(title) + "</h3>" +
    pomoDetailRow(
      T("pomodoro.item.playlist"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-override="playlist"',
        pomoPlaylistOptions(),
        pomoPhaseValue(phase, "playlist", config.playlist || "")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.play"),
      pomoSwitch(
        'data-pomo-phase="' + phase + '" data-pomo-override="play"',
        pomoPhaseValue(phase, "play", !!config.play),
        T("pomodoro.item.play")
      )
    ) +
    pomoDetailRow(
      T("pomodoro.item.order"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-override="order"',
        pomoValueOptions("pomodoro.order", pomodoroOptions().orders || []),
        pomoPhaseValue(phase, "order", config.order || "shuffle")
      )
    ) +
    "</div>"
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
