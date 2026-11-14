/* 启动：绑定全部事件、拉文案与快照，首次运行先走语言选择。 */
function bindEvents() {
  bindShellEvents();
  bindPlaylistEvents();
  bindLibraryEvents();
  bindPanelEvents();
}

/* 首次运行的语言选择器：和设置页「通用 · 语言」用的是同一个分段控件，
   不再用原生 select——它的弹出层由系统绘制，深色模式下根本没法看。 */
function firstRunLanguages(active) {
  const languages = (state.data && state.data.languages) || [];
  if (!languages.length) return "";
  return (
    '<div class="seg seg--block" id="firstrun-language">' +
    languages
      .map(function (item) {
        return (
          '<button class="seg-item' + (item.code === active ? " is-active" : "") +
          '" type="button" data-language="' + esc(item.code) + '">' +
          esc(item.name) + "</button>"
        );
      })
      .join("") +
    "</div>"
  );
}

function firstRunLanguage() {
  const active = qs("#firstrun-language .seg-item.is-active");
  return active ? active.dataset.language : state.data.language;
}

async function runFirstRun() {
  const data = state.data;

  openModal({
    title: T("firstrun.title"),
    dismissible: false,
    body:
      '<p class="modal-note" data-i18n="firstrun.text">' + esc(T("firstrun.text")) + "</p>" +
      '<div class="field-label firstrun-label" data-i18n="firstrun.title">' +
      esc(T("firstrun.title")) + "</div>" +
      firstRunLanguages(data.language),
    actions: [
      {
        label: T("firstrun.start"),
        primary: true,
        onClick: async function () {
          const snapshot = await call("complete_first_run", firstRunLanguage());
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
    onMount: function () {
      const host = qs("#firstrun-language");
      if (!host) return;
      host.addEventListener("click", function (event) {
        const button = event.target.closest("[data-language]");
        if (!button) return;
        // 选一下就立刻切成那种语言：用户不必先点「开始使用」才能看懂界面。
        qsa("#firstrun-language .seg-item").forEach(function (node) {
          node.classList.toggle("is-active", node === button);
        });
        previewLanguage(button.dataset.language);
      });
    },
  });

  const start = qs("#modal-actions .btn");
  if (start) start.dataset.i18n = "firstrun.start";
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
          // 关掉再开下一个：直接换内容会把「淡出」这一步吃掉，看起来像闪了一下。
          closeModal(function () {
            if (redirected) showRedirectNote(redirected);
          });
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
