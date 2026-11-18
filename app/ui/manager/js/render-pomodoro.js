/* 番茄分区：左侧分组列表、总览、番茄钟 / 时长模式 / 资源详情。 */
/* ---------- 数据索引 ---------- */

function pomodoroData() {
  return (state.data && state.data.pomodoro) || {};
}

function pomodoroItems() {
  return pomodoroData().items || [];
}

function pomodoroModes() {
  return pomodoroData().duration_modes || [];
}

function pomodoroBackgrounds() {
  return pomodoroData().backgrounds || [];
}

function pomodoroRings() {
  return pomodoroData().rings || [];
}

function pomodoroEnvironments() {
  return pomodoroData().environments || [];
}

function pomodoroOptions() {
  return pomodoroData().options || {};
}

function pomodoroItemByUid(uid) {
  return pomodoroItems().find(function (item) {
    return item.uid === uid;
  }) || null;
}

function pomodoroModeByUid(uid) {
  return pomodoroModes().find(function (item) {
    return item.uid === uid;
  }) || null;
}

function pomodoroBackgroundByUid(uid) {
  return pomodoroBackgrounds().find(function (item) {
    return item.uid === uid;
  }) || null;
}

function pomodoroRingByUid(uid) {
  return pomodoroRings().find(function (item) {
    return item.uid === uid;
  }) || null;
}

function pomodoroEnvironmentByUid(uid) {
  return pomodoroEnvironments().find(function (item) {
    return item.uid === uid;
  }) || null;
}

function pomodoroGroupDefs() {
  return [
    {
      kind: "pomodoro",
      label: T("pomodoro.group.items"),
      items: pomodoroItems(),
      empty: T("pomodoro.empty_items"),
      add: "pomodoro",
    },
    {
      kind: "duration_mode",
      label: T("pomodoro.group.duration_modes"),
      items: pomodoroModes(),
      empty: T("pomodoro.empty_modes"),
      add: "duration_mode",
    },
    {
      kind: "background",
      label: T("pomodoro.group.backgrounds"),
      items: pomodoroBackgrounds(),
      empty: T("pomodoro.empty_backgrounds"),
      add: "background",
    },
    {
      kind: "ring",
      label: T("pomodoro.group.rings"),
      items: pomodoroRings(),
      empty: T("pomodoro.empty_rings"),
      add: "ring",
    },
    {
      kind: "environment",
      label: T("pomodoro.group.environments"),
      items: pomodoroEnvironments(),
      empty: T("pomodoro.empty_environments"),
      add: "environment",
    },
  ];
}

function pomodoroRowSub(kind, item) {
  if (kind === "pomodoro") {
    return T("pomodoro.row.item_sub", {
      summary: item.summary || T("pomodoro.none"),
      minutes: item.total_minutes || 0,
    });
  }
  if (kind === "duration_mode") {
    return T("pomodoro.row.mode_sub", {
      summary: item.summary,
      minutes: item.total_minutes,
    });
  }
  if (kind === "background") {
    return T(item.kind === "video" ? "pomodoro.background.video" : "pomodoro.background.image") +
      " · " + formatSize(item.size);
  }
  return formatDuration(item.duration_ms) + " · " + formatSize(item.size);
}

/* 详情里的下拉框用普通尺寸（不是筛选行那种小号），菜单与框同宽。 */
function pomoSelect(attrs, options, value, disabled) {
  return selectMarkup(attrs, options, value, "", disabled ? "is-disabled" : "");
}

/* ---------- 左侧列表 ---------- */

function pomodoroCollapsed(kind) {
  return state.pomoCollapsed && state.pomoCollapsed[kind] === true;
}

