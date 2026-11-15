/* 歌单分区：列表、详情、自适应参数卡、条件行。 */
/* ---------- 歌单 ---------- */

function playlistByUid(uid) {
  return (
    ((state.data && state.data.playlists) || []).find(function (item) {
      return item.uid === uid;
    }) || null
  );
}

function visiblePlaylists() {
  const list = (state.data && state.data.playlists) || [];
  const query = state.playlistQuery.trim().toLowerCase();
  if (!query) return list;
  return list.filter(function (playlist) {
    return playlist.title.toLowerCase().indexOf(query) !== -1;
  });
}

function playlistKindLabel(playlist) {
  return T(playlist.kind === "manual" ? "playlist.kind_manual" : "playlist.kind_filter");
}

function renderPlaylistList() {
  const list = qs("#playlist-list");
  const total = (state.data.playlists || []).length;
  const items = visiblePlaylists();
  qs("#playlists-count").textContent = T("playlist.total", { count: total });

  if (!items.length) {
    list.innerHTML = total
      ? '<li class="row-empty">' + esc(T("playlist.no_match")) + "</li>"
      : emptyList("playlist", T("playlist.empty"), T("playlist.empty_hint"), {
          action: "new_playlist",
          label: T("playlist.new"),
        });
    return;
  }

  list.innerHTML = items
    .map(function (playlist) {
      const classes = ["song-row"];
      if (state.activeKind === "playlist" && state.active === playlist.uid) {
        classes.push("is-active");
      }
      const badge = playlist.builtin
        ? T("playlist.builtin")
        : playlistKindLabel(playlist);
      const count = playlist.error
        ? T("playlist.resolve_error")
        : T("playlist.count", { count: playlist.count });
      return (
        '<li class="' + classes.join(" ") + '" draggable="true" data-playlist-uid="' +
        esc(playlist.uid) +
        '" tabindex="0"><div class="song-body"><span class="song-title">' +
        esc(playlist.title) + '</span><span class="song-sub">' + esc(badge) + " · " +
        esc(count) + "</span></div></li>"
      );
    })
    .join("");
}

function renderPlaylistDetail() {
  const pane = qs("#playlist-detail");
  const playlist =
    state.activeKind === "playlist" && state.active ? playlistByUid(state.active) : null;

  if (!playlist) {
    pane.innerHTML =
      '<div class="detail-empty">' +
      '<svg class="empty-art" viewBox="0 0 24 24" aria-hidden="true">' +
      '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>' +
      "<h2>" + esc(T("playlist.no_selection_title")) + "</h2>" +
      "<p>" + esc(T("playlist.no_selection_hint")) + "</p></div>";
    return;
  }

  const count = playlist.error
    ? T("playlist.resolve_error")
    : T("playlist.count", { count: playlist.count });
  const badge = playlist.builtin
    ? '<span class="badge is-builtin">' + esc(T("playlist.builtin")) + "</span>"
    : '<span class="badge">' + esc(playlistKindLabel(playlist)) + "</span>";

  const nameRow = playlist.builtin
    ? '<div class="field-row"><span class="field-label">' + esc(T("playlist.name")) +
      '</span><div class="field-body"><span>' + esc(playlist.title) +
      '</span><p class="detail-hint">' + esc(T("playlist.builtin_hint")) + "</p></div></div>"
    : '<div class="field-row"><span class="field-label">' + esc(T("playlist.name")) +
      '</span><div class="field-body"><input class="input" id="playlist-name" value="' +
      esc(playlist.title) + '" maxlength="120"></div></div>';

  const content =
    playlist.kind === "manual" ? manualPlaylistCard(playlist) : filterPlaylistCard(playlist);

  pane.innerHTML =
    '<header class="detail-head"><div class="detail-title"><h2>' +
    esc(playlist.title) + "</h2><div class=\"detail-meta\">" + badge +
    "<span>·</span><span>" + esc(count) + "</span></div></div>" +
    '<div class="detail-tools">' +
    (playlist.builtin
      ? ""
      : '<button class="btn ghost" data-menu="playlist">' + esc(T("action.more")) + "</button>") +
    "</div></header>" +
    '<section class="card">' + nameRow + "</section>" +
    content +
    adaptationCard(playlist);
}

/* ---------- 自适应 ---------- */

function adaptationDefaults() {
  const common = (state.data && state.data.settings && state.data.settings.common) || {};
  return common.adaptation || {};
}

