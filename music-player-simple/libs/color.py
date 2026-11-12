import ctypes
import sys

dim_black = "\033[30m"
dim_red = "\033[31m"
dim_green = "\033[32m"
dim_yellow = "\033[33m"
dim_blue = "\033[34m"
dim_magenta = "\033[35m"
dim_cyan = "\033[36m"
dim_white = "\033[37m"
black = "\033[90m"
red = "\033[91m"
green = "\033[92m"
yellow = "\033[93m"
blue = "\033[94m"
magenta = "\033[95m"
cyan = "\033[96m"
white = "\033[97m"
reset = "\033[39m"


class _AutoResetWrapper:
    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def write(self, text):
        self.stream.write(f"{text}\033[0m")


def init():
    kernel32 = ctypes.windll.kernel32
    # 获取标准输出设备的句柄（-11 代表 STD_OUTPUT_HANDLE，即标准输出流）
    handle = kernel32.GetStdHandle(-11)
    # 用于存储当前控制台模式
    mode = ctypes.c_ulong(0)
    # 获取当前控制台的模式
    kernel32.GetConsoleMode(handle, ctypes.byref(mode))
    # 设置新的控制台模式，允许控制台解析 ANSI 转义序列
    kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    # 包装标准输出流，使其自动加上重置颜色的 ANSI 转义序列
    sys.stdout = _AutoResetWrapper(sys.stdout)
