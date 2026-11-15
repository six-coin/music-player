/* 自适应统计：右侧抽屉与歌曲详情的统计条。 */
/* ---------- 统计抽屉 ---------- */

function percent(value) {
  return (Math.round(value * 1000) / 10).toFixed(1).replace(/\.0$/, "") + "%";
}

function rateCell(rate) {
  const width = Math.min(100, Math.round(rate * 100));
  return (
    '<div class="rate"><div class="rate-track"><div class="rate-fill' +
    (rate >= 0.6 ? " is-high" : "") + '" style="width:' + width + '%"></div></div>' +
    '<span class="rate-text">' + esc(percent(rate)) + "</span></div>"
  );
}

function statsTable(rows, options) {
  const settings = options || {};
  const head =
    "<tr><th>" + esc(T("adaptation.col_song")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_records")) + "</th>" +
    "<th>" + esc(T("adaptation.col_rate")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_total")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_full")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_auto")) + "</th>" +
    '<th class="num">' + esc(T("adaptation.col_probability")) + "</th>" +
    (settings.reset ? "<th></th>" : "") + "</tr>";

  const body = rows
    .map(function (row) {
      const reset = settings.reset
        ? '<td><button class="btn ghost small" data-reset-md5="' + esc(row.md5) +
          '" data-reset-title="' + esc(row.title) + '">' +
          esc(T("adaptation.reset_one")) + "</button></td>"
        : "";
      return (
        '<tr><td class="cell-title" title="' + esc(row.title) + '">' + esc(row.title) + "</td>" +
        '<td class="num">' + row.total + "</td>" +
        "<td>" + rateCell(row.rate) + "</td>" +
        '<td class="num">' + (row.total_plays || 0) + "</td>" +
        '<td class="num">' + row.full_plays + "</td>" +
        '<td class="num">' + row.auto_skipped + "</td>" +
        '<td class="num">' + esc(percent(row.probability)) + "</td>" +
        reset +
        "</tr>"
      );
    })
    .join("");

  return '<table class="drawer-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table>";
}

async function openStatsDrawer(playlist) {
  const data = await call("get_playlist_stats", playlist.uid);
  if (!data || !data.ok) {
    toast(T("adaptation.stats_failed"), false);
    return;
  }
  state.drawer = playlist.uid;
  qs("#drawer-title").textContent = T("adaptation.stats_title", { name: playlist.title });
  renderDrawer(data);
  qs("#drawer").hidden = false;
}

function closeDrawer() {
  if (!state.drawer) return;
  state.drawer = null;
  const drawer = qs("#drawer");
  drawer.classList.add("is-closing");
  window.setTimeout(function () {
    if (state.drawer) return;
    drawer.hidden = true;
    drawer.classList.remove("is-closing");
    qs("#drawer-body").innerHTML = "";
  }, 160);
}

/* 清空一首歌的记录也要问一句：再小的数据点下去就没了，没有撤销。 */
function confirmClearSongStats(md5, title) {
  const uid = state.drawer;
  if (!uid || !md5) return;
  openModal({
    title: T("adaptation.reset_one_title"),
    body:
      '<p class="modal-note">' +
      esc(T("adaptation.reset_one_confirm", { name: title || md5.slice(0, 8) })) +
      "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("adaptation.reset_one"),
        danger: true,
        onClick: async function () {
          const data = await call("reset_stats", uid, md5);
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function confirmClearPlaylistStats() {
  const uid = state.drawer;
  if (!uid) return;
  openModal({
    title: T("adaptation.reset_all"),
    body: '<p class="modal-note">' + esc(T("adaptation.reset_all_confirm")) + "</p>",
    actions: [
      { label: T("action.cancel"), onClick: closeModal },
      {
        label: T("adaptation.reset_all"),
        danger: true,
        onClick: async function () {
          const data = await call("reset_stats", uid, "");
          if (!data) return;
          closeModal();
          apply(data);
        },
      },
    ],
  });
}

function renderDrawer(data) {
  const params = data.params || {};
  const note = T("adaptation.stats_note", {
    window: params.window,
    min: params.min_plays,
    base: params.base_percent,
    seconds: params.skip_seconds,
  });
  const rows = data.rows || [];
  const body = rows.length
    ? statsTable(rows, { reset: true })
    : '<p class="drawer-note">' + esc(T("adaptation.stats_empty")) + "</p>";

  qs("#drawer-body").innerHTML =
    '<p class="drawer-note">' + esc(note) + "</p>" +
    '<div class="settings-actions" style="padding-bottom:10px">' +
    '<button class="btn ghost small" data-reset-all="1">' +
    esc(T("adaptation.reset_all")) + "</button></div>" +
    body;
}

async function refreshDrawer() {
  if (!state.drawer) return;
  const data = await call("get_playlist_stats", state.drawer);
  if (data && data.ok) renderDrawer(data);
}

async function loadMusicStats(md5) {
  const host = qs("#music-adapt");
  if (!host) return;
  const data = await call("get_music_stats", md5);
  if (!data || !data.ok) {
    host.textContent = T("adaptation.no_records");
    return;
  }

  const source = qs("#music-adapt-source");
  if (source && data.playlist) {
    source.textContent = T("adaptation.song_source", { name: data.playlist.title });
  }

  const cell = function (value, label) {
    return (
      '<div class="adapt-cell"><span class="adapt-value">' + esc(value) +
      '</span><span class="adapt-label">' + esc(label) + "</span></div>"
    );
  };

  if (!data.in_playlist) {
    // 自适应按歌单算，这首歌不在默认歌单里就没有那几项；总播放次数是全库的，
    // 照样能看。
    host.innerHTML =
      cell(String(data.total_plays || 0), T("adaptation.col_total")) +
      '<p class="tag-hint">' + esc(T("adaptation.not_in_default")) + "</p>";
    return;
  }
  host.innerHTML =
    cell(String(data.total), T("adaptation.col_records")) +
    cell(percent(data.rate), T("adaptation.col_rate")) +
    cell(String(data.total_plays || 0), T("adaptation.col_total")) +
    cell(String(data.full_plays || 0), T("adaptation.col_full")) +
    cell(String(data.auto_skipped), T("adaptation.col_auto")) +
    cell(percent(data.probability), T("adaptation.col_probability"));
}
