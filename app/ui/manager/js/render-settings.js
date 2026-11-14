/* 设置页：五个分页的渲染与逐项写回。 */
/* ---------- 设置 ---------- */

function settingsRow(title, hint, control, hintClass) {
  return (
    '<div class="settings-row"><div class="settings-row-main">' +
    '<div class="settings-row-title">' + esc(title) + "</div>" +
    (hint
      ? '<p class="settings-row-hint' + (hintClass ? " " + hintClass : "") + '">' +
        esc(hint) + "</p>"
      : "") +
    '</div><div class="settings-row-control">' + control + "</div></div>"
  );
}

function settingsCard(title, body, hint) {
  return (
    '<section class="card"><div class="card-heading"><h3 class="card-title">' +
    esc(title) + "</h3>" +
    (hint ? '<p class="card-hint">' + esc(hint) + "</p>" : "") +
    "</div>" + body + "</section>"
  );
}

function switchMarkup(attr, on, label) {
  return (
    '<button class="switch" type="button" role="switch" ' + attr + ' aria-checked="' +
    (on ? "true" : "false") + '"' + (label ? ' aria-label="' + esc(label) + '"' : "") +
    '><span class="switch-knob"></span></button>'
  );
}

function settingsGeneral() {
  const common = (state.data.settings && state.data.settings.common) || {};
  const adapt = common.adaptation || {};
  const status = state.data.status || {};
  const auditionVolume = Math.round(
    (((state.data.settings || {}).audition || {}).volume ?? 0.2) * 100
  );

  const themes = [
    ["system", T("settings.theme_system")],
    ["light", T("settings.theme_light")],
    ["dark", T("settings.theme_dark")],
  ];
  const themeSeg =
    '<div class="seg" id="theme-seg">' +
    themes
      .map(function (item) {
        return (
          '<button class="seg-item' + (common.theme === item[0] ? " is-active" : "") +
          '" type="button" data-theme-value="' + item[0] + '">' + esc(item[1]) + "</button>"
        );
      })
      .join("") +
    "</div>";

  const adaptRow = function (key, label, unit, min, max, step) {
    return settingsRow(
      label,
      T("adaptation.range", { min: min, max: max }),
      '<input class="input" type="number" data-default="' + key + '" value="' +
        esc(adapt[key]) + '" min="' + min + '" max="' + max + '" step="' + step +
        '" style="width:110px"><span class="adapt-unit">' + esc(unit) + "</span>"
    );
  };

  // 语言名用各自的语言书写，所以中文界面里也会看到 English (United States)。
  const languages = (state.data && state.data.languages) || [];
  const currentLanguage = (state.data && state.data.language) || "";
  const languageSeg = languages.length
    ? '<div class="seg" id="language-seg">' +
      languages
        .map(function (item) {
          return (
            '<button class="seg-item' + (item.code === currentLanguage ? " is-active" : "") +
            '" type="button" data-language="' + esc(item.code) + '">' +
            esc(item.name) + "</button>"
          );
        })
        .join("") +
      "</div>"
    : '<span class="path-text">' + esc(currentLanguage) + "</span>";

  return (
    settingsCard(
      T("settings.appearance"),
      settingsRow(T("settings.theme"), T("settings.theme_hint"), themeSeg) +
        settingsRow(T("settings.language"), T("settings.language_hint"), languageSeg)
    ) +
    settingsCard(
      T("settings.adaptation_defaults"),
      adaptRow("window", T("adaptation.window"), T("adaptation.times"), 10, 1000, 1) +
        adaptRow("min_plays", T("adaptation.min_plays"), T("adaptation.times"), 0, 1000, 1) +
        adaptRow("base", T("adaptation.base"), "", 0, 0.99, 0.01) +
        adaptRow("skip_seconds", T("adaptation.skip_seconds"), T("adaptation.seconds"), 5, 300, 1),
      T("settings.adaptation_hint")
    ) +
    settingsCard(
      T("settings.audition"),
      settingsRow(
        T("settings.audition_volume"),
        T("settings.audition_volume_hint"),
        '<div class="volume-line"><input class="range" id="audition-default" type="range" ' +
          'min="0" max="100" step="1" value="' + auditionVolume + '">' +
          '<span class="volume-value" id="audition-default-value">' + auditionVolume + "%</span></div>"
      )
    ) +
    settingsCard(
      T("settings.paths"),
      settingsRow(
        T("settings.data_dir"),
        status.data_dir || "",
        '<button class="btn ghost small" data-action="data_dir">' +
          esc(T("action.open")) + "</button>",
        "path-text"
      ) +
        settingsRow(
          T("settings.log_dir"),
          status.log_dir || "",
          '<button class="btn ghost small" data-action="log_dir">' +
            esc(T("action.open")) + "</button>",
          "path-text"
        )
    )
  );
}