function adaptRow(key, label, hint, unit, value, fallback, overridden, limits) {
  const raw = value === null || value === undefined ? fallback : value;
  // 跳过基数存的是比例，界面上按整数百分比显示。
  const number = key === "base" ? Math.round(raw * 100) : raw;
  const range =
    limits && limits.min !== undefined
      ? ' min="' + limits.min + '" max="' + limits.max + '" step="' + (limits.step || 1) + '"'
      : "";
  return (
    '<div class="adapt-row"><div><span class="adapt-name">' + esc(label) + "</span>" +
    '<span class="adapt-hint">' + esc(hint) + "</span></div>" +
    '<input class="input" type="number" data-adapt="' + key + '" value="' + esc(number) + '"' +
    range + (overridden ? "" : " disabled") + ">" +
    '<span class="adapt-unit">' + esc(unit) + "</span>" +
    '<label class="check adapt-inherit"><input type="checkbox" data-inherit="' + key + '"' +
    (overridden ? "" : " checked") + "><span>" + esc(T("adaptation.inherit")) + "</span></label>" +
    "</div>"
  );
}

function adaptationCard(playlist) {
  const adapt = playlist.adaptation || {};
  const defaults = adaptationDefaults();
  const overridden = function (key) {
    return adapt[key] !== null && adapt[key] !== undefined;
  };
  const globalText = function (key, unit) {
    const value = key === "base" ? Math.round((defaults[key] || 0) * 100) : defaults[key];
    // 百分比紧贴数字（「全局 95%」），次数与秒数则留一个空格。
    if (key === "base") return T("adaptation.global_percent", { value: value });
    return unit
      ? T("adaptation.global_unit", { value: value, unit: unit })
      : T("adaptation.global", { value: value });
  };

  return (
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("adaptation.title")) + '</h3><button class="btn ghost small" data-stats="' +
    esc(playlist.uid) + '">' + esc(T("adaptation.view_stats")) + "</button></div>" +
    '<div class="toggle-row"><div class="toggle-body"><div class="toggle-title">' +
    esc(T("adaptation.enabled")) + '</div><p class="toggle-hint">' +
    esc(T("adaptation.enabled_hint")) + "</p></div>" +
    '<button class="switch" type="button" role="switch" data-adapt-enabled aria-checked="' +
    (adapt.enabled ? "true" : "false") + '"><span class="switch-knob"></span></button></div>' +
    adaptRow(
      "window",
      T("adaptation.window"),
      globalText("window", T("adaptation.times")),
      T("adaptation.times"),
      adapt.window,
      defaults.window,
      overridden("window"),
      { min: 10, max: 1000 }
    ) +
    adaptRow(
      "min_plays",
      T("adaptation.min_plays"),
      globalText("min_plays", T("adaptation.times")),
      T("adaptation.times"),
      adapt.min_plays,
      defaults.min_plays,
      overridden("min_plays"),
      { min: 0, max: 1000 }
    ) +
    adaptRow(
      "base",
      T("adaptation.base"),
      globalText("base", T("adaptation.percent")),
      T("adaptation.percent"),
      adapt.base,
      defaults.base,
      overridden("base"),
      { min: 1, max: 99 }
    ) +
    adaptRow(
      "skip_seconds",
      T("adaptation.skip_seconds"),
      globalText("skip_seconds", T("adaptation.seconds")),
      T("adaptation.seconds"),
      adapt.skip_seconds,
      defaults.skip_seconds,
      overridden("skip_seconds"),
      { min: 5, max: 300 }
    ) +
    "</section>"
  );
}

function manualPlaylistCard(playlist) {
  const musics = (playlist.entries || [])
    .map(function (md5) {
      return musicByMd5(md5);
    })
    .filter(Boolean);

  const rows = musics
    .map(function (music) {
      return (
        '<li class="entry-row" draggable="true" data-entry="' + esc(music.md5) + '">' +
        '<span class="grip" aria-hidden="true">⋮⋮</span>' +
        '<div class="entry-body"><span class="entry-title">' + esc(music.title) +
        '</span><span class="entry-sub">' + esc(music.authors_text || T("song.no_author")) +
        " · " + formatDuration(music.duration_ms) + "</span></div>" +
        '<button class="icon-btn" data-entry-remove="' + esc(music.md5) +
        '" aria-label="' + esc(T("action.remove")) + '">×</button></li>'
      );
    })
    .join("");

  return (
    '<section class="card card--list"><div class="card-tools"><h3 class="card-title">' +
    esc(T("playlist.content")) + " · " + esc(T("playlist.count", { count: musics.length })) +
    '</h3><button class="btn soft small" data-playlist-add="1">' +
    esc(T("playlist.add_songs")) + "</button></div>" +
    (rows
      ? '<ul class="entry-list" id="entry-list">' + rows + "</ul>"
      : '<p class="row-empty">' + esc(T("playlist.entries_empty")) + "</p>") +
    "</section>"
  );
}

