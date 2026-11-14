/* 导入：单文件进度、批量向导三步。 */
/* ---------- 导入 ---------- */

async function doImport() {
  const result = await call("browse_import");
  if (!result || !result.paths || !result.paths.length) return;
  if (result.paths.length === 1) {
    const started = await call("start_import", result.paths);
    if (started && started.task_id) openImportModal(started.task_id);
    return;
  }
  const preview = await call("preview_import", result.paths);
  if (!preview || !preview.items.length) return;
  openWizard(preview.items);
}

function progressMarkup() {
  return (
    '<p class="progress-text" id="import-line"></p>' +
    '<div class="progress"><div class="progress-bar" id="import-bar"></div></div>' +
    '<div id="import-errors"></div>'
  );
}

function openImportModal(taskId) {
  openModal({
    title: T("import.title"),
    body: progressMarkup(),
    dismissible: false,
    actions: [],
  });
  runImportTask(taskId, []);
}

function runImportTask(taskId, tagUids) {
  let misses = 0;

  async function poll() {
    const task = await call("poll_task", taskId);
    if (!task) {
      misses += 1;
      if (misses < 3) {
        window.setTimeout(poll, 500);
        return;
      }
      qs("#import-line").textContent = T("import.failed");
      modalDismissible = true;
      qs("#modal-close").hidden = false;
      return;
    }

    if (task.state === "running") {
      const percent = task.total ? Math.round((task.done / task.total) * 100) : 0;
      qs("#import-line").textContent = T("import.running", {
        done: task.done,
        total: task.total,
        current: task.current,
      });
      qs("#import-bar").style.width = percent + "%";
      window.setTimeout(poll, 300);
      return;
    }

    await finishImport(task, tagUids);
  }

  poll();
}