function settingsImport() {
  const section = (state.data.settings && state.data.settings.import) || {};
  const status = state.data.status || {};
  const ffmpegStatus = status.ffmpeg || { available: false, path: "" };
  const probeStatus = status.ffprobe || { available: false, path: "" };

  const statusLine = function (info, label) {
    return (
      '<span class="status-dot' + (info.available ? " is-ok" : "") + '"></span>' +
      esc(info.available ? T("settings.detected") : T("settings.not_detected")) +
      (info.path ? '<span class="path-text">' + esc(info.path) + "</span>" : "")
    );
  };

  return (
    settingsCard(
      T("settings.import_section"),
      settingsRow(
        T("settings.import_dir"),
        T("settings.import_dir_hint"),
        '<input class="input" id="import-dir" value="' + esc(section.dir || "") +
          '" placeholder="' + esc(T("settings.import_dir_placeholder")) + '">' +
          '<button class="btn ghost small" data-action="browse_import_dir">' +
          esc(T("action.browse")) + "</button>" +
          '<button class="btn ghost small" data-action="clear_import_dir">' +
          esc(T("action.clear_field")) + "</button>"
      ) +
        settingsRow(
          T("settings.clean_audio"),
          T("settings.clean_audio_hint"),
          switchMarkup(
            'data-setting-switch="import.clean_audio"',
            section.clean_audio !== false,
            T("settings.clean_audio")
          )
        )
    ) +
    settingsCard(
      T("settings.ffmpeg"),
      settingsRow(T("settings.ffmpeg_binary"), "", statusLine(ffmpegStatus)) +
        settingsRow(T("settings.ffprobe_binary"), "", statusLine(probeStatus)) +
        '<div class="settings-actions"><button class="btn ghost small" ' +
        'data-action="refresh_status">' + esc(T("settings.refresh")) + "</button></div>"
    )
  );
}

function settingsSimple() {
  const section = (state.data.settings && state.data.settings.simple) || {};
  const volume = Math.round((section.volume === undefined ? 0.2 : section.volume) * 100);
  return settingsCard(
    T("settings.simple_section"),
    settingsRow(
        T("settings.play_order"),
        T("settings.simple_order_hint"),
        selectMarkup(
          'data-setting-select="simple.order"',
          [
            { value: "shuffle", label: T("settings.order_shuffle") },
            { value: "list_loop", label: T("settings.order_list_loop") },
          ],
          section.order || "shuffle",
          ""
        )
      ) +
      settingsRow(
        T("settings.simple_volume"),
        T("settings.simple_volume_hint"),
        '<div class="volume-line"><input class="range" id="simple-volume" type="range" ' +
          'min="0" max="100" step="1" value="' + volume + '">' +
          '<span class="volume-value" id="simple-volume-value">' + volume + "%</span></div>"
      ) +
      settingsRow(
        T("settings.default_playlist"),
        T("settings.default_playlist_hint"),
        '<button class="btn ghost small" data-action="goto_default">' +
          esc(T("settings.goto")) + "</button>"
      ),
    T("settings.simple_hint")
  );
}

function settingsPlayer() {
  const section = (state.data.settings && state.data.settings.player) || {};
  const volume = Math.round((section.volume === undefined ? 0.2 : section.volume) * 100);

  return settingsCard(
    T("settings.player_section"),
    settingsRow(
      T("settings.volume"),
      T("settings.volume_hint"),
      '<div class="volume-line"><input class="range" id="player-volume" type="range" ' +
        'min="0" max="100" step="1" value="' + volume + '">' +
        '<span class="volume-value" id="player-volume-value">' + volume + "%</span></div>"
    ) +
      settingsRow(
        T("settings.play_order"),
        T("settings.player_order_hint"),
        selectMarkup(
          'data-setting-select="player.order"',
          [
            { value: "shuffle", label: T("settings.order_shuffle") },
            { value: "list_loop", label: T("settings.order_list_loop") },
            { value: "repeat_one", label: T("settings.order_repeat_one") },
          ],
          section.order || "shuffle",
          ""
        )
      ) +
      settingsRow(
        T("settings.remember_progress"),
        T("settings.remember_progress_hint"),
        switchMarkup(
          'data-setting-switch="player.remember_progress"',
          section.remember_progress !== false,
          T("settings.remember_progress")
        )
      )
  );
}

