/* 标签与作者分区的事件绑定。 */
function bindLibraryEvents() {
  /* ---------- 标签页 ---------- */

  qs("#btn-new-tag-group").addEventListener("click", openCreateTagGroup);

  qs("#tag-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-tag-group]");
    if (row) selectTagGroup(row.dataset.tagGroup);
  });

  qs("#tag-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-tag-group]");
    if (!row) return;
    event.preventDefault();
    const group = tagGroupByUid(row.dataset.tagGroup);
    if (!group) return;
    if (state.active !== group.uid) selectTagGroup(group.uid);
    openMenu({ x: event.clientX, y: event.clientY }, [
      {
        label: T("tag.delete_group"),
        onClick: function () {
          confirmDeleteTagGroup(group);
        },
      },
    ]);
  });

  const tagSearch = qs("#tags-search");
  tagSearch.addEventListener("input", function () {
    state.tagQuery = tagSearch.value;
    qs("#tags-search-clear").hidden = !tagSearch.value;
    renderTagList();
  });
  qs("#tags-search-clear").addEventListener("click", function () {
    tagSearch.value = "";
    state.tagQuery = "";
    qs("#tags-search-clear").hidden = true;
    renderTagList();
    tagSearch.focus();
  });

  // 标签组列表拖拽排序：顺序写回 library.json 的 tag_groups 数组。
  bindDragSort(qs("#tag-list"), {
    row: "[data-tag-group]",
    allow: function () {
      return !state.tagQuery.trim();
    },
    key: function (node) {
      return node.dataset.tagGroup;
    },
    commit: async function (order) {
      const data = await call("reorder_tag_groups", order);
      if (data) apply(data);
    },
  });

  const tagDetail = qs("#tag-detail");

  // 组里的小标签：按住左边的把手拖，顺序写回这个标签组。
  bindDragSort(tagDetail, {
    row: "[data-tag-row]",
    handle: "[data-tag-grip]",
    key: function (node) {
      return node.dataset.tagRow;
    },
    commit: async function (order) {
      const group = tagGroupByUid(state.active);
      if (!group) return;
      const data = await call("reorder_tags", group.uid, order);
      if (data) apply(data);
    },
  });

  tagDetail.addEventListener("change", async function (event) {
    const group = tagGroupByUid(state.active);
    if (!group) return;
    if (event.target.id === "tag-group-name") {
      const value = event.target.value.trim();
      if (!value || value === group.name) {
        event.target.value = group.name;
        return;
      }
      const data = await call("update_tag_group", group.uid, { name: value });
      if (data) apply(data);
      return;
    }
    const tagInput = event.target.closest("[data-tag-name]");
    if (tagInput) {
      const value = tagInput.value.trim();
      if (!value || value === tagInput.dataset.tagOriginal) {
        tagInput.value = tagInput.dataset.tagOriginal;
        return;
      }
      const data = await call("rename_tag", group.uid, tagInput.dataset.tagName, value);
      if (data) apply(data);
    }
  });

  tagDetail.addEventListener("submit", async function (event) {
    if (event.target.id !== "tag-add-form") return;
    event.preventDefault();
    const group = tagGroupByUid(state.active);
    if (!group) return;
    const input = qs("#tag-new");
    const name = input.value.trim();
    if (!name) return;
    const data = await call("add_tag", group.uid, name);
    if (data) {
      apply(data);
      const again = qs("#tag-new");
      if (again) again.focus();
    }
  });

  tagDetail.addEventListener("click", async function (event) {
    const group = tagGroupByUid(state.active);
    if (!group) return;

    const toggle = event.target.closest("[data-switch]");
    if (toggle) {
      const next = toggle.getAttribute("aria-checked") !== "true";
      toggle.setAttribute("aria-checked", next ? "true" : "false");
      const patch = {};
      patch[toggle.dataset.switch] = next;
      const data = await call("update_tag_group", group.uid, patch);
      if (!data) return;
      await delay(170);
      apply(data);
      return;
    }

    const remove = event.target.closest("[data-tag-remove]");
    if (remove) {
      // 小标签也会从歌上摘掉，必须先确认并说明影响范围。
      const tag = (group.tags || []).find(function (item) {
        return item.uid === remove.dataset.tagRemove;
      });
      if (tag) confirmDeleteTag(group, tag);
      return;
    }

    const menu = event.target.closest("[data-menu='tag']");
    if (menu) {
      openMenu(menu, [
        {
          label: T("tag.delete_group"),
          onClick: function () {
            confirmDeleteTagGroup(group);
          },
        },
      ]);
    }
  });

  /* ---------- 作者页 ---------- */

  qs("#btn-new-author").addEventListener("click", openCreateAuthor);

  qs("#author-list").addEventListener("click", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (row) selectAuthor(row.dataset.authorUid);
  });

  qs("#author-list").addEventListener("contextmenu", function (event) {
    const row = event.target.closest("[data-author-uid]");
    if (!row) return;
    event.preventDefault();
    const author = authorByUid(row.dataset.authorUid);
    if (!author) return;
    if (state.active !== author.uid) selectAuthor(author.uid);
    openMenu({ x: event.clientX, y: event.clientY }, [
      {
        label: T("author.delete"),
        onClick: function () {
          confirmDeleteAuthor(author);
        },
      },
    ]);
  });

  const authorSearch = qs("#authors-search");
  authorSearch.addEventListener("input", function () {
    state.authorQuery = authorSearch.value;
    qs("#authors-search-clear").hidden = !authorSearch.value;
    renderAuthorList();
  });
  qs("#authors-search-clear").addEventListener("click", function () {
    authorSearch.value = "";
    state.authorQuery = "";
    qs("#authors-search-clear").hidden = true;
    renderAuthorList();
    authorSearch.focus();
  });

  const authorDetail = qs("#author-detail");

  authorDetail.addEventListener("change", async function (event) {
    const author = authorByUid(state.active);
    if (!author) return;
    if (event.target.id === "author-name") {
      const value = event.target.value.trim();
      if (!value || value === author.name) {
        event.target.value = author.name;
        return;
      }
      const data = await call("update_author", author.uid, { name: value });
      if (data) apply(data);
      return;
    }
    if (event.target.id === "author-description") {
      const value = event.target.value.trim();
      if (value === (author.description || "")) return;
      const data = await call("update_author", author.uid, { description: value });
      if (data) apply(data);
    }
  });

  authorDetail.addEventListener("click", function (event) {
    const author = authorByUid(state.active);
    if (!author) return;

    const song = event.target.closest("[data-author-song]");
    if (song) {
      selectMusic(song.dataset.authorSong);
      return;
    }

    const menu = event.target.closest("[data-menu='author']");
    if (menu) {
      openMenu(menu, [
        {
          label: T("author.delete"),
          onClick: function () {
            confirmDeleteAuthor(author);
          },
        },
      ]);
    }
  });
}