function renderPomodoroNav() {
  const host = qs("#pomodoro-nav");
  if (!host) return;
  const items = pomodoroItems();
  qs("#pomodoro-count").textContent = T("pomodoro.total", { count: items.length });

  const overviewActive = state.activeKind === "pomodoro_overview";
  let html =
    '<button class="pomo-overview' + (overviewActive ? " is-active" : "") +
    '" type="button" data-pomodoro-overview="1">' +
    '<span class="pomo-overview-icon" aria-hidden="true">' +
    '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/>' +
    '<rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>' +
    '<rect x="14" y="14" width="7" height="7" rx="1.5"/></svg></span>' +
    esc(T("pomodoro.group.overview")) + "</button>";

  pomodoroGroupDefs().forEach(function (group) {
    const collapsed = pomodoroCollapsed(group.kind);
    const rows = group.items
      .map(function (item) {
        const active = state.activeKind === group.kind && state.active === item.uid;
        return (
          '<li class="pomo-row' + (active ? " is-active" : "") +
          '" draggable="true" data-pomo-row="1" data-pomo-kind="' + esc(group.kind) +
          '" data-pomo-uid="' + esc(item.uid) + '" tabindex="0">' +
          '<div class="pomo-row-body"><span class="pomo-row-name">' + esc(item.name) +
          '</span><span class="pomo-row-sub">' + esc(pomodoroRowSub(group.kind, item)) +
          "</span></div></li>"
        );
      })
      .join("");
    html +=
      '<div class="pomo-group" data-pomo-group="' + esc(group.kind) + '">' +
      '<div class="pomo-group-head">' +
      '<button class="pomo-group-toggle" type="button" data-pomo-toggle="' + esc(group.kind) +
      '" aria-expanded="' + (collapsed ? "false" : "true") + '">' +
      '<svg class="pomo-chevron' + (collapsed ? " is-collapsed" : "") +
      '" viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 5l7 7-7 7"/></svg>' +
      '<span class="pomo-group-name">' + esc(group.label) + "</span>" +
      '<span class="pomo-group-count">' + group.items.length + "</span></button>" +
      '<button class="icon-btn small pomo-group-add" type="button" data-pomo-add="' +
      esc(group.add) + '" aria-label="' + esc(T("pomodoro.add")) + '" title="' +
      esc(T("pomodoro.add")) + '">+</button></div>' +
      (collapsed
        ? ""
        : '<ul class="pomo-list">' +
          (rows || '<li class="pomo-empty">' + esc(group.empty) + "</li>") +
          "</ul>") +
      "</div>";
  });
  host.innerHTML = html;
}

/* ---------- 详情入口 ---------- */

function pomodoroEmptyDetail() {
  return (
    '<div class="detail-empty">' +
    '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
    '<path d="M12 7.5c3.6 0 6.5 2.9 6.5 6.5S15.6 20.5 12 20.5 5.5 17.6 5.5 14 8.4 7.5 12 7.5Z"/>' +
    '<path d="M12 7.5c0-2 1.1-3.6 3-4.5M12 7.5c0-2-1.1-3.6-3-4.5"/></svg>' +
    "<h2>" + esc(T("pomodoro.no_selection_title")) + "</h2>" +
    "<p>" + esc(T("pomodoro.no_selection_hint")) + "</p></div>"
  );
}

function pomodoroHeader(title, sub, menuKind, uid) {
  return (
    '<header class="detail-head"><div class="detail-title"><h2>' + esc(title) +
    '</h2><div class="detail-meta"><span>' + esc(sub) + "</span></div></div>" +
    (menuKind
      ? '<div class="detail-tools"><button class="btn ghost" data-menu="pomodoro" data-pomo-menu-kind="' +
        esc(menuKind) + '" data-pomo-menu-uid="' + esc(uid) + '">' +
        esc(T("action.more")) + "</button></div>"
      : "") +
    "</header>"
  );
}

function renderPomodoroDetail() {
  const pane = qs("#pomodoro-detail");
  if (!pane) return;
  const kind = state.activeKind;
  const uid = state.active;
  if (kind !== "pomodoro_audition") stopPomodoroAuditionIfChanged(kind, uid);

  if (kind === "pomodoro_overview") {
    pane.innerHTML = pomodoroOverviewMarkup();
    return;
  }
  if (kind === "pomodoro" && uid) {
    const item = pomodoroItemByUid(uid);
    if (item) {
      pane.innerHTML = pomodoroItemMarkup(item);
      return;
    }
  }
  if (kind === "duration_mode" && uid) {
    const mode = pomodoroModeByUid(uid);
    if (mode) {
      pane.innerHTML = pomodoroModeMarkup(mode);
      return;
    }
  }
  if (kind === "background" && uid) {
    const background = pomodoroBackgroundByUid(uid);
    if (background) {
      pane.innerHTML = pomodoroBackgroundMarkup(background);
      return;
    }
  }
  if (kind === "ring" && uid) {
    const ring = pomodoroRingByUid(uid);
    if (ring) {
      pane.innerHTML = pomodoroAudioMarkup(ring, "ring");
      return;
    }
  }
  if (kind === "environment" && uid) {
    const environment = pomodoroEnvironmentByUid(uid);
    if (environment) {
      pane.innerHTML = pomodoroAudioMarkup(environment, "environment");
      return;
    }
  }
  pane.innerHTML = pomodoroEmptyDetail();
}

