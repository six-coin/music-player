"""快捷键：规范形式、默认绑定与控制台字节映射。

三端用同一个字符串格式描述一个按键：修饰键按 ``Ctrl → Alt → Shift`` 的固定顺序
排列，用 ``+`` 连接，最后一段是主键——``Ctrl+Shift+K``、``Space``、``ArrowLeft``。
统一格式是为了让设置文件可读、可手改，也让管理器里录下来的组合能原样交给
播放器与控制台使用。

这里只有纯逻辑：认字符串、给默认值、把控制台读到的字节翻回同一个格式。
谁响应按键、按键做了什么，都在各自的界面层里。
"""

from __future__ import annotations

MODIFIER_ORDER = ("Ctrl", "Alt", "Shift")

MODIFIER_ALIASES = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift"}

#: 主键的别名表。键名一律小写查表，输出统一用 ``KeyboardEvent.key`` 的写法。
NAMED_KEYS: dict[str, str] = {
    "space": "Space",
    "spacebar": "Space",
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "up": "ArrowUp",
    "arrowup": "ArrowUp",
    "down": "ArrowDown",
    "arrowdown": "ArrowDown",
    "left": "ArrowLeft",
    "arrowleft": "ArrowLeft",
    "right": "ArrowRight",
    "arrowright": "ArrowRight",
}
NAMED_KEYS.update({f"f{number}": f"F{number}" for number in range(1, 13)})

#: 界面上的写法。方向键与 Esc 用符号更省地方，也让按键帽看起来像个键。
PRETTY_KEYS = {
    "ArrowLeft": "←",
    "ArrowRight": "→",
    "ArrowUp": "↑",
    "ArrowDown": "↓",
    "Escape": "Esc",
    "Delete": "Del",
    "PageUp": "PgUp",
    "PageDown": "PgDn",
}

#: 每个程序的动作与出厂绑定。顺序就是设置页里的展示顺序。
#: 出厂值本身也必须是规范形式——前端拿它直接比对按键，写 ``Ctrl+Left`` 会永远匹配不上。
DEFAULTS: dict[str, dict[str, str]] = {
    "manager": {
        "search": "Ctrl+F",
        "import": "Ctrl+I",
        "settings": "Ctrl+,",
    },
    "simple": {
        "skip": "Ctrl+C",
        "quit": "Ctrl+Q",
    },
    "player": {
        "play_pause": "Space",
        "next": "Ctrl+C",
        "prev": "Ctrl+ArrowLeft",
        "seek_back": "ArrowLeft",
        "seek_forward": "ArrowRight",
        "volume_up": "ArrowUp",
        "volume_down": "ArrowDown",
        "queue": "Escape",
        "pick_loop": "Ctrl+L",
    },
}

GROUPS = tuple(DEFAULTS)

#: 控制台能读到的特殊键。其余功能键是两字节，交给固定的「Alt+F4 退出」处理。
CONSOLE_KEYS = {
    "Space": b" ",
    "Enter": b"\r",
    "Tab": b"\t",
    "Escape": b"\x1b",
    "Backspace": b"\x08",
}

#: 这几个字母的控制码与上面的特殊键撞车（Ctrl+H=退格、Ctrl+I=Tab、Ctrl+M=回车），
#: 控制台里分不出来，所以不接受绑定。
CONSOLE_ALIASED = frozenset({"H", "I", "M"})


def _canonical_key(text: str) -> str | None:
    if not text:
        return None
    named = NAMED_KEYS.get(text.casefold())
    if named is not None:
        return named
    if len(text) == 1:
        return text.upper() if text.isalpha() else text
    return None


def normalize(spec: object) -> str | None:
    """把任意写法压成规范形式；认不出来返回 ``None``，绝不抛异常。

    ``ctrl+left`` / ``Ctrl+ArrowLeft`` / ``CTRL + ←`` 都得到 ``Ctrl+ArrowLeft``。
    只有修饰键没有主键的组合（比如只按住 Ctrl）不算一个键，返回 ``None``。
    """
    if not isinstance(spec, str):
        return None
    text = spec.strip()
    if not text:
        # 一个空格就是空格键；一串空白只是没填。
        return "Space" if spec == " " else None

    parts = [part.strip() for part in text.split("+")]
    # ``Ctrl++`` 的最后一个空段代表「加号」这个主键本身。
    if len(parts) > 1 and parts[-1] == "":
        key = "+"
        parts = parts[:-1]
    else:
        key = parts.pop() if parts else ""

    modifiers: set[str] = set()
    for part in parts:
        if not part:
            continue
        modifier = MODIFIER_ALIASES.get(part.casefold())
        if modifier is None:
            return None
        modifiers.add(modifier)

    key = _canonical_key(key)
    if key is None:
        return None
    ordered = [name for name in MODIFIER_ORDER if name in modifiers]
    return "+".join([*ordered, key])


def pretty(spec: str) -> str:
    """界面展示用的写法；认不出来就原样返回，不抛异常。"""
    if not isinstance(spec, str):
        return ""
    return "+".join(PRETTY_KEYS.get(part, part) for part in spec.split("+"))


def clamp(group: str, raw: object) -> dict[str, str]:
    """按一个程序的默认表压平用户写的那一节。

    认不出来的值退回默认，缺的动作补上默认，认不出来的动作名原样留着
    （设置文件的未知键不丢），但值必须是字符串。
    """
    base = DEFAULTS[group]
    result = {
        str(key): value
        for key, value in (raw.items() if isinstance(raw, dict) else ())
        if isinstance(value, str)
    }
    for action, fallback in base.items():
        result[action] = normalize(result.get(action)) or normalize(fallback) or fallback
    return result


def console_bytes(spec: str) -> bytes | None:
    """控制台里这个组合会送进来哪个字节；读不到的返回 ``None``。

    控制台关掉了行输入与已处理输入，于是按键是一个个原始字节：``Ctrl+A``..``Ctrl+Z``
    是 0x01–0x1A，特殊键见 ``CONSOLE_KEYS``。Alt 组合与功能键不走这条路。
    """
    special = CONSOLE_KEYS.get(spec)
    if special is not None:
        return special
    if spec.startswith("Ctrl+") and len(spec) == 6:
        letter = spec[5]
        if letter.isalpha() and letter.isupper() and letter not in CONSOLE_ALIASED:
            return bytes([ord(letter) - 64])
    return None


def from_console(chunk: bytes | None) -> str | None:
    """控制台读到的一个输入块对应哪个规范键；认不出来返回 ``None``。"""
    if not chunk:
        return None
    for spec, value in CONSOLE_KEYS.items():
        if chunk == value:
            return spec
    if len(chunk) == 1 and 1 <= chunk[0] <= 26:
        letter = chr(chunk[0] + 64)
        if letter not in CONSOLE_ALIASED:
            return f"Ctrl+{letter}"
    return None


def console_supported(spec: str) -> bool:
    return console_bytes(spec) is not None
