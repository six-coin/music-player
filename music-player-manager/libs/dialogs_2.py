from libs import config
from libs import dialogs
from libs import parser
from libs import standard_ui
from libs import utils


class ItemSwapDialog(standard_ui.Dialog):
    def __init__(self, parent, title, available_items, selected_uids, get_display, get_search_keys, search_placeholder):
        # 窗口 accept 后，调用 get_result 的来到包含所有项目 uid 的列表
        super().__init__(parent, title)

        self.available_items = available_items  # 所有可选对象列表（必须有 .uid 属性）
        self.selected_uids = selected_uids  # 当前已经选择的项目的 uid 组成的列表
        self.get_display = get_display  # 获取项目的显示名称的函数
        self.get_search_keys = get_search_keys  # 获取项目的搜索关键字的函数

        left_label = standard_ui.Label(self, "备选项")
        left_search = standard_ui.LineEdit(self)
        left_search.setPlaceholderText(search_placeholder)
        left_search.textChanged.connect(self.on_search)
        left_list = standard_ui.ListWidget(self)
        left_list.setSelectionMode(standard_ui.ListWidget.SelectionMode.SingleSelection)
        left_layout = standard_ui.VerticalLayout([left_label, left_search, left_list])

        right_label = standard_ui.Label(self, "已选项（可拖拽排序）")
        right_list = standard_ui.ListWidget(self, allow_drop=True)
        right_layout = standard_ui.VerticalLayout([right_label, right_list])

        btn_add = standard_ui.Button(self, "添加 >", function=self.add)
        btn_remove = standard_ui.Button(self, "< 移除", function=self.remove)
        mid_layout = standard_ui.VerticalLayout([None, btn_add, btn_remove, None])

        body_layout = standard_ui.HorizontalLayout([left_layout, mid_layout, right_layout], spacing=10)

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.finish, level="primary")
        bottom_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        main_layout = standard_ui.VerticalLayout([body_layout, bottom_layout], margin=15)
        self.setLayout(main_layout)

        self.left_search = left_search
        self.left_list = left_list
        self.right_list = right_list

        self.setMinimumWidth(900)
        self.setMinimumHeight(550)

        self.refresh_left_list()
        self.refresh_right_list()

    def refresh_left_list(self, filter_text=""):
        self.left_list.blockSignals(True)
        self.left_list.clear()
        right_set = set(self.selected_uids)
        filter_lower = filter_text.strip().lower()
        for obj in self.available_items:
            if obj.uid in right_set:
                continue
            if filter_text:
                keys = self.get_search_keys(obj)
                if not any(filter_lower in key.lower() for key in keys):
                    continue
            display = self.get_display(obj)
            item = standard_ui.ListWidgetItem(display, [(32, obj.uid)])
            self.left_list.addItem(item)
        self.left_list.blockSignals(False)

    def refresh_right_list(self):
        self.right_list.blockSignals(True)
        self.right_list.clear()
        for uid in self.selected_uids:
            obj = next((obj for obj in self.available_items if obj.uid == uid), None)
            if obj is None:
                continue
            display = self.get_display(obj)
            item = standard_ui.ListWidgetItem(display, [(32, obj.uid)])
            self.right_list.addItem(item)
        self.right_list.blockSignals(False)

    def on_search(self, text):
        self.refresh_left_list(text)

    def add(self):
        item = self.left_list.currentItem()
        if item is None:
            standard_ui.show_alert_dialog(self, "请现在左侧列表中选择一个项目。")
            return
        uid = item.data(32)
        self.selected_uids.append(uid)
        self.refresh_left_list(self.left_search.text())
        self.refresh_right_list()
        self.right_list.setCurrentRow(self.right_list.count() - 1)

    def remove(self):
        item = self.right_list.currentItem()
        if item is None:
            standard_ui.show_alert_dialog(self, "请现在右侧列表中选择一个项目。")
            return
        uid = item.data(32)
        self.selected_uids.remove(uid)
        self.refresh_left_list(self.left_search.text())
        self.refresh_right_list()

    def finish(self):
        final_order = []
        for i in range(self.right_list.count()):
            final_order.append(self.right_list.item(i).data(32))
        self.selected_uids = final_order
        self.accept()