/* ---------- 总览 ---------- */

function pomodoroStatCard(value, label) {
  return (
    '<div class="pomo-stat"><span class="pomo-stat-value">' + esc(value) +
    '</span><span class="pomo-stat-label">' + esc(label) + "</span></div>"
  );
}

function pomodoroRecentRows(rows, edited) {
  if (!rows.length) {
    return '<li class="row-empty">' + esc(T("pomodoro.overview.empty_recent")) + "</li>";
  }
  return rows
    .map(function (row) {
      const sub = edited
        ? T("pomodoro.overview.edited_at", { time: formatDate(row.updated_at) })
        : T("pomodoro.overview.used_time", {
            focus: formatDuration(row.stats.focus_ms),
            total: formatDuration(row.stats.total_ms),
          });
      return (
        '<li class="row is-clickable" data-pomo-goto="' + esc(row.uid) + '" tabindex="0">' +
        '<div class="row-body"><span class="row-title">' + esc(row.name) +
        '</span><span class="row-sub">' + esc(row.summary || "") + " · " + esc(sub) +
        "</span></div></li>"
      );
    })
    .join("");
}

function pomodoroOverviewMarkup() {
  const data = pomodoroData();
  const overview = data.overview || {};
  const total = overview.total || {};
  const counts = overview.counts || {};
  const recentUsed = overview.recent_used || [];
  const recentEdited = overview.recent_edited || [];
  return (
    '<header class="detail-head"><div class="detail-title"><h2>' +
    esc(T("pomodoro.overview.title")) + '</h2><div class="detail-meta"><span>' +
    esc(T("pomodoro.overview.sub")) + "</span></div></div></header>" +
    '<section class="card"><div class="pomo-stat-grid">' +
    pomodoroStatCard(formatDuration(total.total_ms), T("pomodoro.stat.total")) +
    pomodoroStatCard(formatDuration(total.focus_ms), T("pomodoro.stat.focus")) +
    pomodoroStatCard(formatDuration(total.rest_ms), T("pomodoro.stat.rest")) +
    pomodoroStatCard(String(total.sessions || 0), T("pomodoro.stat.sessions")) +
    "</div></section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.overview.counts")) +
    '</h3><div class="pomo-count-grid">' +
    '<span>' + esc(T("pomodoro.group.items")) + " · " + (counts.items || 0) + "</span>" +
    '<span>' + esc(T("pomodoro.group.duration_modes")) + " · " + (counts.duration_modes || 0) + "</span>" +
    '<span>' + esc(T("pomodoro.group.backgrounds")) + " · " + (counts.backgrounds || 0) + "</span>" +
    '<span>' + esc(T("pomodoro.group.rings")) + " · " + (counts.rings || 0) + "</span>" +
    '<span>' + esc(T("pomodoro.group.environments")) + " · " + (counts.environments || 0) + "</span>" +
    "</div></section>" +
    '<section class="card"><div class="card-heading"><h3 class="card-title">' +
    esc(T("pomodoro.overview.recent_used")) + "</h3></div>" +
    '<ul class="rows">' + pomodoroRecentRows(recentUsed, false) + "</ul></section>" +
    '<section class="card"><div class="card-heading"><h3 class="card-title">' +
    esc(T("pomodoro.overview.recent_edited")) + "</h3></div>" +
    '<ul class="rows">' + pomodoroRecentRows(recentEdited, true) + "</ul></section>"
  );
}

/* ---------- 番茄钟详情 ---------- */

function pomoField(label, control, hint) {
  return (
    '<div class="field-row"><span class="field-label">' + esc(label) + "</span>" +
    '<div class="field-body">' + control +
    (hint ? '<p class="detail-hint">' + esc(hint) + "</p>" : "") + "</div></div>"
  );
}

function pomoPlaylistOptions() {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    (pomodoroOptions().playlists || []).map(function (playlist) {
      return { value: playlist.uid, label: playlist.title };
    })
  );
}

function pomoBackgroundOptions() {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    pomodoroBackgrounds().map(function (background) {
      return { value: background.uid, label: background.name };
    })
  );
}

function pomoRingOptions() {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    pomodoroRings().map(function (ring) {
      return { value: ring.uid, label: ring.name };
    })
  );
}