async function finishImport(task, tagUids) {
  qs("#import-line").textContent = T("import.done");
  qs("#import-bar").style.width = "100%";

  const summary = document.createElement("p");
  summary.className = "modal-note";
  summary.textContent = T("import.summary", {
    ok: task.imported.length,
    failed: task.errors.length,
  });
  qs("#import-errors").appendChild(summary);

  if (task.errors.length) {
    const list = document.createElement("ul");
    list.className = "report-list";
    task.errors.forEach(function (item) {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    qs("#import-errors").appendChild(list);
  }

  // 先把「关闭」放出来，后面即使刷新状态失败，用户也不会被锁在弹窗里。
  const actions = qs("#modal-actions");
  const button = document.createElement("button");
  button.className = "btn primary";
  button.textContent = T("action.close");
  button.addEventListener("click", closeModal);
  actions.appendChild(button);
  modalDismissible = true;
  qs("#modal-close").hidden = false;

  let data = null;
  if (tagUids.length && task.imported.length) {
    data = await call("batch_add_tags", task.imported, tagUids, false);
  }
  if (!data) data = await call("get_state");
  if (data) apply(data);

  if (task.imported.length) {
    const selected = await call("select_item", "music", task.imported[0]);
    if (selected) apply(selected);
  }
}
/* ---------- 批量导入向导 ---------- */

const wizard = { rows: [], tags: new Set(), step: 1 };

function openWizard(items) {
  wizard.rows = items.map(function (item) {
    return {
      path: item.path,
      filename: item.filename,
      title: item.title || "",
      authors: (item.authors || []).join(", "),
    };
  });
  wizard.tags = new Set();
  wizard.step = 1;
  renderWizard();
}

function renderWizard() {
  const step = wizard.step;
  const stepNames = {
    1: T("import.step_files"),
    2: T("import.step_tags"),
    3: T("import.step_confirm"),
  };
  let body = "";
  if (step === 1) body = wizardFiles();
  else if (step === 2) body = wizardTags();
  else body = wizardConfirm();

  const actions = [{ label: T("action.cancel"), onClick: closeModal }];
  if (step > 1) {
    actions.push({
      label: T("import.prev"),
      onClick: function () {
        wizard.step -= 1;
        renderWizard();
      },
    });
  }
  if (step < 3) {
    actions.push({
      label: T("import.next"),
      primary: true,
      onClick: function () {
        wizard.step += 1;
        renderWizard();
      },
    });
  } else {
    actions.push({ label: T("import.start"), primary: true, onClick: runWizardImport });
  }

  openModal({
    title: T("import.wizard_title"),
    body:
      '<p class="modal-note">' +
      esc(T("import.step", { current: step, total: 3 })) +
      " · " +
      esc(stepNames[step]) +
      "</p>" +
      body,
    wide: true,
    actions: actions,
    onMount: function () {
      mountWizard(step);
    },
  });
}

function wizardFiles() {
  if (!wizard.rows.length) {
    return '<p class="row-empty">' + esc(T("import.empty")) + "</p>";
  }
  const rows = wizard.rows
    .map(function (row, index) {
      return (
        '<div class="wizard-row" data-index="' + index + '">' +
        '<div class="wizard-head"><span class="wizard-file" title="' +
        esc(row.filename) + '">' + esc(row.filename) + "</span>" +
        '<button class="icon-btn" data-remove="' + index + '" aria-label="' +
        esc(T("action.remove")) + '">×</button></div>' +
        '<div class="wizard-fields">' +
        '<input class="input" data-field="title" value="' + esc(row.title) +
        '" placeholder="' + esc(T("import.title_field")) + '">' +
        '<input class="input" data-field="authors" value="' + esc(row.authors) +
        '" placeholder="' + esc(T("import.authors_field")) + '">' +
        "</div></div>"
      );
    })
    .join("");
  return (
    '<p class="modal-note">' +
    esc(T("import.files_note", { count: wizard.rows.length })) +
    "</p>" +
    '<div class="wizard-list">' + rows + "</div>"
  );
}

function wizardTags() {
  const groups = state.data.library.tag_groups || [];
  if (!groups.length) {
    return '<p class="row-empty">' + esc(T("batch.no_tags")) + "</p>";
  }
  const sections = groups
    .map(function (group) {
      const chips = group.tags
        .map(function (tag) {
          const on = wizard.tags.has(tag.uid);
          return (
            '<button class="chip-toggle' + (on ? " is-on" : "") + '" data-wizard-tag="' +
            esc(tag.uid) + '">' + esc(tag.name) + "</button>"
          );
        })
        .join("");
      return (
        '<div class="tag-group"><div class="tag-group-head"><span>' +
        esc(group.name) + '</span></div><div class="chips">' + chips + "</div></div>"
      );
    })
    .join("");
  return '<p class="modal-note">' + esc(T("import.tags_note")) + "</p>" + sections;
}

function wizardConfirm() {
  const rows = wizard.rows
    .map(function (row) {
      const title = row.title.trim() || row.filename;
      const authors = row.authors.trim();
      return "<li>" + esc(title) + (authors ? " · " + esc(authors) : "") + "</li>";
    })
    .join("");
  const cleanDefault = Boolean(
    state.data.settings && state.data.settings.import && state.data.settings.import.clean_audio
  );
  return (
    '<p class="modal-note">' +
    esc(T("import.confirm_note", { count: wizard.rows.length })) +
    "</p>" +
    '<ul class="report-list">' + rows + "</ul>" +
    '<label class="check" style="margin-top:14px"><input type="checkbox" id="wizard-clean"' +
    (cleanDefault ? " checked" : "") +
    "><span>" +
    esc(T("import.clean")) +
    "</span></label>"
  );
}

function mountWizard(step) {
  const body = qs("#modal-body");
  if (step === 1) {
    body.oninput = function (event) {
      const row = event.target.closest("[data-index]");
      const field = event.target.dataset.field;
      if (!row || !field) return;
      wizard.rows[Number(row.dataset.index)][field] = event.target.value;
    };
    body.onclick = function (event) {
      const remove = event.target.closest("[data-remove]");
      if (!remove) return;
      wizard.rows.splice(Number(remove.dataset.remove), 1);
      if (!wizard.rows.length) {
        closeModal();
        return;
      }
      renderWizard();
    };
  } else if (step === 2) {
    body.onclick = function (event) {
      const chip = event.target.closest("[data-wizard-tag]");
      if (!chip) return;
      const uid = chip.dataset.wizardTag;
      if (wizard.tags.has(uid)) wizard.tags.delete(uid);
      else wizard.tags.add(uid);
      chip.classList.toggle("is-on", wizard.tags.has(uid));
    };
  }
}

async function runWizardImport() {
  const cleanBox = qs("#wizard-clean");
  const clean = cleanBox ? cleanBox.checked : null;
  const items = wizard.rows.map(function (row) {
    return {
      path: row.path,
      title: row.title.trim(),
      authors: row.authors
        .split(/[,，]/)
        .map(function (name) {
          return name.trim();
        })
        .filter(Boolean),
    };
  });

  const started = await call("start_import", items, clean);
  if (!started || !started.task_id) return;

  openModal({
    title: T("import.wizard_title"),
    body: progressMarkup(),
    dismissible: false,
    actions: [],
  });
  runImportTask(started.task_id, Array.from(wizard.tags));
}