class MusicEditDialog(standard_ui.Dialog):
    def __init__(self, parent, music_obj=None, default_file=None):
        super().__init__(parent, "编辑歌曲信息" if music_obj else "新建歌曲")

        self.music_obj = music_obj
        self.default_file = default_file

        left_name_label = standard_ui.Label(self, "歌曲名称")
        left_name_edit = standard_ui.LineEdit(self)
        if music_obj:
            escaped_names = [name.replace("/", "//") for name in music_obj.names]
            left_name_edit.setText(" / ".join(escaped_names))
        left_author_label = standard_ui.Label(self, "作者（可拖拽排序）")
        left_author_list = standard_ui.ListWidget(self, allow_drop=True)
        uids = self.music_obj.authors if self.music_obj else []
        for uid in uids:
            author = parser.authors.get(uid)
            if author:
                item = standard_ui.ListWidgetItem(author.name, [(32, uid)])
                left_author_list.addItem(item)
        left_btn_edit = standard_ui.Button(self, "编辑作者", function=self.edit_authors)
        left_btn_new = standard_ui.Button(self, "新建作者", function=self.new_author)
        left_btn_layout = standard_ui.VerticalLayout([left_btn_edit, left_btn_new])
        left_layout = standard_ui.VerticalLayout(
            [left_name_label, left_name_edit, left_author_label, left_author_list, left_btn_layout]
        )

        mid_music_label = standard_ui.Label(self, "音乐文件（可拖拽排序，双击查看详情）")
        mid_file_list = standard_ui.ListWidget(self, allow_drop=True)
        mid_file_list.itemDoubleClicked.connect(self.show_file_info)
        uids = self.music_obj.files if self.music_obj else [self.default_file.uid] if self.default_file else []
        for uid in uids:
            music_file = parser.music_files.get(uid)
            if music_file:
                display = utils.get_music_file_display_name_simple(music_file)
                item = standard_ui.ListWidgetItem(display, [(32, uid)])
                mid_file_list.addItem(item)
        mid_btn_edit = standard_ui.Button(self, "编辑文件", function=self.edit_files)
        mid_btn_import = standard_ui.Button(self, "导入文件", function=self.import_file)
        mid_btn_layout = standard_ui.VerticalLayout([mid_btn_edit, mid_btn_import])
        mid_layout = standard_ui.VerticalLayout([mid_music_label, mid_file_list, mid_btn_layout])

        right_label = standard_ui.Label(self, "标签")
        tag_widgets = {}  # 字典，从标签组 uid 映射至检查框列表
        right_group_boxes = []
        for tag_group in parser.tag_groups.values():
            checkboxes = []
            for tag in tag_group.tags:
                checkbox = standard_ui.CheckBox(self, tag.name)
                checkbox.setProperty("tag_uid", tag.uid)
                if music_obj and tag.uid in music_obj.tags:
                    checkbox.setChecked(True)
                checkboxes.append(checkbox)
            group_layout = standard_ui.VerticalLayout(checkboxes)
            compulsory = "必选" if tag_group.compulsory else "不必选"
            unique = "唯一" if tag_group.unique else "不唯一"
            group_box = standard_ui.GroupBox(self, f"标签组：{tag_group.name}（{compulsory}，{unique}）")
            group_box.setLayout(group_layout)
            right_group_boxes.append(group_box)
            tag_widgets[tag_group.uid] = checkboxes
        right_group_boxes.append(None)
        right_scroll_area = standard_ui.ScrollArea(self, right_group_boxes)
        right_layout = standard_ui.VerticalLayout([right_label, right_scroll_area])

        body_layout = standard_ui.HorizontalLayout([left_layout, mid_layout, right_layout], spacing=10)

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.on_accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        main_layout = standard_ui.VerticalLayout([body_layout, btn_layout], margin=15)
        self.setLayout(main_layout)

        self.left_name_edit = left_name_edit
        self.left_author_list = left_author_list
        self.mid_file_list = mid_file_list
        self.tag_widgets = tag_widgets

        self.setMinimumWidth(1200)
        self.setMinimumHeight(600)

    def get_author_uids_from_list(self):
        """从 author_list 读取 uid 列表"""
        return [self.left_author_list.item(i).data(32) for i in range(self.left_author_list.count())]

    def edit_authors(self):
        dialog = ItemSwapDialog(
            self, "编辑作者",
            available_items=list(parser.authors.values()),
            selected_uids=self.get_author_uids_from_list(),
            get_display=lambda obj: obj.name,
            get_search_keys=lambda obj: [obj.name],
            search_placeholder="搜索作者名称…"
        )
        dialog.left_search.setPlaceholderText("搜索作者名称…")
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            new_order = dialog.selected_uids
            self.left_author_list.blockSignals(True)
            self.left_author_list.clear()
            for uid in new_order:
                author = parser.authors.get(uid)
                if author:
                    item = standard_ui.ListWidgetItem(author.name, [(32, uid)])
                    self.left_author_list.addItem(item)
            self.left_author_list.blockSignals(False)

    def new_author(self):
        dialog = dialogs.AuthorEditDialog(self)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            # 刷新作者列表（新建的作者会自动加入列表）
            item = standard_ui.ListWidgetItem(dialog.obj.name, [(32, dialog.obj.uid)])
            self.left_author_list.addItem(item)

    def get_file_uids_from_list(self):
        """从 file_list 读取 uid 列表"""
        return [self.mid_file_list.item(i).data(32) for i in range(self.mid_file_list.count())]

    def edit_files(self):
        dialog = ItemSwapDialog(
            self, "编辑音乐文件",
            available_items=list(parser.music_files.values()),
            selected_uids=self.get_file_uids_from_list(),
            get_display=utils.get_music_file_display_name_simple,
            get_search_keys=utils.get_music_file_search_keys,
            search_placeholder="搜索音乐文件 MD5…"
        )
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            new_order = dialog.selected_uids
            self.mid_file_list.blockSignals(True)
            self.mid_file_list.clear()
            for uid in new_order:
                music_file = parser.music_files.get(uid)
                if music_file:
                    display = utils.get_music_file_display_name_simple(music_file)
                    item = standard_ui.ListWidgetItem(display, [(32, uid)])
                    self.mid_file_list.addItem(item)
            self.mid_file_list.blockSignals(False)

    def import_file(self):
        file_path = standard_ui.show_file_dialog(
            self, False,
            "选择音乐文件", config.configs["manager"]["import_dir"], "音频文件 (*.mp3 *.m4a)"
        )
        if not file_path:
            return

        try:
            music_file = parser.import_music_file(file_path)
        except Exception as e:
            standard_ui.show_alert_dialog(self, str(e))
            return

        display = utils.get_music_file_display_name_simple(music_file)
        item = standard_ui.ListWidgetItem(display, [(32, music_file.uid)])
        self.mid_file_list.addItem(item)

    def show_file_info(self, item):
        dialogs.MusicFileInfoDialog(self, parser.music_files.get(item.data(32))).exec()

    def on_accept(self):
        # 名称
        names_text = self.left_name_edit.text().strip()
        if not names_text:
            standard_ui.show_alert_dialog(self, "歌曲名称不能为空。")
            return
        names = utils.parse_comma_separated(names_text)

        # 作者（按列表顺序）
        authors = self.get_author_uids_from_list()
        if not authors:
            standard_ui.show_alert_dialog(self, "须至少选择一个作者。")
            return

        # 标签
        selected_tags = []
        for checkboxes in self.tag_widgets.values():
            for checkbox in checkboxes:
                if checkbox.isChecked():
                    selected_tags.append(checkbox.property("tag_uid"))

        for tag_group in parser.tag_groups.values():
            tags = {tag.uid for tag in tag_group.tags}
            selected_in_group = [uid for uid in selected_tags if uid in tags]
            count = len(selected_in_group)
            if tag_group.compulsory and tag_group.unique and count != 1:
                standard_ui.show_alert_dialog(self, f"标签组“{tag_group.name}”要求恰好选择一个标签。")
                return
            if tag_group.compulsory and not tag_group.unique and count < 1:
                standard_ui.show_alert_dialog(self, f"标签组“{tag_group.name}”要求至少选择一个标签。")
                return
            if not tag_group.compulsory and tag_group.unique and count > 1:
                standard_ui.show_alert_dialog(self, f"标签组“{tag_group.name}”要求最多选择一个标签。")
                return

        # 文件（按列表顺序）
        files = self.get_file_uids_from_list()
        if not files:
            standard_ui.show_alert_dialog(self, "须至少关联一个音乐文件。")
            return

        for uid in files:
            for existing_music in parser.musics.values():
                if self.music_obj and existing_music.uid == self.music_obj.uid:
                    continue
                if uid in existing_music.files:
                    display = f"文件 {uid} 已被歌曲“{utils.get_music_display_name(existing_music)}”关联，是否继续？"
                    if standard_ui.show_confirm_dialog(self, display) != 1:
                        return

        # 保存
        if self.music_obj is not None:
            self.music_obj.names = names
            self.music_obj.authors = authors
            self.music_obj.files = files
            self.music_obj.tags = selected_tags
        else:
            mid = parser.uid_generate()
            parser.musics[mid] = parser.Music(mid, names, authors, files, selected_tags)

        self.accept()


