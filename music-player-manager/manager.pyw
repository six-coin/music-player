import os
import pathlib
import sys

from libs import config
from libs import dialogs
from libs import log
from libs import parser
from libs import standard_ui
from libs import utils


class MainWindow(standard_ui.MainWindow):
    def __init__(self):
        super().__init__(0.5, 0.5, 0.85, 0.85, "音乐管理器")

        log.write("开始主窗口初始化", 3)

        self.dirty = False

        menus = (
            (
                "文件",
                ("保存文件", "Ctrl+S", self.save_all),
                ("编辑首选项", "Ctrl+P", lambda: dialogs.PreferenceDialog(self).exec()),
                ("退出程序", "Ctrl+Q", self.close)
            ),
            (
                "工具",
                ("完整性检查（不含文件校验）", "Ctrl+I", lambda: self.show_integrity_check(False)),
                ("完整性检查（含文件校验）", "Ctrl+L", lambda: self.show_integrity_check(False)),
                ("批量导入音乐", "Ctrl+O", self.open_quick_import)
            )
        )
        self.create_menu_bar(menus)

        self.status_message("就绪")

        tabs = (
            (self.create_music_tab(), "歌曲"),
            (self.create_playlist_tab(), "歌单"),
            (self.create_tag_tab(), "标签"),
            (self.create_author_tab(), "作者"),
            (self.create_music_file_tab(), "歌曲文件")
        )
        self.tab_widget = standard_ui.TabWidget(self, tabs)
        self.set_central_widget(self.tab_widget)

        log.write("主窗口初始化完毕", 3)

    def load_config(self):
        """加载所有配置文件"""
        error_messages = ""

        # 加载首选项
        log.write("开始加载首选项", 3)
        manager_path = pathlib.Path("config") / "manager.json"
        manager_schema = {
            "type": dict,
            "required": ["import_dir", "save_dialog"],
            "properties": {
                "import_dir": {"type": str, "default": ""},
                "save_dialog": {"type": bool, "default": False}
            }
        }
        try:
            config.read(manager_path, manager_schema, call_name="manager")
        except Exception as e:
            config.read_default(manager_path, manager_schema, call_name="manager")
            err_msg = f"读取首选项配置失败：{e}"
            log.write(err_msg, 1)
            error_messages += f"{err_msg}\n将从默认首选项开始，在当前程序配置的首选项可能丢失\n\n"

        # 加载数据
        log.write("开始加载数据", 3)
        file_load_error = parser.file_load()
        if file_load_error:
            log.write(f"部分数据读取失败：\n{file_load_error}", 1)
            error_messages += file_load_error + "\n以上读取失败的数据将从空数据开始，为防止数据丢失，请确认是否继续启动"

        self.refresh_all_tabs()
        self.dirty = False

        if error_messages:
            log.write("打开数据读取错误提示窗口", 3)
            choice = standard_ui.show_text_edit_dialog(
                self, "警告", error_messages,
                [("继续启动", False, 0), ("取消启动", True, 1)],
                800, 300
            )
            if choice in (-1, 1):
                os._exit(0)

    def setup_list_page(self, widget, items_getter, search_keys_getter, search_placeholder, new_callback):
        def refresh_list(filter_text=""):
            filter_text = filter_text.strip()
            list_widget.clear()
            for data_item in items_getter():
                if filter_text:
                    search_keys = search_keys_getter(data_item)
                    if not any(filter_text.lower() in key.lower() for key in search_keys):
                        continue
                list_item = standard_ui.ListWidgetItem(utils.get_display(data_item), data_list=[(32, data_item)])
                list_widget.addItem(list_item)

        search_edit = standard_ui.LineEdit(widget)
        search_edit.setPlaceholderText(search_placeholder)
        search_edit.textChanged.connect(refresh_list)
        edit_callback = lambda: self.edit_item(list_widget.currentItem())
        delete_callback = lambda: self.delete_item(list_widget.currentItem())
        edit_btn = standard_ui.Button(widget, "编辑", function=edit_callback)
        new_btn = standard_ui.Button(widget, "新建", function=new_callback, level="primary")
        delete_btn = standard_ui.Button(widget, "删除", function=delete_callback, level="danger")
        top_layout = standard_ui.HorizontalLayout([search_edit, edit_btn, new_btn, delete_btn])

        list_widget = standard_ui.ListWidget(widget)
        list_widget.itemDoubleClicked.connect(lambda list_item: self.edit_item(list_item))

        layout = standard_ui.VerticalLayout([top_layout, list_widget], margin=15)
        widget.setLayout(layout)

        refresh_list()
        setattr(widget, "refresh_list", refresh_list)

    def create_music_tab(self):
        widget = standard_ui.Widget(self, margin=0)
        self.setup_list_page(
            widget,
            items_getter=lambda: list(parser.musics.values()),
            search_keys_getter=utils.get_music_search_keys,
            search_placeholder="搜索歌曲名称…",
            new_callback=self.new_music
        )
        return widget

    def create_playlist_tab(self):
        widget = standard_ui.Widget(self, margin=0)
        self.setup_list_page(
            widget,
            items_getter=lambda: list(parser.playlists.values()),
            search_keys_getter=lambda playlist: [playlist.name],
            search_placeholder="搜索歌单名称…",
            new_callback=lambda: self.open_playlist_dialog(None)
        )
        return widget

    def create_tag_tab(self):
        widget = standard_ui.Widget(self, margin=0)
        self.setup_list_page(
            widget,
            items_getter=lambda: list(parser.tag_groups.values()),
            search_keys_getter=lambda tag_group: [tag_group.name],
            search_placeholder="搜索标签组名称…",
            new_callback=lambda: self.open_tag_group_dialog(None)
        )
        return widget

    def create_author_tab(self):
        widget = standard_ui.Widget(self, margin=0)
        self.setup_list_page(
            widget,
            items_getter=lambda: list(parser.authors.values()),
            search_keys_getter=lambda author: [author.name],
            search_placeholder="搜索作者名称…",
            new_callback=lambda: self.open_author_dialog(None)
        )
        return widget

    def create_music_file_tab(self):
        widget = standard_ui.Widget(self, margin=0)
        self.setup_list_page(
            widget,
            items_getter=lambda: list(parser.music_files.values()),
            search_keys_getter=lambda music_file: utils.get_music_file_search_keys(music_file),
            search_placeholder="搜索文件 MD5 或关联的歌曲名称…",
            new_callback=self.new_music_file
        )
        return widget

    def refresh_all_tabs(self):
        self.dirty = True
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            refresh_list = getattr(tab, "refresh_list", None)
            if refresh_list:
                search_edit = tab.findChild(standard_ui.LineEdit)
                refresh_list(search_edit.text() if search_edit else "")

    def edit_item(self, item):
        if item is None:
            standard_ui.show_alert_dialog(self, "请先选择要编辑的项目。")
            return
        obj = item.data(32)
        data_type = utils.get_type(obj)
        if data_type == "music":
            self.open_music_dialog(obj)
        elif data_type == "playlist":
            self.open_playlist_dialog(obj)
        elif data_type == "music_file":
            self.open_music_file_dialog(obj)
        elif data_type == "tag_group":
            self.open_tag_group_dialog(obj)
        elif data_type == "author":
            self.open_author_dialog(obj)

    def delete_item(self, item):
        if item is None:
            standard_ui.show_alert_dialog(self, "请先选择要删除的项目。")
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

        parser.delete_object(obj)
        self.refresh_all_tabs()

    def new_music(self):
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
        self.open_music_dialog(None, default_file=music_file)
        self.refresh_all_tabs()

    def new_music_file(self):
        file_path = standard_ui.show_file_dialog(
            self, False,
            "选择音乐文件", config.configs["manager"]["import_dir"], "音频文件 (*.mp3 *.m4a)"
        )
        if not file_path:
            return

        try:
            parser.import_music_file(file_path)
        except Exception as e:
            standard_ui.show_alert_dialog(self, str(e))
            return
        self.refresh_all_tabs()

    def open_music_dialog(self, music_obj, default_file=None):
        dialog = dialogs.MusicEditDialog(self, music_obj, default_file)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            self.refresh_all_tabs()

    def open_author_dialog(self, author_obj):
        dialog = dialogs.AuthorEditDialog(self, author_obj)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            self.refresh_all_tabs()

    def open_tag_group_dialog(self, tag_group_obj):
        dialog = dialogs.TagGroupEditDialog(self, tag_group_obj)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            self.refresh_all_tabs()

    def open_music_file_dialog(self, music_file_obj):
        dialogs.MusicFileInfoDialog(self, music_file_obj).exec()

    def open_playlist_dialog(self, playlist_obj):
        dialog = dialogs.PlaylistEditDialog(self, playlist_obj)
        if dialog.exec() == standard_ui.Dialog.DialogCode.Accepted:
            self.refresh_all_tabs()

    def save_all(self):
        """保存所有文件并显示状态"""
        parser.file_save()
        self.dirty = False
        if config.configs["manager"]["save_dialog"]:
            standard_ui.show_alert_dialog(self, "文件已保存。", title="提示")
        self.status_message("保存成功！", 5000)

    def show_integrity_check(self, if_check_md5):
        """显示文件完整性检查对话框"""
        report = parser.check_integrity(if_check_md5)
        standard_ui.show_text_edit_dialog(self, "完整性检查报告", report, [("确定", True, 0)], 1100, 500)

    def open_quick_import(self):
        """打开快速导入对话框"""
        # 打开文件选择对话框
        files = standard_ui.show_file_dialog(
            self, True,
            "选择音乐文件（可多选）", config.configs["manager"]["import_dir"], "音频文件 (*.mp3 *.m4a)"
        )
        if not files:
            return

        # 解析文件名
        parsed = []
        for file in files:
            parsed.append(utils.parse_file_name(file))

        # 弹出标签选择对话框
        tag_dialog = dialogs.QuickImportTagDialog(self)
        if tag_dialog.exec() != standard_ui.Dialog.DialogCode.Accepted:
            return
        tag_uids = tag_dialog.get_selected_tags()

        # 弹出信息确认对话框
        confirm_dialog = dialogs.QuickImportConfirmDialog(self, parsed)
        if confirm_dialog.exec() != standard_ui.Dialog.DialogCode.Accepted:
            return

        # 导入文件并记录错误
        failed_items = []  # 每个元素：(文件名, 原因)
        for item in parsed:
            file_path = item["path"]

            try:
                music_file = parser.import_music_file(file_path, ignore_exists=False)
            except Exception as e:
                log.write(f"批量导入音乐时发生错误：{e}", 1)
                failed_items.append((pathlib.Path(file_path).name, str(e)))
                continue

            author_uids = []
            for author_name in item["authors"]:
                author_id = next((author.uid for author in parser.authors.values() if author.name == author), None)
                if author_id:
                    author_uids.append(author_id)
                else:
                    new_author_uid = parser.uid_generate()
                    parser.authors[new_author_uid] = parser.Author(new_author_uid, author_name)
                    author_uids.append(new_author_uid)

            title = item["title"]
            if item["marked_for_review"]:
                title = f"【待修改】{title}"

            music_uid = parser.uid_generate()

            parser.musics[music_uid] = parser.Music(music_uid, [title], author_uids, [music_file.uid], tag_uids)

        # 如果有失败项，弹出提示框
        if failed_items:
            report_lines = ["以下文件因重复或错误而未导入："]
            for file_name, reason in failed_items:
                report_lines.append(f"{file_name}：{reason}")
            standard_ui.show_text_edit_dialog(
                self, "批量导入结果", "\n".join(report_lines),
                [("确定", True, 0)], 1100, 500
            )

        self.refresh_all_tabs()
        self.status_message("批量导入完成", 5000)

    def closeEvent(self, event):
        if self.dirty:
            choice = standard_ui.show_message_dialog(
                self, "确认", "文件已被修改，是否保存？",
                [("保存", True, 0), ("不保存", False, 1), ("取消", False, 2)]
            )
            if choice == 0:
                self.save_all()
                event.accept()
            elif choice == 1:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    # 设置当前工作目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 初始化日志
    log.init("manager")

    # 执行程序初始化
    try:
        app = standard_ui.Application(sys.argv)
        window = MainWindow()
        window.show()
        window.load_config()
        sys.exit(app.exec())
    except Exception as e:
        err_msg = f"程序运行中出现未知错误：{e}"
        log.write(err_msg, 0)
        log.error(err_msg)


if __name__ == "__main__":
    main()
