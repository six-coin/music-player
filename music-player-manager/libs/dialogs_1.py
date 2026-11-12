import vlc

from libs import config
from libs import parser
from libs import standard_ui
from libs import utils


class PreferenceDialog(standard_ui.Dialog):
    def __init__(self, parent):
        super().__init__(parent, "编辑首选项")

        import_dir_label = standard_ui.Label(self, "默认文件导入路径")
        import_dir_edit = standard_ui.LineEdit(self)
        import_dir_edit.setText(config.configs["managers"]["import_dir"])

        save_dialog_label = standard_ui.Label(self, "保存成功时显示对话框")
        save_dialog_combo = standard_ui.ComboBox(self, ["是", "否"])
        save_dialog_combo.setCurrentIndex(0 if config.configs["managers"]["save_dialog"] else 1)

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "确定", function=self.on_accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        layout = standard_ui.VerticalLayout(
            [import_dir_label, import_dir_edit, save_dialog_label, save_dialog_combo, btn_layout], margin=15
        )
        self.setLayout(layout)

        self.import_dir_edit = import_dir_edit
        self.save_dialog_combo = save_dialog_combo

        suggested_size = self.sizeHint()
        suggested_size.setWidth(400)
        self.setFixedSize(suggested_size)

    def on_accept(self):
        config.configs["manager"]["import_dir"] = self.import_dir_edit.text().strip()
        config.configs["manager"]["save_dialog"] = self.save_dialog_combo.currentIndex() == 0
        try:
            config.save("manager")
        except Exception as e:
            message = f"首选项保存失败：{e}\n\n程序重新启动后首选项配置可能丢失，但当前程序会应用配置的首选项。"
            standard_ui.show_alert_dialog(self, message)
        self.accept()


class QuickImportTagDialog(standard_ui.Dialog):
    def __init__(self, parent):
        super().__init__(parent, "批量导入标签选择")

        group_label = standard_ui.Label(self, "标签组")
        group_search = standard_ui.LineEdit(self)
        group_search.setPlaceholderText("搜索标签组…")
        group_search.textChanged.connect(self.on_group_search)
        group_list = standard_ui.ListWidget(self)
        group_list.currentItemChanged.connect(self.on_group_selected)
        group_layout = standard_ui.VerticalLayout([group_label, group_search, group_list])

        tag_label = standard_ui.Label(self, "标签")
        tag_list = standard_ui.ListWidget(self)
        tag_layout = standard_ui.VerticalLayout([tag_label, tag_list])

        selected_label = standard_ui.Label(self, "已选标签")
        selected_list = standard_ui.ListWidget(self)
        btn_add = standard_ui.Button(self, "添加选中的标签", function=self.add_to_selected)
        btn_remove = standard_ui.Button(self, "删除选中的标签", function=self.remove_from_selected)
        selected_layout = standard_ui.VerticalLayout([selected_label, selected_list, btn_add, btn_remove])

        body_layout = standard_ui.HorizontalLayout([group_layout, tag_layout, selected_layout], spacing=10)

        btn_cancel_import = standard_ui.Button(self, "取消导入", function=self.reject)
        btn_no_tag = standard_ui.Button(self, "不添加标签", function=self.no_tag)
        btn_accept = standard_ui.Button(self, "完成", function=self.finish, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, btn_cancel_import, btn_no_tag, btn_accept])

        main_layout = standard_ui.VerticalLayout([body_layout, btn_layout], margin=15)
        self.setLayout(main_layout)

        self.group_search = group_search
        self.group_list = group_list
        self.tag_list = tag_list
        self.selected_list = selected_list
        self.populate_group_list()

        self.setMinimumWidth(900)
        self.setMinimumHeight(500)

    def populate_group_list(self, filter_text=""):
        self.group_list.blockSignals(True)
        self.group_list.clear()
        filter_text = filter_text.strip().lower()
        for tag_group in parser.tag_groups.values():
            if filter_text and filter_text not in tag_group.name.lower():
                continue
            item = standard_ui.ListWidgetItem(tag_group.name, [(32, tag_group.uid)])
            self.group_list.addItem(item)
        self.group_list.blockSignals(False)

        self.tag_list.clear()

    def on_group_search(self, text):
        self.populate_group_list(text)

    def on_group_selected(self, current, _):
        self.tag_list.clear()
        if current is None:
            return
        for tag in parser.tag_groups[current.data(32)].tags:
            item = standard_ui.ListWidgetItem(tag.name, [(32, tag.uid)])
            self.tag_list.addItem(item)

    def add_to_selected(self):
        current = self.tag_list.currentItem()
        if current is None:
            standard_ui.show_alert_dialog(self, "请先在标签列表中选择一个标签。")
            return
        uid = current.data(32)
        if uid in self.get_selected_tags():
            standard_ui.show_alert_dialog(self, "该标签已在已选列表中。")
            return
        item = standard_ui.ListWidgetItem(utils.get_tag_full_display(parser.tags[current.data(32)]), [(32, uid)])
        self.selected_list.addItem(item)

    def remove_from_selected(self):
        current = self.selected_list.currentItem()
        if current is None:
            standard_ui.show_alert_dialog(self, "请先在已选列表中选择一个标签。")
            return
        self.selected_list.takeItem(self.selected_list.row(current))

    def no_tag(self):
        self.selected_list.clear()
        self.accept()

    def finish(self):
        self.accept()

    def get_selected_tags(self):
        return [self.selected_list.item(i).data(32) for i in range(self.selected_list.count())]


