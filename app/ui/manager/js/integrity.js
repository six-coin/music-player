/* 完整性检查：报告渲染、深检进度、按类别修复。 */
/* ---------- 完整性检查 ---------- */

function integrityBody(report) {
  if (report.ok) {
    return (
      '<div class="empty" style="min-height:200px"><h2>' + esc(T("integrity.ok")) + "</h2></div>"
    );
  }
  return (
    '<p class="modal-note">' + esc(T("integrity.count", { count: report.count })) + "</p>" +
    report.sections
      .map(function (section) {
        const items = section.items
          .map(function (item) {
            return "<li>" + esc(item) + "</li>";
          })
          .join("");
        const fix = section.fixable
          ? '<button class="btn soft small report-fix" data-fix="' + esc(section.key) + '">' +
            esc(T("integrity.fix")) + "</button>"
          : "";
        return (
          '<div class="report-section"><h3 class="report-title">' +
          esc(T("integrity." + section.key)) +
          '<span class="report-count">' + section.items.length + "</span>" +
          fix +
          '</h3><ul class="report-list">' + items + "</ul></div>"
        );
      })
      .join("")
  );
}

async function runDeepCheck() {
  const started = await call("start_integrity", true);
  if (!started || !started.task_id) return null;
  const taskId = started.task_id;

  return new Promise(function (resolve) {
    openModal({
      title: T("integrity.title"),
      body:
        '<p class="progress-text" id="deep-line"></p>' +
        '<div class="progress"><div class="progress-bar" id="deep-bar"></div></div>',
      dismissible: false,
      actions: [
        {
          label: T("integrity.cancel"),
          onClick: function () {
            call("cancel_task", taskId);
          },
        },
      ],
    });

    async function poll() {
      const task = await call("poll_task", taskId);
      if (!task) {
        modalDismissible = true;
        resolve(null);
        return;
      }
      if (task.state === "running") {
        const percent = task.total ? Math.round((task.done / task.total) * 100) : 0;
        const line = qs("#deep-line");
        const bar = qs("#deep-bar");
        if (line) {
          line.textContent = T("integrity.running", {
            done: formatSize(task.done),
            total: formatSize(task.total),
          });
        }
        if (bar) bar.style.width = percent + "%";
        window.setTimeout(poll, 250);
        return;
      }
      modalDismissible = true;
      if (task.state === "cancelled") {
        resolve(null);
        return;
      }
      resolve(task.result || null);
    }

    poll();
  });
}

async function openIntegrity(options) {
  const settings = options || {};
  let report = settings.report || null;
  if (!report) {
    report = settings.deep ? await runDeepCheck() : await call("run_integrity");
  }
  if (!report) {
    closeModal();
    toast(T("integrity.cancelled"));
    return;
  }

  const fixable = report.sections.some(function (section) {
    return section.fixable;
  });
  const actions = [];
  if (fixable) {
    actions.push({
      label: T("integrity.fix_all"),
      primary: true,
      onClick: function () {
        fixIssues("");
      },
    });
  }
  actions.push({
    label: T("integrity.deep"),
    onClick: function () {
      openIntegrity({ deep: true });
    },
  });
  actions.push({ label: T("action.close"), primary: !fixable, onClick: closeModal });

  openModal({
    title: T("integrity.title"),
    body: integrityBody(report),
    wide: true,
    actions: actions,
    onMount: function () {
      qsa("[data-fix]").forEach(function (button) {
        button.addEventListener("click", function () {
          fixIssues(button.dataset.fix);
        });
      });
    },
  });
}

async function fixIssues(kind) {
  const data = await call("fix_issues", kind);
  if (!data) return;
  apply(data);
  toast(data.message || T("integrity.fixed", { count: 0 }), true);
  openIntegrity();
}
