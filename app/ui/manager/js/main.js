/* 启动：绑定全部事件、拉文案与快照，首次运行先走语言选择。 */
function bindEvents() {
  bindShellEvents();
  bindPlaylistEvents();
  bindLibraryEvents();
  bindPanelEvents();
}

async function runFirstRun() {
  const data = state.data;
  const options = (data.languages || [])
    .map(function (item) {
      return (
        '<option value="' + esc(item.code) + '"' +
        (item.code === data.language ? " selected" : "") +
        ">" + esc(item.name) + "</option>"
      );
    })
    .join("");

  openModal({
    title: T("firstrun.title"),
    dismissible: false,
    body:
      '<p class="modal-note" data-i18n="firstrun.text">' + esc(T("firstrun.text")) + "</p>" +
      '<label class="field-label" for="firstrun-language" data-i18n="firstrun.title">' +
      esc(T("firstrun.title")) + "</label>" +
      '<select class="input" id="firstrun-language">' + options + "</select>",
    actions: [
      {
        label: T("firstrun.start"),
        primary: true,
        onClick: async function () {
          const select = qs("#firstrun-language");
          const snapshot = await call("complete_first_run", select ? select.value : data.language);
          closeModal();
          if (snapshot) {
            await loadStrings();
            applyStrings();
            apply(snapshot);
          }
          await showFirstRunReadme(data.redirected_from);
        },
      },
    ],
  });

  // 下拉框一改就把界面切成那种语言：用户不必先点「开始使用」才能看懂界面。
  const start = qs("#modal-actions .btn");
  if (start) start.dataset.i18n = "firstrun.start";
  const select = qs("#firstrun-language");
  if (select) {
    select.addEventListener("change", function () {
      previewLanguage(select.value);
    });
  }
}

async function previewLanguage(code) {
  const result = await call("preview_language", code);
  if (!result) return;
  await loadStrings();
  applyStrings();
  if (state.data) state.data.language = result.language;
  document.documentElement.lang = result.language;
  const title = qs("#modal-title");
  if (title) title.textContent = T("firstrun.title");
}

async function showFirstRunReadme(redirected) {
  const readme = await call("get_readme");
  const body =
    readme && readme.markdown
      ? renderMarkdown(readme.markdown)
      : '<p class="modal-note">' + esc(T("about.readme_missing")) + "</p>";

  openModal({
    title: T("firstrun.readme_title"),
    dismissible: false,
    wide: true,
    body: '<p class="modal-note">' + esc(T("firstrun.readme_text")) + "</p>" + body,
    actions: [
      {
        label: T("firstrun.readme_close"),
        primary: true,
        onClick: function () {
          closeModal();
          if (redirected) showRedirectNote(redirected);
        },
      },
    ],
  });
}

function showRedirectNote(origin) {
  const key = "firstrun.origin." + origin;
  const label = (state.strings || {})[key] ? T(key) : origin;
  openModal({
    title: T("firstrun.redirect_title"),
    dismissible: false,
    body:
      '<p class="modal-note">' +
      esc(T("firstrun.redirect_text", { origin: label, manager: T("app.title") })) +
      "</p>",
    actions: [{ label: T("firstrun.readme_close"), primary: true, onClick: closeModal }],
  });
}

async function init() {
  bindEvents();
  initSelects();
  await loadStrings();
  applyStrings();
  setupSortSelect();
  apply(await call("get_state"));
  if (state.data && state.data.first_run) await runFirstRun();
}

if (bridge()) {
  init();
} else {
  window.addEventListener("pywebviewready", init, { once: true });
}