function settingsMaintenance() {
  const debugOn = ((state.data.settings || {}).common || {}).debug === true;
  return (
    settingsCard(
      T("settings.debug_section"),
      settingsRow(
        T("settings.debug"),
        T("settings.debug_hint"),
        switchMarkup('data-setting-switch="common.debug"', debugOn, T("settings.debug"))
      )
    ) +
    settingsCard(
      T("settings.maintenance_section"),
      settingsRow(
        T("settings.check"),
        T("settings.check_hint"),
        '<button class="btn ghost small" data-action="integrity">' +
          esc(T("settings.check_quick")) + "</button>" +
          '<button class="btn ghost small" data-action="integrity_deep">' +
          esc(T("settings.check_deep")) + "</button>"
      ) +
        settingsRow(
          T("settings.clean_orphans"),
          T("settings.clean_orphans_hint"),
          '<button class="btn ghost small" data-action="fix_orphans">' +
            esc(T("settings.clean_orphans")) + "</button>"
        ) +
        settingsRow(
          T("settings.clear_stats"),
          T("settings.clear_stats_hint"),
          '<button class="btn danger-ghost small" data-action="clear_stats">' +
            esc(T("settings.clear_stats")) + "</button>"
        ) +
        settingsRow(
          T("settings.dirs"),
          T("settings.dirs_hint"),
          '<button class="btn ghost small" data-action="data_dir">' +
            esc(T("settings.data_dir")) + "</button>" +
            '<button class="btn ghost small" data-action="log_dir">' +
            esc(T("settings.log_dir")) + "</button>"
        )
    )
  );
}

function renderSettings(animate) {
  qsa(".settings-tab").forEach(function (tab) {
    tab.classList.toggle("is-active", tab.dataset.settings === state.settingsTab);
  });
  const body = qs("#settings-body");
  if (!state.data) return;
  if (state.settingsTab === "import") body.innerHTML = settingsImport();
  else if (state.settingsTab === "simple") body.innerHTML = settingsSimple();
  else if (state.settingsTab === "player") body.innerHTML = settingsPlayer();
  else if (state.settingsTab === "maintenance") body.innerHTML = settingsMaintenance();
  else body.innerHTML = settingsGeneral();

  if (animate) {
    body.classList.remove("is-entering");
    void body.offsetWidth;
    body.classList.add("is-entering");
  }
}

function settingValue(path) {
  return path.split(".").reduce(function (node, key) {
    return node && typeof node === "object" ? node[key] : undefined;
  }, state.data.settings);
}

async function patchSetting(path, value) {
  const parts = path.split(".");
  const patch = {};
  let node = patch;
  parts.forEach(function (key, index) {
    if (index === parts.length - 1) node[key] = value;
    else {
      node[key] = {};
      node = node[key];
    }
  });
  const data = await call("update_settings", patch);
  if (!data) return;
  if (data.ok === false) {
    apply(data);
    return;
  }
  // 开关和滑块本身就是最终状态，不需要重绘；重绘会把正在播的过渡直接换掉，
  // 也会把设置页的滚动位置弹回顶部。
  if (data.settings) state.data.settings = data.settings;
  if (data.status) state.data.status = data.status;

  // 后端可能夹取数值（比如 base 上限 0.99），这时输入框要跟着回正。
  let actual = data.settings;
  parts.forEach(function (key) {
    actual = actual && typeof actual === "object" ? actual[key] : undefined;
  });
  if (actual !== value) apply(data);
}

async function browseImportDir() {
  const picked = await call("browse_folder");
  if (!picked || !picked.path) return;
  const data = await call("update_settings", { import: { dir: picked.path } });
  if (data) apply(data);
}

async function refreshStatus() {
  const data = await call("refresh_status");
  if (data) apply(data);
}

function confirmFixOrphans() {
  openModal({
    title: T("settings.clean_orphans"),
    body: '<p class="modal-note">' + esc(T("settings.clean_orphans_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("settings.clean_orphans"),
        danger: true,
        onClick: async function () {
          const data = await call("fix_issues", "orphan_file");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function confirmClearStats() {
  openModal({
    title: T("settings.clear_stats"),
    body: '<p class="modal-note">' + esc(T("settings.clear_stats_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("settings.clear_stats"),
        danger: true,
        onClick: async function () {
          const data = await call("clear_all_stats");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}
