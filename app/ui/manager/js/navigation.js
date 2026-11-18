/* 分区跳转与「当前选中项」：所有点击最终都落到这里的几个函数上。 */
async function goSection(section) {
  applyNav(section);
  const data = await call("select_section", section);
  if (data) apply(data);

  // 数量都不多，进分区时直接落在第一个，省掉一次点击。
  if (section === "playlists" && state.activeKind !== "playlist") {
    const first = ((state.data && state.data.playlists) || [])[0];
    if (first) selectPlaylist(first.uid);
  } else if (section === "tags" && state.activeKind !== "tag_group") {
    const first = ((state.data && state.data.library.tag_groups) || [])[0];
    if (first) selectTagGroup(first.uid);
  } else if (section === "authors" && state.activeKind !== "author") {
    const first = ((state.data && state.data.library.authors) || [])[0];
    if (first) selectAuthor(first.uid);
  } else if (section === "pomodoro" && !isPomodoroKind(state.activeKind)) {
    const overview = await call("select_pomodoro_overview");
    if (overview) apply(overview);
  }
}

/* 进入番茄分区时，如果上一个选中项还是歌曲 / 歌单，就落到总览。 */
function isPomodoroKind(kind) {
  return (
    kind === "pomodoro" ||
    kind === "duration_mode" ||
    kind === "background" ||
    kind === "ring" ||
    kind === "environment" ||
    kind === "pomodoro_overview"
  );
}

function animateDetail(id) {
  const pane = qs("#" + id);
  if (!pane) return;
  pane.scrollTop = 0;
  pane.classList.remove("is-entering");
  void pane.offsetWidth;
  pane.classList.add("is-entering");
}

/* 切换条目时分两步：先只把列表的高亮挪过去，等新快照回来再画详情并播入场动画。
   如果先连详情一起画，用户会看到目标内容「啪」地出现，然后才从头播动画——
   看起来就是闪一下。 */
async function selectMusic(md5) {
  const same = state.activeKind === "music" && state.active === md5;
  state.active = md5;
  state.activeKind = "music";
  state.selection = new Set([md5]);
  state.anchor = md5;
  renderSongList();
  renderSelectionBar();
  const data = await call("select_item", "music", md5);
  if (!data) return;
  apply(data);
  if (!same) animateDetail("song-detail");
}

async function selectPlaylist(uid) {
  const same = state.activeKind === "playlist" && state.active === uid;
  state.active = uid;
  state.activeKind = "playlist";
  renderPlaylistList();
  const data = await call("select_item", "playlist", uid);
  if (!data) return;
  apply(data);
  if (!same) animateDetail("playlist-detail");
}

async function selectTagGroup(uid) {
  const same = state.activeKind === "tag_group" && state.active === uid;
  state.active = uid;
  state.activeKind = "tag_group";
  renderTagList();
  const data = await call("select_item", "tag_group", uid);
  if (!data) return;
  apply(data);
  if (!same) animateDetail("tag-detail");
}

async function selectAuthor(uid) {
  const same = state.activeKind === "author" && state.active === uid;
  state.active = uid;
  state.activeKind = "author";
  renderAuthorList();
  const data = await call("select_item", "author", uid);
  if (!data) return;
  apply(data);
  if (!same) animateDetail("author-detail");
}

function toggleSelection(md5) {
  if (state.selection.has(md5)) state.selection.delete(md5);
  else state.selection.add(md5);
  state.active = md5;
  state.anchor = md5;
  renderSongs();
}

function selectRange(md5) {
  const musics = visibleMusics();
  const from = musics.findIndex(function (item) {
    return item.md5 === state.anchor;
  });
  const to = musics.findIndex(function (item) {
    return item.md5 === md5;
  });
  if (from === -1 || to === -1) return toggleSelection(md5);
  const start = Math.min(from, to);
  const end = Math.max(from, to);
  for (let index = start; index <= end; index += 1) state.selection.add(musics[index].md5);
  state.active = md5;
  renderSongs();
}