function pomoEnvironmentOptions() {
  return [{ value: "", label: T("pomodoro.none") }].concat(
    pomodoroEnvironments().map(function (environment) {
      return { value: environment.uid, label: environment.name };
    })
  );
}

function pomoModeOptions() {
  return pomodoroModes().map(function (mode) {
    return { value: mode.uid, label: mode.name + " · " + mode.summary };
  });
}

function pomoValueOptions(prefix, values) {
  return values.map(function (value) {
    return { value: value, label: T(prefix + "." + value) };
  });
}

function pomoPhaseCard(item, phase, title, hint) {
  const config = item[phase] || {};
  const play = !!config.play;
  return (
    '<section class="card"><h3 class="card-title">' + esc(title) + "</h3>" +
    '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
    esc(T("pomodoro.item.play")) + '</div><p class="toggle-hint">' + esc(hint) +
    '</p></div><button class="switch" type="button" role="switch" data-pomo-phase="' +
    phase + '" data-pomo-field="play" aria-checked="' + (play ? "true" : "false") +
    '"><span class="switch-knob"></span></button></div>' +
    pomoField(
      T("pomodoro.item.playlist"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-field="playlist"',
        pomoPlaylistOptions(),
        config.playlist || "",
        !play
      )
    ) +
    pomoField(
      T("pomodoro.item.order"),
      pomoSelect(
        'data-pomo-phase="' + phase + '" data-pomo-field="order"',
        pomoValueOptions("pomodoro.order", pomodoroOptions().orders || []),
        config.order || "shuffle",
        !play
      )
    ) +
    "</section>"
  );
}

function pomodoroItemMarkup(item) {
  const modeOptions = pomoModeOptions();
  const backgroundOptions = pomoBackgroundOptions();
  const background = item.background ? pomodoroBackgroundByUid(item.background) : null;
  return (
    pomodoroHeader(
      item.name,
      T("pomodoro.row.item_sub", {
        summary: item.summary || T("pomodoro.none"),
        minutes: item.total_minutes || 0,
      }),
      "pomodoro",
      item.uid
    ) +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.basic")) + "</h3>" +
    pomoField(
      T("pomodoro.item.name"),
      '<input class="input" id="pomodoro-name" value="' + esc(item.name) +
        '" maxlength="120" data-pomo-name="' + esc(item.uid) + '">'
    ) +
    pomoField(
      T("pomodoro.item.description"),
      '<textarea class="input textarea" id="pomodoro-description" maxlength="2000" ' +
        'placeholder="' + esc(T("pomodoro.item.description_placeholder")) +
        '" data-pomo-description="' + esc(item.uid) + '">' + esc(item.description || "") +
        "</textarea>"
    ) +
    "</section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.timing")) + "</h3>" +
    pomoField(
      T("pomodoro.item.duration_mode"),
      pomoSelect(
        'data-pomo-field="duration_mode"',
        modeOptions,
        item.duration_mode || ""
      ),
      item.summary ? T("pomodoro.item.mode_hint", { summary: item.summary }) : ""
    ) +
    "</section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.background")) +
    "</h3>" +
    pomoField(
      T("pomodoro.item.background"),
      pomoSelect(
        'data-pomo-field="background"',
        backgroundOptions,
        item.background || ""
      )
    ) +
    pomoField(
      T("pomodoro.item.background_mode"),
      pomoSelect(
        'data-pomo-field="background_mode"',
        pomoValueOptions("pomodoro.bg_mode", pomodoroOptions().background_modes || []),
        item.background_mode || "cover"
      )
    ) +
    (background
      ? '<div class="pomo-preview">' +
        (background.kind === "video"
          ? '<video src="' + esc(background.url) + '" controls muted preload="metadata"></video>'
          : '<img src="' + esc(background.url) + '" alt="">') +
        "</div>"
      : "") +
    "</section>" +
    pomoPhaseCard(item, "focus", T("pomodoro.item.focus_section"), T("pomodoro.item.focus_hint")) +
    pomoPhaseCard(item, "rest", T("pomodoro.item.rest_section"), T("pomodoro.item.rest_hint")) +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.sound")) + "</h3>" +
    pomoField(
      T("pomodoro.item.ring"),
      pomoSelect('data-pomo-field="ring"', pomoRingOptions(), item.ring || "")
    ) +
    pomoField(
      T("pomodoro.item.environment"),
      pomoSelect(
        'data-pomo-field="environment"',
        pomoEnvironmentOptions(),
        item.environment || ""
      )
    ) +
    '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
    esc(T("pomodoro.item.environment_enabled")) + '</div><p class="toggle-hint">' +
    esc(T("pomodoro.item.environment_hint")) +
    '</p></div><button class="switch" type="button" role="switch" ' +
    'data-pomo-field="environment_enabled" aria-checked="' +
    (item.environment_enabled ? "true" : "false") +
    '"><span class="switch-knob"></span></button></div>' +
    "</section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.appearance")) +
    "</h3>" +
    pomoField(
      T("pomodoro.item.font"),
      pomoSelect(
        'data-pomo-field="font"',
        pomoValueOptions("pomodoro.font", pomodoroOptions().fonts || []),
        item.font || "system"
      )
    ) +
    "</section>" +
    pomodoroStatsCard(item.stats)
  );
}