class QuickImportConfirmDialog(standard_ui.Dialog):
    def __init__(self, parent, parsed):
        super().__init__(parent, "批量导入信息确认")

        file_label = standard_ui.Label(self, "文件名")
        file_edit = standard_ui.LineEdit(self, read_only=True)
        title_label = standard_ui.Label(self, "歌曲名称")
        title_edit = standard_ui.LineEdit(self)
        author_label = standard_ui.Label(self, "作者匹配情况")
        author_edit = standard_ui.PlainTextEdit(self, read_only=True)
        review_checkbox = standard_ui.ButtonGroup(self, False, ["标记为“待修改”"]).get_buttons()[0]

        btn_previous = standard_ui.Button(self, "上一首", function=self.go_previous)
        btn_next = standard_ui.Button(self, "下一首", function=self.go_next)
        btn_finish = standard_ui.Button(self, "完成", function=self.finish)
        btn_layout = standard_ui.HorizontalLayout([None, btn_previous, btn_next, btn_finish], spacing=5)

        layout = standard_ui.VerticalLayout(
            [file_label, file_edit, title_label, title_edit, author_label, author_edit, review_checkbox, btn_layout],
            margin=15
        )
        self.setLayout(layout)

        self.file_edit = file_edit
        self.title_edit = title_edit
        self.author_edit = author_edit
        self.review_checkbox = review_checkbox
        self.btn_previous = btn_previous
        self.btn_next = btn_next
        self.btn_finish = btn_finish

        self.parsed = parsed
        self.total = len(parsed)
        self.current_item = 0
        self.load_item(0)
        self.finish_flag = False

        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

    def save_current(self):
        item = self.parsed[self.current_item]
        item["title"] = self.title_edit.text().strip()
        item["marked_for_review"] = self.review_checkbox.isChecked()

    def load_item(self, index):
        item = self.parsed[index]
        self.file_edit.setText(item["path"].name)
        self.title_edit.setText(item["title"])
        lines = []
        for author in item["authors"]:
            author_id = next((author.uid for author in parser.authors.values() if author.name == author), None)
            lines.append(f"{author} - 已存在（{author_id}）" if author_id else f"{author} - 不存在，将新建")
        self.author_edit.setPlainText("\n".join(lines) if lines else "未检测到默认作者")
        self.review_checkbox.setChecked(item["marked_for_review"])

        if index == self.total - 1:
            self.finish_flag = True
            self.btn_finish.set_level("primary")
        self.btn_previous.setEnabled(index != 0)
        self.btn_next.setEnabled(index != self.total - 1)

    def go_previous(self):
        if self.current_item > 0:
            self.save_current()
            self.current_item -= 1
            self.load_item(self.current_item)

    def go_next(self):
        if self.current_item < self.total - 1:
            self.save_current()
            self.current_item += 1
            self.load_item(self.current_item)

    def finish(self):
        if not self.finish_flag:
            choice = standard_ui.show_confirm_dialog(self, "还未确认所有歌曲，是否跳过剩余歌曲信息确认？")
            if not choice == 1:
                return
        self.save_current()
        self.accept()


