/* 设置页：五个分页的渲染与逐项写回。
   分页顺序：通用 → 音乐库管理器 → 轻量音乐播放器 → 音乐播放器 → 关于。
   管理器自己的东西（试听、导入、维护）都在「音乐库管理器」里，通用页只放
   三端共享的外观与自适应默认值。 */
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

/* ---------- 快捷键 ---------- */

/* 动作清单与出厂键都来自快照：后端是唯一的真相，前端不另抄一份表。 */
function keyMeta() {
  return (state.data && state.data.keys) || {};
}

function keyActions(group) {
  return (keyMeta().actions || {})[group] || [];
}

function keyDefaults(group) {
  return (keyMeta().defaults || {})[group] || {};
}

function currentKey(group, action) {
  const section = (state.data && state.data.settings && state.data.settings[group]) || {};
  return (section.keys || {})[action] || keyDefaults(group)[action] || "";
}

function keyRow(group, action) {
  const spec = currentKey(group, action);
  const fallback = keyDefaults(group)[action] || "";
  return settingsRow(
    T("keys." + group + "." + action),
    "",
    '<button class="keycap" type="button" data-key-group="' + esc(group) +
      '" data-key-action="' + esc(action) + '">' +
      esc(prettyKey(spec)) + "</button>" +
      '<button class="btn ghost small" data-key-reset="' + esc(group + ":" + action) +
      '" title="' + esc(T("settings.keys_reset_to", { key: prettyKey(fallback) })) + '"' +
      (spec === fallback ? " disabled" : "") + ">" +
      esc(T("settings.keys_reset")) + "</button>"
  );
}

function settingsKeys(group) {
  const actions = keyActions(group);
  if (!actions.length) return "";
  const notes = {
    manager: T("settings.keys_fixed"),
    simple: T("settings.keys_simple_hint"),
    player: T("settings.keys_player_hint"),
  };
  const hint = T("settings.keys_hint") + (notes[group] ? " · " + notes[group] : "");
  return settingsCard(
    T("settings.keys_section"),
    actions
      .map(function (action) {
        return keyRow(group, action);
      })
      .join("") +
      '<div class="settings-actions"><button class="btn ghost small" data-key-reset-all="' +
      esc(group) + '">' + esc(T("settings.keys_reset_all")) + "</button></div>",
    hint
  );
}

/* 录制中的那一行：按键只服务录制，全局快捷键让路。 */
function beginKeyCapture(node) {
  endKeyCapture();
  state.recording = {
    group: node.dataset.keyGroup,
    action: node.dataset.keyAction,
    node: node,
  };
  node.classList.add("is-recording");
  node.textContent = T("settings.keys_recording");
}

function endKeyCapture() {
  const recording = state.recording;
  state.recording = null;
  if (!recording || !recording.node) return;
  recording.node.classList.remove("is-recording");
  recording.node.textContent = prettyKey(currentKey(recording.group, recording.action));
}

/* 只换这一行的显示：整页重绘会把设置页的滚动位置弹回顶部。 */
function paintKeyRow(node, group, action) {
  if (!node) return;
  node.textContent = prettyKey(currentKey(group, action));
  const reset = node.parentNode ? node.parentNode.querySelector("[data-key-reset]") : null;
  if (reset) reset.disabled = currentKey(group, action) === keyDefaults(group)[action];
}

async function saveKey(group, action, spec, node) {
  endKeyCapture();
  const data = await call("set_shortcut", group, action, spec);
  if (!data) return;
  if (data.ok === false) {
    if (data.reason === "conflict") {
      toast(
        T("settings.keys_conflict", {
          key: prettyKey(spec),
          action: T("keys." + group + "." + (data.action || "")),
        }),
        false
      );
    } else if (data.reason === "unsupported") {
      toast(T("settings.keys_console_unsupported"), false);
    } else {
      toast(T("settings.keys_invalid"), false);
    }
    return;
  }
  if (data.settings) state.data.settings = data.settings;
  if (data.keys) state.data.keys = data.keys;
  paintKeyRow(node, group, action);
}

async function resetKeyGroup(group) {
  const patch = {};
  patch[group] = { keys: keyDefaults(group) };
  const data = await call("update_settings", patch);
  if (!data) return;
  if (data.settings) state.data.settings = data.settings;
  renderSettings();
  toast(T("settings.keys_reset_done"));
}

