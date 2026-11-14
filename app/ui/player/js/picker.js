/* 「选一首循环」弹窗。 */
/* ---------- 选歌弹窗 ---------- */

async function openPicker() {
  state.pickerOpen = true;
  state.pickerIndex = 0;
  window.clearTimeout(state.pickerCloseTimer);
  qs("#picker").classList.remove("is-closing");
  qs("#picker").hidden = false;
  qs("#app").setAttribute("inert", "");
  qs("#picker-search").value = "";
  await loadPicker("");
  qs("#picker-search").focus();
}

function closePicker() {
  state.pickerOpen = false;
  qs("#app").removeAttribute("inert");
  const picker = qs("#picker");
  picker.classList.add("is-closing");
  window.clearTimeout(state.pickerCloseTimer);
  state.pickerCloseTimer = window.setTimeout(function () {
    picker.hidden = true;
    picker.classList.remove("is-closing");
  }, 160);
}

async function loadPicker(query) {
  const result = await call("list_songs", query);
  state.pickerItems = (result && result.items) || [];
  state.pickerIndex = 0;
  renderPicker();
}

function renderPicker() {
  const list = qs("#picker-list");
  if (!state.pickerItems.length) {
    list.innerHTML = '<div class="picker-empty">' + esc(T("player.pick.empty")) + "</div>";
    return;
  }
  list.innerHTML = state.pickerItems
    .map(function (item, index) {
      const meta = [item.authors || T("player.unknown_author")];
      if (item.in_playlist) meta.push(T("player.pick.in_playlist"));
      return (
        '<button type="button" role="option" aria-selected="' +
        (index === state.pickerIndex ? "true" : "false") +
        '" class="picker-item' +
        (index === state.pickerIndex ? " is-active" : "") +
        '" data-md5="' +
        esc(item.md5) +
        '" data-index="' +
        index +
        '">' +
        '<span class="picker-name">' +
        esc(item.title) +
        "</span>" +
        '<span class="picker-meta">' +
        esc(meta.join(" · ")) +
        "</span></button>"
      );
    })
    .join("");
}

function movePicker(delta) {
  if (!state.pickerItems.length) return;
  state.pickerIndex =
    (state.pickerIndex + delta + state.pickerItems.length) % state.pickerItems.length;
  renderPicker();
  const active = qs('.picker-item[data-index="' + state.pickerIndex + '"]');
  if (active) active.scrollIntoView({ block: "nearest" });
}

function choosePicker(index) {
  const item = state.pickerItems[index];
  if (!item) return;
  closePicker();
  call("pick_loop_song", item.md5, Math.round(state.playedMs)).then(apply);
}
