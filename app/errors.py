"""异常体系。

只有一个基类与四个子类，够用就好。异常里带本地化文案：单机工具里，
界面层直接 ``str(error)`` 就能显示，比「结构化字段 + 界面映射」少一半代码。
代价是 core 层绑定了文案层，这个取舍是明确的，不是疏忽。
"""

from __future__ import annotations


class AppError(Exception):
    """本程序抛出的所有异常的基类。"""


class ConfigError(AppError):
    """配置文件缺失、读不出来、或结构不合法。"""


class DataError(AppError):
    """业务数据结构不合法，例如记录字段类型错误。"""


class PlaylistCycleError(DataError):
    """条件歌单之间出现循环引用。"""

    def __init__(self, message: str, chain: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.chain = chain


class ActionError(AppError):
    """动作执行失败，例如导入、换源、删除文件。"""
