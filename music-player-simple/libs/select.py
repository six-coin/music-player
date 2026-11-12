import msvcrt
import os

from libs import color


class Selection:
    def __init__(self, mode, options, prompt, head_prompt, special_keys):
        system_prompt_2_dict = {
            0: "选中目标条目后，用回车键确认选择。",
            1: "选中目标条目后，用回车键将其添加至列表，或从列表中移除。",
            2: "选中目标条目后，用回车键将其添加到列表的末尾，或从列表中移除它及它以后的条目。"
        }
        self.mode = mode  # 选择模式：0 为单项选择；1 为多项选择；2 为顺序选择
        self.head_prompt = head_prompt  # 自定义，在最前面显示的提示
        self.prompt = prompt  # 自定义，解释选择的意义、方法等
        self.system_prompt_1 = "用上下箭头切换选择条目，用左右箭头快速切换选择条目。"  # 操作说明第一行
        self.system_prompt_2 = system_prompt_2_dict[self.mode]  # 操作说明第二行
        self.special_keys = special_keys  # 特殊按键列表，形如 [["Q", "返回主菜单"], ["W", "开启特殊模式"], ...]
        self.selected_index = 0  # 当前选择的（标蓝的）选项序号
        self.selected_cnt = 0  # 顺序选择特有，选择总项数
        self.ori_options = options  # 原始传入的选项列表
        # 对不同的模式进行 self.option 的预处理，不同的模式有不同的结构，说明见下
        # 单项选择：["a", "b", "c"]
        # 多项选择：[["a", True], ["b", False], ["c", False]]，二级列表，第一项是选项，第二项是是否选择
        # 顺序选择：[["a", -1, 0], ["b", 3, 1], ["c", 1, 2]]，二级列表，第一项是选项，第二项是选择顺序（-1 为未选择），第三项是序号
        if mode == 0:
            self.options = self.ori_options
        elif mode == 1:
            self.options = []
            for option in self.ori_options:
                self.options.append([option, False])
        elif mode == 2:
            self.options = []
            for num, option in enumerate(self.ori_options):
                self.options.append([option, -1, num])
        self.option_num = len(self.ori_options)  # 选项总数量
        # 对不同的模式进行 self.special_keys 的预处理
        if mode == 1 or mode == 2:
            if special_keys is None:
                self.special_keys = [["Q", "完成选择"]]
            else:
                self.special_keys.insert(0, ["Q", "完成选择"])

    def do_selection(self):
        self.display_menu()
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch()

                if not self.options and not self.special_keys:
                    continue

                if key == b"\xe0":
                    second_key = msvcrt.getch()
                    # 下箭头
                    if second_key == b"H":
                        self.selected_index = max(0, self.selected_index - 1)
                        self.display_menu()
                    # 上箭头
                    elif second_key == b"P":
                        self.selected_index = min(self.option_num - 1, self.selected_index + 1)
                        self.display_menu()
                    # 左箭头
                    elif second_key == b"K":
                        self.selected_index = max(0, self.selected_index - 5)
                        self.display_menu()
                    # 右箭头
                    elif second_key == b"M":
                        self.selected_index = min(self.option_num - 1, self.selected_index + 5)
                        self.display_menu()
                # 回车
                elif key == b"\r" and self.options:
                    if self.mode == 0:
                        # 单项选择 - 结束选择
                        os.system("cls")
                        return self.selected_index
                    elif self.mode == 1:
                        # 已经选择过的选项，清除自身选择；没有选择过的选项，添加至选择的列表中
                        self.options[self.selected_index][1] ^= True
                        self.display_menu()
                    elif self.mode == 2:
                        # 已经选择过的选项，清除自身及所有序号比自身大的选择
                        if self.options[self.selected_index][1] != -1:
                            lowest_index = self.options[self.selected_index][1]
                            for option in self.options:
                                if option[1] >= lowest_index:
                                    option[1] = -1
                            self.selected_cnt = lowest_index - 1
                            self.display_menu()
                        # 没有选择过的选项，添加至选择的列表中
                        else:
                            self.selected_cnt += 1
                            self.options[self.selected_index][1] = self.selected_cnt
                            self.display_menu()
                # Q 键
                elif self.is_letter(key, "Q") and (self.mode == 1 or self.mode == 2):
                    if self.mode == 1:
                        # 多项选择 - 结束选择
                        os.system("cls")
                        return_list = [num for num, option in enumerate(self.options) if option[1]]
                        return return_list
                    elif self.mode == 2:
                        # 顺序选择 - 结束选择
                        os.system("cls")
                        return_list = sorted((item for item in self.options if item[1] > 0), key=lambda x: x[1])
                        return [item[2] for item in return_list]
                # 特殊键
                elif self.is_special_key(key):
                    os.system("cls")
                    return key.decode("utf-8").upper()

    @staticmethod
    def is_letter(byte, literal):
        return byte == bytes(literal.upper(), "utf-8") or byte == bytes(literal.lower(), "utf-8")

    def is_special_key(self, key_pressed):
        if self.special_keys is None:
            return False
        for special_key in self.special_keys:
            if self.is_letter(key_pressed, special_key[0]):
                return True
        return False

    def display_menu(self):
        os.system("cls")
        if self.head_prompt:
            print(f"{color.cyan}{self.head_prompt}\n")
        print(f"{color.red}{self.prompt}\n")
        print(f"{color.black}{self.system_prompt_1}")
        print(f"{color.black}{self.system_prompt_2}\n")

        if not self.options and not self.special_keys:
            print(f"{color.red}没有可用操作，请退出程序！")
            return

        for index, option in enumerate(self.options):
            selected = index == self.selected_index
            if self.mode == 0:
                display_color = color.blue if selected else color.dim_white
                print(f"{display_color}  {option}")
            elif self.mode == 1:
                display_color = color.blue if selected else color.black if option[1] else color.dim_white
                display_head = "√ " if option[1] else "   "
                print(f"{display_color}{display_head}{option[0]}")
            elif self.mode == 2:
                display_color = color.blue if selected else color.black if option[1] != -1 else color.dim_white
                indent = len(str(len(self.options))) + 1
                option_index_len = len(str(option[1]))
                display_head = indent * " " if option[1] == -1 else str(option[1]) + (indent - option_index_len) * " "
                print(f"{display_color}{display_head}{option[0]}")

        if self.options:
            print()

        if self.special_keys is not None:
            for special_key in self.special_keys:
                print(f"{color.cyan}[{special_key[0]}] {color.white}{special_key[1]}")


def single(options, prompt, head_prompt=None, special_keys=None):
    return Selection(0, options, prompt, head_prompt, special_keys).do_selection()


def multiple(options, prompt, head_prompt=None, special_keys=None):
    return Selection(1, options, prompt, head_prompt, special_keys).do_selection()


def sequential(options, prompt, head_prompt=None, special_keys=None):
    return Selection(2, options, prompt, head_prompt, special_keys).do_selection()