class AuthorEditDialog(standard_ui.Dialog):
    def __init__(self, parent, obj=None):
        # author_obj 为 None 时，本窗口 accept 后会自动在 parser.authors 中添加作者
        super().__init__(parent, "编辑作者" if obj else "新建作者")

        name_label = standard_ui.Label(self, "作者名称")
        name_edit = standard_ui.LineEdit(self)
        if obj:
            name_edit.setText(obj.name)

        description_label = standard_ui.Label(self, "作者简介（可选）")
        description_edit = standard_ui.TextEdit(self)
        if obj:
            description_edit.setPlainText(obj.description)

        btn_cancel = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.on_accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, btn_cancel, btn_accept])

        layout = standard_ui.VerticalLayout(
            [name_label, name_edit, description_label, description_edit, btn_layout],
            margin=15
        )
        self.setLayout(layout)

        self.obj = obj
        self.name_edit = name_edit
        self.description_edit = description_edit

        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

    def on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            standard_ui.show_alert_dialog(self, "作者名称不能为空。")
            return
        description = self.description_edit.toPlainText().strip()
        if self.obj is not None:
            self.obj.name = name
            self.obj.description = description
        else:
            uid = parser.uid_generate()
            self.obj = parser.Author(uid, name, description)
            parser.authors[uid] = self.obj
        self.accept()


class TagEditDialog(standard_ui.Dialog):
    def __init__(self, parent, obj):
        # 本窗口 tag_obj 不允许为 None，需要在外部预先定义，后续须手动添加进标签组中
        super().__init__(parent, "编辑标签" if obj.name else "添加标签")

        name_label = standard_ui.Label(self, "标签名称")
        name_edit = standard_ui.LineEdit(self)
        name_edit.setText(obj.name)

        cancel_btn = standard_ui.Button(self, "取消", function=self.reject)
        accept_btn = standard_ui.Button(self, "完成", function=self.on_accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, cancel_btn, accept_btn])

        layout = standard_ui.VerticalLayout([name_label, name_edit, btn_layout], margin=15)
        self.setLayout(layout)

        self.obj = obj
        self.name_edit = name_edit

        suggested_size = self.sizeHint()
        suggested_size.setWidth(300)
        self.setFixedSize(suggested_size)

    def on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            standard_ui.show_alert_dialog(self, "标签名称不能为空。")
            return
        self.obj.name = name
        self.accept()