function pomodoroStatsCard(stats) {
  const data = stats || {};
  return (
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.stats")) +
    '</h3><div class="pomo-stat-grid pomo-stat-grid--small">' +
    pomodoroStatCard(formatDuration(data.focus_ms), T("pomodoro.stat.focus")) +
    pomodoroStatCard(formatDuration(data.rest_ms), T("pomodoro.stat.rest")) +
    pomodoroStatCard(formatDuration(data.total_ms), T("pomodoro.stat.total")) +
    pomodoroStatCard(String(data.sessions || 0), T("pomodoro.stat.sessions")) +
    "</div>" +
    '<p class="detail-hint">' +
    esc(
      data.last_used_at
        ? T("pomodoro.stat.last_used", { time: formatDate(data.last_used_at) })
        : T("pomodoro.never_used")
    ) +
    "</p></section>"
  );
}

/* ---------- 时长模式详情 ---------- */

function pomodoroModeMarkup(mode) {
  const rows = mode.segments
    .map(function (minutes, index) {
      const focus = index % 2 === 0;
      return (
        '<div class="pomo-seg-row" data-pomo-segment-row="1" data-pomo-segment="' + index + '">' +
        '<span class="grip drag-grip" data-pomo-segment-grip="1" aria-hidden="true">⋮⋮</span>' +
        '<span class="pomo-seg-type' + (focus ? " is-focus" : "") + '">' +
        esc(T(focus ? "pomodoro.mode.focus" : "pomodoro.mode.rest")) + "</span>" +
        '<input class="input pomo-seg-input" type="number" min="1" max="180" step="1" value="' +
        minutes + '" data-pomo-segment-minutes="' + index + '">' +
        '<span class="pomo-seg-unit">' + esc(T("pomodoro.mode.minutes")) + "</span>" +
        '<button class="icon-btn" type="button" data-pomo-remove-segment="' + index +
        '" aria-label="' + esc(T("action.remove")) + '">×</button></div>'
      );
    })
    .join("");
  return (
    pomodoroHeader(
      mode.name,
      T("pomodoro.row.mode_sub", { summary: mode.summary, minutes: mode.total_minutes }),
      "duration_mode",
      mode.uid
    ) +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.basic")) + "</h3>" +
    pomoField(
      T("pomodoro.mode.name"),
      '<input class="input" id="pomodoro-mode-name" value="' + esc(mode.name) +
        '" maxlength="120" data-pomo-mode-name="' + esc(mode.uid) + '">'
    ) +
    "</section>" +
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("pomodoro.mode.segments")) + " · " +
    esc(T("pomodoro.mode.total", { minutes: mode.total_minutes })) +
    '</h3><button class="btn soft small" type="button" data-pomo-add-segment="1">' +
    esc(T("pomodoro.mode.add_segment")) + "</button></div>" +
    '<div class="pomo-seg-list">' + rows + "</div>" +
    '<p class="detail-hint">' + esc(T("pomodoro.mode.segments_hint")) + "</p></section>"
  );
}

/* ---------- 资源详情 ---------- */