class ConditionsPlaylistEditDialog(standard_ui.Dialog):
    def __init__(self, parent, conditions=None):
        super().__init__(parent, "编辑条件")

        if conditions is None:
            conditions = [{"mode": "exclude", "filter": "all"}]
        self.conditions = conditions

        # 左侧：重置条件，预览
        reset_label = standard_ui.Label(self, "重置条件")
        reset_btn = standard_ui.Button(self, "重置所有条件", function=self.reset_conditions, level="danger")
        preview_label = standard_ui.Label(self, "歌单预览")
        preview_list = standard_ui.ListWidget(self, selection_mode=-1, allow_drop=False)
        left_layout = standard_ui.VerticalLayout([reset_label, reset_btn, preview_label, preview_list])

        # 右侧：条件编辑区，添加条件按钮
        conditions_label = standard_ui.Label(self, "条件编辑")
        cond_layout = standard_ui.VerticalLayout([], spacing=8)
        cond_widget = standard_ui.Widget(self)
        cond_widget.setLayout(cond_layout)
        cond_scroll = standard_ui.ScrollArea(self, [], is_vertical=True, margin=0, no_widgets=True)
        cond_scroll.setWidget(cond_widget)
        add_btn = standard_ui.Button(self, "添加新条件", function=self.add_condition, level="primary")
        right_layout = standard_ui.VerticalLayout([conditions_label, cond_scroll, add_btn])

        body_layout = standard_ui.HorizontalLayout([(left_layout, 1), (right_layout, 2)], spacing=10)

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        main_layout = standard_ui.VerticalLayout([body_layout, btn_layout], margin=15)
        self.setLayout(main_layout)

        self.preview_list = preview_list
        self.cond_layout = cond_layout
        self.condition_widgets = []  # 包含每个 condition 对应的 cond_info，格式见下
        # cond_info = {
        #     "group": group_box,
        #     "mode_combo": mode_combo,
        #     "filter_combo": filter_combo,
        #     "list_widget": list_widget,
        #     "selected_uids": condition.get("list", [])
        # }

        for condition in self.conditions:
            self.create_condition_editor(condition)

        self.update_preview()

        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

    def create_condition_editor(self, condition):
        group_box = standard_ui.GroupBox(self, "条件")

        mode_label = standard_ui.Label(self, "方式：")
        mode_combo = standard_ui.ComboBox(self, [], allow_scroll=False)
        mode_combo.addItem("包含（所有符合条件的歌曲都将被添加）", "include")
        mode_combo.addItem("排除（所有符合条件的歌曲都将被排除）", "exclude")
        mode_combo.currentIndexChanged.connect(self.update_preview)
        mode_row = standard_ui.HorizontalLayout([(mode_label, 1), (mode_combo, 3)])

        filter_label = standard_ui.Label(self, "依据：")
        filter_combo = standard_ui.ComboBox(self, [], allow_scroll=False)
        filter_combo.addItem("全部歌曲", "all")
        filter_combo.addItem("筛选歌曲", "music")
        filter_combo.addItem("筛选歌单（歌单中全部歌曲符合，禁止循环引用）", "playlist")
        filter_combo.addItem("筛选标签（歌曲标签列表中存在即符合）", "tag")
        filter_combo.addItem("筛选作者（歌曲作者列表中存在即符合）", "author")
        filter_combo.currentIndexChanged.connect(lambda: [
            self.populate_list_widget(cond_info),
            self.update_preview()
        ])
        filter_row = standard_ui.HorizontalLayout([(filter_label, 1), (filter_combo, 3)])

        list_widget = standard_ui.ListWidget(self, allow_drop=False, selection_mode=-1)
        list_widget.setMinimumHeight(200)
        list_widget.setVisible(False)

        btn_edit = standard_ui.Button(self, "编辑此条件", function=lambda: self.edit_condition(cond_info))
        btn_del = standard_ui.Button(
            self, "删除此条件",
            function=lambda: self.remove_condition(group_box), level="danger"
        )
        btn_row = standard_ui.HorizontalLayout([btn_edit, btn_del])

        group_box_layout = standard_ui.VerticalLayout([mode_row, filter_row, list_widget, btn_row], spacing=5)
        group_box.setLayout(group_box_layout)

        cond_info = {
            "group": group_box,
            "mode_combo": mode_combo,
            "filter_combo": filter_combo,
            "list_widget": list_widget,
            "selected_uids": condition.get("list", [])
        }

        # 设置初始值
        mode_value = condition["mode"]
        filter_value = condition["filter"]
        mode_combo.setCurrentIndex(mode_combo.findData(mode_value))
        filter_combo.setCurrentIndex(filter_combo.findData(filter_value))

        self.populate_list_widget(cond_info)
        self.condition_widgets.append(cond_info)

        # 将编辑器插入到布局末尾
        if self.cond_layout.count() > 0:
            last_item = self.cond_layout.itemAt(self.cond_layout.count() - 1)
            self.cond_layout.removeItem(last_item)
            self.cond_layout.addWidget(group_box)
            self.cond_layout.addStretch()
        else:
            self.cond_layout.addWidget(group_box)
            self.cond_layout.addStretch()

    @staticmethod
    def populate_list_widget(cond_info):
        list_widget = cond_info["list_widget"]
        filter_type = cond_info["filter_combo"].currentData()
        selected = cond_info["selected_uids"]

        list_widget.clear()
        if filter_type == "all":
            list_widget.setVisible(False)
            return
        list_widget.setVisible(True)

        if not selected:
            return

        if filter_type == "music":
            for uid in selected:
                music = parser.musics.get(uid)
                if music:
                    list_widget.addItem(utils.get_music_display_name(music))
        elif filter_type == "playlist":
            for uid in selected:
                playlist = parser.playlists.get(uid)
                if playlist:
                    list_widget.addItem(playlist.name)
        elif filter_type == "tag":
            for uid in selected:
                tag = parser.tags.get(uid)
                if tag:
                    list_widget.addItem(utils.get_tag_full_display(tag))
        elif filter_type == "author":
            for uid in selected:
                author = parser.authors.get(uid)
                if author:
                    list_widget.addItem(author.name)

    def edit_condition(self, cond_info):
        filter_type = cond_info["filter_combo"].currentData()

        if filter_type == "all":
            standard_ui.show_alert_dialog(self, "“全部”类型无需编辑对象列表。")
            return

        if filter_type == "music":
            available = list(parser.musics.values())
            get_display = utils.get_music_display_name
            get_search_keys = utils.get_music_search_keys
        elif filter_type == "playlist":
            available = list(parser.playlists.values())
            get_display = lambda playlist: playlist.name
            get_search_keys = lambda playlist: [playlist.name]
        elif filter_type == "tag":
            available = list(parser.tags.values())
            get_display = utils.get_tag_full_display
            get_search_keys = lambda tag: [utils.get_tag_full_display(tag)]
        else:  # filter_type == "author"
            available = list(parser.authors.values())
            get_display = lambda author: author.name
            get_search_keys = lambda author: [author.name]

        selected_uids = cond_info["selected_uids"]
        dialog = ItemSwapDialog(
            self,
            f"编辑单个条件",
            available_items=available,
            selected_uids=selected_uids,
            get_display=get_display,
            get_search_keys=get_search_keys,
            search_placeholder="搜索…"
        )
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            cond_info["selected_uids"] = dialog.selected_uids
            self.populate_list_widget(cond_info)
            self.update_preview()

    def remove_condition(self, group_box):
        for condition_widget in self.condition_widgets:
            if condition_widget["group"] == group_box:
                self.cond_layout.removeWidget(group_box)
                group_box.deleteLater()
                self.condition_widgets.remove(condition_widget)
                break
        self.update_preview()

    def add_condition(self, _, condition=None):
        if condition is None:
            condition = {"mode": "include", "filter": "music", "list": []}
        self.create_condition_editor(condition)

    def reset_conditions(self, _):
        for condition_widget in self.condition_widgets[:]:
            self.remove_condition(condition_widget["group"])
        self.add_condition(None, {"mode": "exclude", "filter": "all"})

    def get_conditions(self):
        conditions = []
        for condition_widget in self.condition_widgets:
            mode = condition_widget["mode_combo"].currentData()
            filter_type = condition_widget["filter_combo"].currentData()
            condition = {"mode": mode, "filter": filter_type}
            if filter_type != "all":
                condition["list"] = condition_widget["selected_uids"]
            conditions.append(condition)
        return conditions

    def update_preview(self):
        self.preview_list.clear()
        try:
            temp_uid = "__temp_playlist__"
            temp_playlist = parser.Playlist(temp_uid, "临时歌单", "conditions", self.get_conditions())
            parser.playlists[temp_uid] = temp_playlist
            try:
                resolved = parser.resolve_playlist(temp_uid)
            finally:
                del parser.playlists[temp_uid]
            for uid in resolved:
                music = parser.musics.get(uid)
                if music:
                    self.preview_list.addItem(utils.get_music_display_name(music))
        except Exception as e:
            self.preview_list.addItem(f"解析失败：{e}")