class TagBatchAddDialog(standard_ui.Dialog):
    def __init__(self, parent, tag_group):
        # 窗口 accept 后，调用 get_tags 的来到包含所有 tag 名称字符串的列表
        super().__init__(parent, "批量新增标签")

        self.tag_group = tag_group

        text_label = standard_ui.Label(self, "在下方文本框内每行填入一个标签名称")
        text_edit = standard_ui.PlainTextEdit(self)
        cancel_btn = standard_ui.Button(self, "取消", function=self.reject)
        accept_btn = standard_ui.Button(self, "完成", function=self.accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([None, cancel_btn, accept_btn])
        layout = standard_ui.VerticalLayout([text_label, text_edit, btn_layout], margin=15)
        self.setLayout(layout)

        self.text_edit = text_edit

        self.setMinimumWidth(400)
        self.setMinimumHeight(400)

    def get_tags(self):
        lines = [line.strip() for line in self.text_edit.toPlainText().splitlines()]
        tags = [parser.Tag(parser.uid_generate(), line, self.tag_group) for line in lines if line]
        return tags


class TagGroupEditDialog(standard_ui.Dialog):
    def __init__(self, parent, obj=None):
        # tag_group_obj 为 None 时，本窗口 accept 后会自动在 parser.tag_group 中添加作者
        super().__init__(parent, "编辑标签组" if obj else "新建标签组")

        if obj is None:
            obj = parser.TagGroup(parser.uid_generate(), "", False, False, [])

        name_label = standard_ui.Label(self, "标签组名称")
        name_edit = standard_ui.LineEdit(self)
        name_edit.setText(obj.name)

        checkboxes = standard_ui.ButtonGroup(self, False, ["必选", "唯一"]).get_buttons()
        compulsory_checkbox = checkboxes[0]
        unique_checkbox = checkboxes[1]
        compulsory_checkbox.setChecked(obj.compulsory)
        unique_checkbox.setChecked(obj.unique)

        tag_label = standard_ui.Label(self, "标签列表（可拖拽排序）")
        tag_list = standard_ui.ListWidget(self, allow_drop=True)
        tag_list.itemDoubleClicked.connect(self.on_tag_double_clicked)
        for tag in obj.tags:
            item = standard_ui.ListWidgetItem(tag.name, [(32, tag)])
            tag_list.addItem(item)

        btn_add = standard_ui.Button(self, "添加标签", function=self.add_tag)
        btn_edit = standard_ui.Button(self, "编辑标签", function=self.edit_tag)
        btn_del = standard_ui.Button(self, "删除选中标签", function=self.del_tag, level="danger")
        btn_batch = standard_ui.Button(self, "批量新增标签", function=self.batch_add_tags, level="primary")
        tag_btn_layout = standard_ui.HorizontalLayout([btn_add, btn_edit, btn_del, btn_batch])

        btn_reject = standard_ui.Button(self, "取消", function=self.reject)
        btn_accept = standard_ui.Button(self, "完成", function=self.on_accept, level="primary")
        bottom_btn_layout = standard_ui.HorizontalLayout([None, btn_reject, btn_accept])

        layout = standard_ui.VerticalLayout(
            [name_label, name_edit, compulsory_checkbox, unique_checkbox, tag_label, tag_list, tag_btn_layout,
             bottom_btn_layout], margin=15
        )
        self.setLayout(layout)

        self.obj = obj
        self.name_edit = name_edit
        self.compulsory_checkbox = compulsory_checkbox
        self.unique_checkbox = unique_checkbox
        self.tag_list = tag_list

        self.setMinimumWidth(700)
        self.setMinimumHeight(600)

    def add_tag(self):
        tag = parser.Tag(parser.uid_generate(), "", self.obj)
        dialog = TagEditDialog(self, tag)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            item = standard_ui.ListWidgetItem(tag.name, [(32, tag)])
            self.tag_list.addItem(item)

    def del_tag(self):
        item = self.tag_list.currentItem()
        if item is None:
            standard_ui.show_alert_dialog(self, "请先选择一个标签。")
            return

        obj = item.data(32)
        confirm = standard_ui.show_confirm_dialog(self, f"确定要删除“{utils.get_display(obj)}”吗？")
        if confirm != 1:
            return

        can, msg = parser.check_dependencies(obj)
        if not can:
            force = standard_ui.show_confirm_dialog(self, msg + "\n\n是否强制删除？")
            if force != 1:
                return

        self.tag_list.takeItem(self.tag_list.row(item))

    def edit_tag(self):
        item = self.tag_list.currentItem()
        if item is None:
            standard_ui.show_alert_dialog(self, "请先选择一个标签。")
            return
        tag = item.data(32)
        dialog = TagEditDialog(self, tag)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            item.setText(tag.name)

    def on_tag_double_clicked(self, item):
        tag = item.data(32)
        dialog = TagEditDialog(self, tag)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            item.setText(tag.name)

    def batch_add_tags(self):
        dialog = TagBatchAddDialog(self, self.obj)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            new_tags = dialog.get_tags()
            for tag in new_tags:
                item = standard_ui.ListWidgetItem(tag.name, [(32, tag)])
                self.tag_list.addItem(item)

    def on_accept(self):
        name = self.name_edit.text().strip()
        tags = [self.tag_list.item(i).data(32) for i in range(self.tag_list.count())]
        compulsory = self.compulsory_checkbox.isChecked()
        unique = self.unique_checkbox.isChecked()
        if not name:
            standard_ui.show_alert_dialog(self, "标签组名称不能为空。")
            return
        if not tags:
            standard_ui.show_alert_dialog(self, "至少需要一个标签。")
            return

        self.obj.name = name
        self.obj.compulsory = compulsory
        self.obj.unique = unique
        self.obj.tags = tags
        if not self.obj.uid in parser.tag_groups:
            parser.tag_groups[self.obj.uid] = self.obj

        self.accept()


class MusicFileInfoDialog(standard_ui.Dialog):
    def __init__(self, parent, obj):
        super().__init__(parent, "歌曲文件信息")

        md5_label = standard_ui.Label(self, f"文件MD5：{obj.uid}")
        path_label = standard_ui.Label(self, f"路径：{obj.path}")
        time_label = standard_ui.Label(self, f"导入时间：{utils.get_formated_timestamp(obj)}")

        preview_btn = standard_ui.Button(self, "开始试听", function=self.start_preview)
        preview_btn.setEnabled(False)
        stop_btn = standard_ui.Button(self, "停止播放", function=self.stop_preview)
        stop_btn.setEnabled(False)
        accept_btn = standard_ui.Button(self, "关闭", function=self.accept, level="primary")
        btn_layout = standard_ui.HorizontalLayout([preview_btn, stop_btn, None, accept_btn])

        layout = standard_ui.VerticalLayout([md5_label, path_label, time_label, btn_layout], margin=15)
        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())

        self.preview_btn = preview_btn
        self.stop_btn = stop_btn

        # VLC 初始化
        self.instance = vlc.Instance()
        self.media = self.instance.media_new(obj.path)
        self.player = self.instance.media_player_new()
        self.player.set_media(self.media)

        # 试听控制变量
        self.preview_playing = False  # 是否正在播放
        self.segments = []  # 片段列表，每个元素 (start_sec, play_sec)
        self.segment_index = 0  # 将要播放的片段编号
        self.segment_timer = standard_ui.Timer(self, self.on_segment_end)  # 计时等待片段播放结束
        self.duration = 0  # 音频总时长，毫秒
        self.media.event_manager().event_attach(vlc.EventType(3), self.on_media_parsed)  # EventType.MediaParsedChanged
        self.media.parse()  # 异步解析媒体时长

    def on_media_parsed(self, _):
        self.duration = self.media.get_duration()
        self.preview_btn.setEnabled(True)

    def build_segments(self):
        duration_seconds = self.duration / 1000.0

        if duration_seconds <= 20:
            # 完整重复播放
            return [(0.0, duration_seconds)]
        elif duration_seconds <= 60:
            # 从 50%，0% 各放 10 秒
            return [(duration_seconds * 0.5, 10.0), (0.0, 10.0)]
        else:
            # 从 25%，50%，75%，0% 各放 10 秒
            return [
                (duration_seconds * 0.25, 10.0),
                (duration_seconds * 0.50, 10.0),
                (duration_seconds * 0.75, 10.0),
                (0.0, 10.0)
            ]

    def start_preview(self):
        if self.duration <= 0:
            standard_ui.show_alert_dialog(self, "音乐文件解析失败，无法试听。")
            return
        if self.preview_playing:
            return

        self.preview_playing = True
        self.preview_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.segments = self.build_segments()
        self.segment_index = 0
        self.play_next_segment()

    def stop_preview(self):
        if not self.preview_playing:
            return

        self.preview_playing = False
        self.stop_btn.setEnabled(False)
        self.preview_btn.setEnabled(True)
        self.segment_timer.stop()
        self.player.stop()

    def play_next_segment(self):
        if not self.preview_playing or not self.segments:
            return

        start_second, play_second = self.segments[self.segment_index]
        self.player.play()
        self.player.set_time(int(start_second * 1000))
        self.segment_timer.start(int(play_second * 1000))
        self.segment_index = (self.segment_index + 1) % len(self.segments)

    def on_segment_end(self):
        self.play_next_segment()

    def release_vlc(self):
        if self.player:
            self.player.stop()
            self.player.release()
            self.player = None
        if self.media:
            self.media.release()
            self.media = None
        if self.instance:
            self.instance.release()
            self.instance = None

    def closeEvent(self, event):
        self.stop_preview()
        self.release_vlc()
        super().closeEvent(event)

    def reject(self):
        self.stop_preview()
        self.release_vlc()
        super().reject()

    def accept(self):
        self.stop_preview()
        self.release_vlc()
        super().accept()