function pomodoroBackgroundMarkup(background) {
  const preview = background.exists
    ? background.kind === "video"
      ? '<video src="' + esc(background.url) + '" controls muted preload="metadata"></video>'
      : '<img src="' + esc(background.url) + '" alt="">'
    : '<p class="row-empty">' + esc(T("pomodoro.background.missing")) + "</p>";
  return (
    pomodoroHeader(
      background.name,
      T(background.kind === "video" ? "pomodoro.background.video" : "pomodoro.background.image") +
        " · " + formatSize(background.size),
      "background",
      background.uid
    ) +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.basic")) + "</h3>" +
    pomoField(
      T("pomodoro.asset.name"),
      '<input class="input" id="pomodoro-asset-name" value="' + esc(background.name) +
        '" maxlength="120" data-pomo-asset-name="' + esc(background.uid) +
        '" data-pomo-asset-kind="background">'
    ) +
    "</section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.background.preview")) +
    '</h3><div class="pomo-preview">' + preview + "</div></section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.asset.info")) + "</h3>" +
    pomoField(
      T("pomodoro.asset.format"),
      '<span class="path-text">' +
        esc(
          T(
            background.kind === "video"
              ? "pomodoro.background.video"
              : "pomodoro.background.image"
          )
        ) +
        "</span>"
    ) +
    (background.kind === "video"
      ? pomoField(
          T("pomodoro.asset.dimensions"),
          '<span class="path-text">' + background.width + " × " + background.height + "</span>"
        )
      : "") +
    pomoField(
      T("pomodoro.asset.duration"),
      '<span class="path-text">' + esc(formatDuration(background.duration_ms)) + "</span>"
    ) +
    pomoField(
      T("pomodoro.asset.size"),
      '<span class="path-text">' + esc(formatSize(background.size)) + "</span>"
    ) +
    pomoField(T("pomodoro.asset.file"), '<span class="path-text">' + esc(background.file) + "</span>") +
    "</section>"
  );
}

function pomodoroAuditionMarkup(asset) {
  return (
    '<div class="pomo-audition" data-pomo-audition="1" data-audition-url="' + esc(asset.url) +
    '" data-audition-uid="' + esc(asset.uid) + '">' +
    '<button class="icon-btn pomo-audition-toggle" type="button" data-pomo-audition-toggle="1" ' +
    'data-playing="false" aria-label="' + esc(T("pomodoro.audition.play")) + '">' +
    '<svg class="icon-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>' +
    '<svg class="icon-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4h4v16H7zM13 4h4v16h-4z"/></svg>' +
    "</button>" +
    '<span class="pomo-audition-time" data-pomo-audition-current>0:00</span>' +
    '<input class="range pomo-audition-seek" type="range" min="0" max="1000" value="0" ' +
    'data-pomo-audition-seek="1" aria-label="' + esc(T("pomodoro.audition.seek")) + '">' +
    '<span class="pomo-audition-time" data-pomo-audition-total>' +
    esc(formatDuration(asset.duration_ms)) + "</span></div>"
  );
}

function pomodoroAudioMarkup(asset, kind) {
  const title = T(kind === "ring" ? "pomodoro.group.rings" : "pomodoro.group.environments");
  return (
    pomodoroHeader(asset.name, title + " · " + formatDuration(asset.duration_ms), kind, asset.uid) +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.item.basic")) + "</h3>" +
    pomoField(
      T("pomodoro.asset.name"),
      '<input class="input" id="pomodoro-asset-name" value="' + esc(asset.name) +
        '" maxlength="120" data-pomo-asset-name="' + esc(asset.uid) +
        '" data-pomo-asset-kind="' + esc(kind) + '">'
    ) +
    "</section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.audition.title")) +
    '</h3><div class="pomo-audition-host" id="pomodoro-audition-host">' +
    (asset.exists ? pomodoroAuditionMarkup(asset) : '<p class="row-empty">' +
      esc(T("pomodoro.asset.missing")) + "</p>") +
    "</div></section>" +
    '<section class="card"><h3 class="card-title">' + esc(T("pomodoro.asset.info")) + "</h3>" +
    pomoField(T("pomodoro.asset.format"), '<span class="path-text">' + esc(asset.ext) + "</span>") +
    pomoField(
      T("pomodoro.asset.duration"),
      '<span class="path-text">' + esc(formatDuration(asset.duration_ms)) + "</span>"
    ) +
    pomoField(
      T("pomodoro.asset.size"),
      '<span class="path-text">' + esc(formatSize(asset.size)) + "</span>"
    ) +
    pomoField(T("pomodoro.asset.file"), '<span class="path-text">' + esc(asset.file) + "</span>") +
    "</section>"
  );
}

/* ---------- 总渲染 ---------- */

function renderPomodoros() {
  renderPomodoroNav();
  renderPomodoroDetail();
}