class PlaylistEditDialog(standard_ui.Dialog):
    def __init__(self, parent, playlist_obj=None):
        super().__init__(parent, "编辑歌单" if playlist_obj else "新建歌单")

        if playlist_obj:
            self.name = playlist_obj.name
            self.mode = playlist_obj.mode
            self.data = playlist_obj.data if self.mode == "simple" else [dict(cond) for cond in playlist_obj.data]
        else:
            self.name = ""
            self.mode = "simple"
            self.data = []
        self.playlist_obj = playlist_obj

        name_label = standard_ui.Label(self, "歌单名称")
        name_edit = standard_ui.LineEdit(self)
        name_edit.setText(self.name)

        mode_label = standard_ui.Label(self, "歌单模式")
        mode_group = standard_ui.ButtonGroup(self, True, ["简单模式", "条件模式"])
        radio_simple, radio_cond = mode_group.get_buttons()
        radio_simple.toggled.connect(self.on_simple_toggled)
        radio_cond.toggled.connect(self.on_cond_toggled)
        if self.mode == "conditions":
            radio_cond.setChecked(True)
        else:
            radio_simple.setChecked(True)

        preview_label = standard_ui.Label(self, "歌单预览")
        preview_list = standard_ui.ListWidget(self, selection_mode=-1, allow_drop=False)

        edit_btn = standard_ui.Button(self, "编辑歌单", function=self.edit_playlist)

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.on_accept, level="primary")
        bottom_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        main_layout = standard_ui.VerticalLayout(
            [name_label, name_edit, mode_label, radio_simple, radio_cond, preview_label, preview_list, edit_btn,
             bottom_layout], margin=15
        )
        self.setLayout(main_layout)

        self.name_edit = name_edit
        self.radio_simple = radio_simple
        self.radio_cond = radio_cond
        self.preview_list = preview_list
        self.edit_btn = edit_btn

        self.update_preview()

        self.setMinimumWidth(600)
        self.setMinimumHeight(650)

    def on_simple_toggled(self, checked):
        if checked and self.mode != "simple":
            self.data = []
            self.mode = "simple"
            self.update_preview()

    def on_cond_toggled(self, checked):
        if checked and self.mode != "conditions":
            self.data = [{"mode": "exclude", "filter": "all"}]
            self.mode = "conditions"
            self.update_preview()

    def edit_playlist(self):
        if self.radio_simple.isChecked():
            dialog = ItemSwapDialog(
                self, "编辑歌单歌曲",
                available_items=list(parser.musics.values()),
                selected_uids=list(self.data),
                get_display=utils.get_music_display_name,
                get_search_keys=utils.get_music_search_keys,
                search_placeholder="搜索歌曲名称…",
            )
            if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
                self.data = dialog.selected_uids
                self.update_preview()
        else:
            conditions = self.data
            dialog = ConditionsPlaylistEditDialog(self, conditions)
            if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
                self.data = dialog.get_conditions()
                self.update_preview()

    def update_preview(self):
        self.preview_list.clear()
        try:
            if self.radio_simple.isChecked():
                for uid in self.data:
                    music = parser.musics.get(uid)
                    if music:
                        self.preview_list.addItem(utils.get_music_display_name(music))
            else:
                temp_uid = "__temp_playlist__"
                temp_playlist = parser.Playlist(temp_uid, "临时歌单", "conditions", self.data)
                parser.playlists[temp_uid] = temp_playlist
                try:
                    resolved = parser.resolve_playlist(temp_uid)
                finally:
                    del parser.playlists[temp_uid]
                for uid in resolved:
                    music = parser.musics.get(uid)
                    if music:
                        self.preview_list.addItem(utils.get_music_display_name(music))
        except Exception as e:
            self.preview_list.addItem(f"解析失败：{e}")

    def on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            standard_ui.show_alert_dialog(self, "歌单名称不能为空。")
            return

        is_simple = self.radio_simple.isChecked()
        if not self.data:
            standard_ui.show_alert_dialog(self, "须至少选择一首歌曲。" if is_simple else "须至少添加一个条件。")
            return

        if self.playlist_obj is not None:
            self.playlist_obj.name = name
            self.playlist_obj.mode = self.mode
            self.playlist_obj.data = self.data
        else:
            uid = parser.uid_generate()
            parser.playlists[uid] = parser.Playlist(uid, name, self.mode, self.data)

        self.accept()