function playlistErrorCard(playlist) {
  const detail = playlist.error_detail || {};
  const isCycle = detail.kind === "cycle";
  const title = T(isCycle ? "playlist.cycle_title" : "playlist.error_title");
  const body = isCycle
    ? T("playlist.cycle_body", { chain: (detail.chain || []).join(" → ") })
    : detail.text || playlist.error || "";
  const hint = T(isCycle ? "playlist.cycle_hint" : "playlist.error_hint");
  return (
    '<div class="error-card" role="alert">' +
    '<div class="error-card-title">' + esc(title) + "</div>" +
    '<p class="error-card-text">' + esc(body) + "</p>" +
    (hint ? '<p class="error-card-hint">' + esc(hint) + "</p>" : "") +
    "</div>"
  );
}

function filterPlaylistCard(playlist) {
  const rows = (playlist.filters || [])
    .map(function (condition, index) {
      return filterRowMarkup(condition, index);
    })
    .join("");

  return (
    '<section class="card"><div class="card-tools"><h3 class="card-title">' +
    esc(T("playlist.conditions")) + " · " +
    esc(
      playlist.error
        ? T("playlist.resolve_error")
        : T("playlist.count", { count: playlist.count })
    ) +
    '</h3><button class="btn soft small" data-filter-add="1">' +
    esc(T("playlist.add_condition")) + "</button></div>" +
    (rows || '<p class="row-empty">' + esc(T("playlist.condition_empty")) + "</p>") +
    (playlist.error ? playlistErrorCard(playlist) : "") +
    '<div class="card-foot">' +
    '<button class="btn ghost small" data-playlist-preview="1">' +
    esc(T("playlist.preview")) + "</button></div>" +
    "</section>"
  );
}

function filterRowMarkup(condition, index) {
  const modeOptions = [
    { value: "include", label: T("playlist.filter_include") },
    { value: "exclude", label: T("playlist.filter_exclude") },
  ];
  const targetOptions = [
    { value: "all", label: T("playlist.target_all") },
    { value: "music", label: T("playlist.target_music") },
    { value: "playlist", label: T("playlist.target_playlist") },
    { value: "tag", label: T("playlist.target_tag") },
    { value: "author", label: T("playlist.target_author") },
  ];

  const values =
    condition.target === "all"
      ? '<span class="filter-summary">' + esc(T("playlist.target_all")) + "</span>"
      : '<span class="filter-summary">' + esc(filterSummary(condition)) + "</span>" +
        '<button class="btn soft small" data-filter-pick="' + index + '">' +
        esc(T("playlist.filter_pick")) + "</button>";

  return (
    '<div class="filter-row" data-filter-row="' + index + '" data-filter-index="' + index + '">' +
    '<span class="grip drag-grip" data-filter-grip="1" title="' +
    esc(T("common.drag_hint")) + '" aria-hidden="true">⋮⋮</span>' +
    selectMarkup('data-filter-mode="' + index + '"', modeOptions, condition.mode) +
    selectMarkup('data-filter-target="' + index + '"', targetOptions, condition.target) +
    '<div class="filter-values">' + values + "</div>" +
    '<div class="filter-tools">' +
    '<button class="icon-btn" data-filter-remove="' + index + '" aria-label="' +
    esc(T("action.remove")) + '">×</button>' +
    "</div></div>"
  );
}

function filterSummary(condition) {
  const values = condition.values || [];
  if (!values.length) return T("playlist.filter_empty");
  const names = values
    .map(function (uid) {
      return objectName(condition.target, uid);
    })
    .filter(Boolean);
  if (!names.length) return T("playlist.filter_empty");
  const shown = names.slice(0, 2).join(T("list.separator"));
  return names.length > 2 ? shown + T("playlist.more", { count: names.length - 2 }) : shown;
}

function objectName(target, uid) {
  if (target === "music") {
    const music = musicByMd5(uid);
    return music ? music.title : "";
  }
  if (target === "playlist") {
    const playlist = playlistByUid(uid);
    return playlist ? playlist.title : "";
  }
  if (target === "tag") {
    const tag = tagMap()[uid];
    return tag ? tag.name : "";
  }
  if (target === "author") {
    const author = authorMap()[uid];
    return author ? author.name : "";
  }
  return "";
}

function renderPlaylists() {
  renderPlaylistList();
  renderPlaylistDetail();
}