function settingsGeneral() {
  const common = (state.data.settings && state.data.settings.common) || {};
  const adapt = common.adaptation || {};

  const themes = [
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

  const adaptRow = function (key, label, unit, min, max, step, value) {
    return settingsRow(
      label,
      T("adaptation." + key + "_hint") + " · " + T("adaptation.range", { min: min, max: max }),
      '<input class="input" type="number" data-default="' + key + '" value="' +
        esc(value) + '" min="' + min + '" max="' + max + '" step="' + step +
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

  // 级别用与语言同一套分段控件：四个值，点一下就切，不用展开菜单。
  const logLevels = [
    ["DEBUG", T("settings.log_level_debug")],
    ["INFO", T("settings.log_level_info")],
    ["WARNING", T("settings.log_level_warning")],
    ["ERROR", T("settings.log_level_error")],
  ];
  const currentLevel = common.log_level || "INFO";
  const logLevelSeg =
    '<div class="seg" id="log-level-seg">' +
    logLevels
      .map(function (item) {
        return (
          '<button class="seg-item' + (item[0] === currentLevel ? " is-active" : "") +
          '" type="button" data-log-level="' + item[0] + '">' + esc(item[1]) + "</button>"
        );
      })
      .join("") +
    "</div>";

  return (
    settingsCard(
      T("settings.appearance"),
      settingsRow(T("settings.theme"), T("settings.theme_hint"), themeSeg) +
        settingsRow(T("settings.language"), T("settings.language_hint"), languageSeg)
    ) +
    settingsCard(
      T("settings.adaptation_defaults"),
      adaptRow("window", T("adaptation.window"), T("adaptation.times"), 10, 1000, 1, adapt.window) +
        adaptRow(
          "min_plays",
          T("adaptation.min_plays"),
          T("adaptation.times"),
          0,
          1000,
          1,
          adapt.min_plays
        ) +
        adaptRow(
          "base",
          T("adaptation.base"),
          T("adaptation.percent"),
          1,
          99,
          1,
          Math.round((adapt.base === undefined ? 0.95 : adapt.base) * 100)
        ) +
        adaptRow(
          "skip_seconds",
          T("adaptation.skip_seconds"),
          T("adaptation.seconds"),
          5,
          300,
          1,
          adapt.skip_seconds
        ),
      T("settings.adaptation_hint")
    ) +
    settingsCard(
      T("settings.playback_section"),
      settingsRow(
        T("settings.record_total_plays"),
        T("settings.record_total_plays_hint"),
        switchMarkup(
          'data-setting-switch="common.record_total_plays"',
          common.record_total_plays !== false,
          T("settings.record_total_plays")
        )
      )
    ) +
    settingsCard(
      T("settings.logs_section"),
      settingsRow(T("settings.log_level"), T("settings.log_level_hint"), logLevelSeg) +
        settingsRow(
          T("settings.log_cleanup"),
          T("settings.log_cleanup_hint"),
          switchMarkup(
            'data-setting-switch="common.log_cleanup"',
            common.log_cleanup !== false,
            T("settings.log_cleanup")
          )
        ) +
        settingsRow(
          T("settings.log_retention_days"),
          T("settings.log_retention_days_hint"),
          '<input class="input" id="log-retention-days" type="number" value="' +
            esc(common.log_retention_days === undefined ? 30 : common.log_retention_days) +
            '" min="1" max="365" step="1" style="width:110px">' +
            '<span class="adapt-unit">' + esc(T("settings.days")) + "</span>"
        ),
      T("settings.logs_hint")
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
  return (
    settingsCard(
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
          T("settings.default_playlist"),
          T("settings.default_playlist_hint"),
          '<button class="btn ghost small" data-action="goto_default">' +
            esc(T("settings.goto")) + "</button>"
        ),
      T("settings.simple_hint")
    ) + settingsKeys("simple")
  );
}

function settingsPlayer() {
  const section = (state.data.settings && state.data.settings.player) || {};
  const volume = Math.round((section.volume === undefined ? 0.2 : section.volume) * 100);

  return (
    settingsCard(
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
    ) + settingsKeys("player")
  );
}

/* 「音乐库管理器」页：只属于管理器的几件事——试听、导入、维护。
   维护卡片里放完整性检查、孤儿文件、统计与目录，还有调试状态。 */
function settingsManager() {
  const data = state.data || {};
  const audition = (data.settings || {}).audition || {};
  const auditionVolume = Math.round((audition.volume ?? 0.2) * 100);
  const debugOn = ((data.settings || {}).common || {}).debug === true;

  return (
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
    settingsImport() +
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
        ) +
        settingsRow(
          T("settings.debug"),
          T("settings.debug_hint"),
          switchMarkup('data-setting-switch="common.debug"', debugOn, T("settings.debug"))
        )
    ) + settingsKeys("manager")
  );
}

function settingsAbout() {
  const data = state.data || {};
  const next = data.data_dir_next || "";
  // 输入框显示的是「重启后生效的落点」，没有待生效的值就是当前目录。
  const shown = next || data.data_dir || "";

  return settingsCard(
    T("about.title"),
    settingsRow(
      T("about.data_dir"),
      next ? T("about.data_dir_pending", { path: next }) : T("about.data_dir_hint"),
      '<input class="input path-input" id="data-dir" spellcheck="false" value="' +
        esc(shown) + '">' +
        '<button class="btn ghost small" data-action="about_data_dir">' +
        esc(T("about.data_dir_change")) + "</button>" +
        '<button class="btn ghost small" data-action="about_data_dir_reset">' +
        esc(T("about.data_dir_reset")) + "</button>"
    ) +
      settingsRow(
        T("about.readme"),
        T("about.readme_hint"),
        '<button class="btn ghost small" data-action="about_readme">' +
          esc(T("about.readme")) + "</button>"
      ) +
      settingsRow(
        T("about.reset"),
        T("about.reset_hint"),
        '<button class="btn danger-ghost small" data-action="about_reset">' +
          esc(T("about.reset")) + "</button>"
      ) +
      settingsRow(
        T("about.version"),
        "",
        '<span class="path-text">' + esc(data.version || "") + "</span>"
      )
  );
}

function renderSettings(animate) {
  // 重绘会换掉正在录制的那一行，录制状态先收干净。
  endKeyCapture();
  qsa(".settings-tab").forEach(function (tab) {
    tab.classList.toggle("is-active", tab.dataset.settings === state.settingsTab);
  });
  const body = qs("#settings-body");
  if (!state.data) return;
  if (state.settingsTab === "manager") body.innerHTML = settingsManager();
  else if (state.settingsTab === "simple") body.innerHTML = settingsSimple();
  else if (state.settingsTab === "player") body.innerHTML = settingsPlayer();
  else if (state.settingsTab === "about") body.innerHTML = settingsAbout();
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

/* ---------- 关于 ---------- */

function openAboutReadme() {
  call("get_readme").then(function (data) {
    const body =
      data && data.markdown
        ? renderMarkdown(data.markdown)
        : '<p class="modal-note">' + esc(T("about.readme_missing")) + "</p>";
    openModal({
      title: T("about.readme_title"),
      body: body,
      wide: true,
      actions: [{ label: T("action.close"), primary: true, onClick: closeModal }],
    });
  });
}

function confirmResetSettings() {
  openModal({
    title: T("about.reset"),
    body: '<p class="modal-note">' + esc(T("about.reset_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("about.reset"),
        danger: true,
        onClick: async function () {
          const data = await call("reset_settings");
          closeModal();
          if (!data) return;
          await loadStrings();
          applyStrings();
          apply(data);
          renderSettings();
          toast(data.message || T("about.reset_done"));
        },
      },
    ],
  });
}

async function applyDataDir(raw) {
  const value = String(raw || "").trim();
  if (!value) {
    renderSettings();
    return;
  }
  const data = await call("set_data_dir", value);
  if (!data) return;
  apply(data);
  renderSettings();
  if (data.message) toast(data.message);
}

async function changeDataDir() {
  const input = qs("#data-dir");
  const current = String(state.data.data_dir_next || state.data.data_dir || "").trim();
  const typed = input ? input.value.trim() : "";
  // 输入框改过就按输入的落点走，没改过才去选目录。
  if (typed && typed !== current) {
    await applyDataDir(typed);
    return;
  }
  const picked = await call("browse_folder");
  if (!picked || !picked.path) return;
  await applyDataDir(picked.path);
}

async function resetDataDir() {
  const data = await call("reset_data_dir");
  if (!data) return;
  apply(data);
  renderSettings();
  if (data.message) toast(data.message);
}
