# 配置与数据格式

本文只写数据：有几个文件、每个键是什么类型、默认多少、越界会怎样。界面操作见 [readme/zh-CN.md](readme/zh-CN.md)，为什么这样分文件见 [architecture.md](architecture.md)。

## 0. 总则

| 项 | 规定 |
|---|---|
| 文件数 | 5 类：`settings.json`、`library.json`、`playlists.json`、`stats/<uid>.json`、`player.json` |
| 编码 | UTF-8，无 BOM，缩进 4 空格，末尾一个换行 |
| 写入 | 临时文件 + `os.replace` 原子替换；中途崩溃不会留下半个文件 |
| 读取 | 一律先夹取再使用；**不信任文件内容** |
| 文件不存在 | 自动生成一份可用内容（统计文件除外，它按需创建） |
| 结构损坏 | `library.json` / `playlists.json` 抛 `ConfigError`，弹窗给日志路径后退出；`settings.json` 与统计文件降级继续 |
| 未知键 | 原样保留，保存时不丢 |
| 位置 | 全部由 `app/paths.py` 推导。数据目录默认 `%PROGRAMDATA%\six-coin\music-player`，可在设置里改，**重启后生效**；相对路径以数据目录为基准 |
| 锁 | 放在 `%LOCALAPPDATA%\six-coin\music-player\locks\`，不跟数据混在一起 |

三个程序对同一份文件的权限：

| 文件 | manager | player | simple |
|---|---|---|---|
| `settings.json` | 读写全部 | 读全部，只写 `player` 节 | 只读 |
| `library.json` | 读写 | 只读 | 只读 |
| `playlists.json` | 读写 | 只读 | 只读 |
| `stats/*.json` | 读写 | 读写 | 读写 |
| `player.json` | 不碰 | 读写 | 不碰 |

跨进程写入一律「取锁 → 重新读盘 → 改 → 原子替换」，不信任内存里的旧值。

## 1. `<数据目录>/settings.json`

```json
{
    "version": 1,
    "common": {
        "theme": "light",
        "language": "zh-CN",
        "debug": false,
        "adaptation": {
            "window": 100,
            "min_plays": 10,
            "base": 0.95,
            "skip_seconds": 30
        }
    },
    "import": {
        "dir": "",
        "clean_audio": true
    },
    "audition": {
        "volume": 0.2
    },
    "simple": {
        "order": "shuffle",
        "volume": 0.2
    },
    "player": {
        "volume": 0.2,
        "order": "shuffle",
        "remember_progress": true,
        "last_playlist": null,
        "last_md5": null,
        "last_position_ms": 0
    }
}
```

### 1.1 `common`

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `theme` | str | 系统主题 | `light` / `dark`，没有 `system`；首次启动读一次系统偏好，旧值 `system` 在读取时定成当时的浅色/深色，其它值回退 `light` |
| `language` | str | 系统语言 | 语言代码，必须存在同名语言包；没有匹配或无法识别时回退 `en-US` |
| `debug` | bool | `false` | 非布尔回退 `false`。为真时 player 与 simple 既不判定也不记录自适应 |
| `adaptation.window` | int | `100` | 10–1000，越界夹取；决定每首歌保留多少条记录 |
| `adaptation.min_plays` | int | `10` | 0–`window`，越界夹取；记录数不超过它时永不跳过 |
| `adaptation.base` | float | `0.95` | 0–0.99，越界夹取；概率 = `min(base, 0.99) × 跳过比例` |
| `adaptation.skip_seconds` | int | `30` | 5–300，越界夹取；播放不足这个秒数就切歌记为跳过 |

`common` 的四项自适应是**全局默认值**。歌单可以在自己的 `adaptation` 里覆盖任意一项，`null` 表示继承。

### 1.2 `import`

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `dir` | str | `""` | 文件对话框的起始目录。空串表示程序目录；相对路径以程序目录为基准；首尾引号会被去掉 |
| `clean_audio` | bool | `true` | 非布尔回退 `true`。为真时导入要调 FFmpeg，缺失会失败并提示 |

### 1.3 `audition`

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `volume` | float | `0.2` | 0–1，越界夹取；非数字回退 0.2。只影响管理器底部的试听条 |

### 1.4 `simple`

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `order` | str | `shuffle` | `shuffle` / `list_loop`；其它值回退 `shuffle`。simple 没有「顺序播放」 |
| `volume` | float | `0.2` | 0–1，越界夹取；simple 只在启动时读一次 |

### 1.5 `player`

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `volume` | float | `0.2` | 0–1，越界夹取；player 拖动音量时回写 |
| `order` | str | `shuffle` | `shuffle` / `list_loop` / `repeat_one`；其它值回退 `shuffle` |
| `remember_progress` | bool | `true` | 为假时 `last_position_ms` 恒写 0，但歌单与曲目仍记住 |
| `last_playlist` | str \| null | `null` | 上次的歌单 uid；歌单已被删除时启动回落到「选个歌单开始」 |
| `last_md5` | str \| null | `null` | 上次的曲目；不在歌单里时落到第一首 |
| `last_position_ms` | int | `0` | 负数夹到 0，非整数回退 0；最多每 10 秒写一次 |

`player` 节里前三个是用户配置（manager 的设置页也写它们），后三个由 player 自写自读，界面上不展示。

### 1.6 夹取规则

| 情况 | 结果 |
|---|---|
| 整个文件不是 JSON 对象 | 全部用默认值，记 warning |
| 某个分节不是对象（`"player": 5`） | 该分节整体回退默认值，其它分节不受影响 |
| 数字字段是字符串 | 回退默认值（不做隐式转换） |
| 数字越界 | 夹到范围内，不报错 |
| 布尔字段不是布尔 | 回退默认值 |
| 未知键 | 原样保留 |

## 2. `<数据目录>/library.json`

```json
{
    "version": 1,
    "authors": [
        { "uid": "6f1c…", "name": "Ludovico Einaudi", "description": "" }
    ],
    "tag_groups": [
        {
            "uid": "9a2b…",
            "name": "风格",
            "compulsory": false,
            "unique": true,
            "tags": [
                { "uid": "11aa…", "name": "古典" },
                { "uid": "22bb…", "name": "电影原声" }
            ]
        }
    ],
    "musics": [
        {
            "md5": "a1b2…",
            "names": ["Experience", "经验"],
            "authors": ["6f1c…"],
            "tags": ["11aa…"],
            "ext": "mp3",
            "duration_ms": 344000,
            "size": 8123456,
            "created_at": 1763000000,
            "updated_at": 1763000000
        }
    ]
}
```

### 2.1 作者

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `uid` | str | — | 32 位小写十六进制；不合法则该条记录被跳过 |
| `name` | str | — | 去首尾空白后不能为空 |
| `description` | str | `""` | 去首尾空白 |

数组顺序就是作者列表顺序，也是歌曲详情里作者选择器的顺序。`uid` 重复时后一条被跳过。

### 2.2 标签组

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `uid` | str | — | 32 位小写十六进制 |
| `name` | str | — | 去空白后不能为空 |
| `compulsory` | bool | `false` | 必选：每首歌至少要有一个这组里的标签 |
| `unique` | bool | `false` | 唯一：每首歌最多只能有一个这组里的标签 |
| `tags[].uid` | str | — | 32 位小写十六进制，组内唯一 |
| `tags[].name` | str | — | 去空白后不能为空；组内不校验重名 |

`compulsory` 与 `unique` 只影响提示与完整性检查，不阻止保存。

### 2.3 歌曲

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `md5` | str | — | 主键，32 位小写十六进制，全库唯一 |
| `names` | str[] | `[]` | 去空、去重、保序；`[0]` 是主名称，其余是别名；全部为空则该条记录被跳过 |
| `authors` | str[] | `[]` | 作者 uid 列表，去重保序；引用不存在的作者不阻断加载，由完整性检查报告 |
| `tags` | str[] | `[]` | 标签 uid 列表，去重保序 |
| `ext` | str | `mp3` | `mp3` / `m4a`；其它值该条记录被跳过 |
| `duration_ms` | int | `0` | 负数夹到 0；`0` 表示未知，界面显示 `0:00` |
| `size` | int | `0` | 负数夹到 0；字节 |
| `created_at` | int | `0` | 导入时间（秒） |
| `updated_at` | int | `0` | 最近一次字段变更（秒）；概览「最近编辑」用它 |

**路径不存进数据。** 文件位置恒为 `<数据目录>/music/{md5}.{ext}`。

## 3. `<数据目录>/playlists.json`

```json
{
    "version": 1,
    "default_uid": "d0d0…",
    "items": [
        {
            "uid": "d0d0…",
            "name": null,
            "builtin": true,
            "kind": "filter",
            "entries": [],
            "filters": [
                { "mode": "include", "target": "all", "values": [] }
            ],
            "adaptation": {
                "enabled": false,
                "window": null,
                "min_plays": null,
                "base": null,
                "skip_seconds": null
            },
            "created_at": 1763000000,
            "updated_at": 1763000000
        },
        {
            "uid": "77aa…",
            "name": "深夜",
            "builtin": false,
            "kind": "manual",
            "entries": ["a1b2…", "d4e5f6…"],
            "filters": [],
            "adaptation": {
                "enabled": false,
                "window": 100,
                "min_plays": 10,
                "base": 0.95,
                "skip_seconds": null
            },
            "created_at": 1763000000,
            "updated_at": 1763000000
        }
    ]
}
```

### 3.1 顶层

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `default_uid` | str | — | 必须指向一个 `builtin` 歌单；否则新建一个默认歌单并立刻落盘 |
| `items` | object[] | `[]` | 歌单列表；`uid` 重复时后一条被跳过 |

### 3.2 歌单

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `uid` | str | — | 32 位小写十六进制 |
| `name` | str \| null | `null` | `builtin` 为真时强制 `null`，显示名走文案键 `overview.default_playlist`；非内置歌单去空白后不能为空 |
| `builtin` | bool | `false` | 只有默认歌单为真。不可删除、不可改名 |
| `kind` | str | `manual` | `manual` 有序；`filter` 是集合。**创建后不可切换** |
| `entries` | str[] | `[]` | 仅 `manual` 使用：歌曲 md5，去重保序；`filter` 歌单该字段被清空 |
| `filters` | object[] | `[]` | 仅 `filter` 使用；`manual` 歌单该字段被清空 |
| `adaptation.enabled` | bool | `false` | 该歌单的自适应开关 |
| `adaptation.window` | int \| null | `null` | `null` 表示继承 `common.adaptation.window` |
| `adaptation.min_plays` | int \| null | `null` | 同上，继承 `common.adaptation.min_plays` |
| `adaptation.base` | float \| null | `null` | 同上 |
| `adaptation.skip_seconds` | int \| null | `null` | 同上 |
| `created_at` / `updated_at` | int | `0` | 秒；任何字段变更都刷新 `updated_at` |

### 3.3 条件

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `mode` | str | `include` | `include` 做并集，`exclude` 做差集；其它值该条记录被跳过 |
| `target` | str | `all` | `all` / `music` / `playlist` / `tag` / `author`；其它值该条记录被跳过 |
| `values` | str[] | `[]` | 目标为 `all` 时强制清空；**允许为空**，空条件命中零首歌 |

条件按数组顺序求值。引用另一个条件歌单时递归解析，出现环抛 `PlaylistCycleError`，界面只标红那一行。

**至少一条条件。** 删掉最后一条时 `normalize()` 会补回「包含 · 全部歌曲」，否则保存出去的文件通不过校验，下次加载会把整条歌单当成坏记录丢掉。

## 4. `<数据目录>/stats/<歌单标识>.json`

```json
{
    "version": 1,
    "playlist": "d0d0…",
    "songs": {
        "a1b2…": {
            "records": "0110100101",
            "auto_skipped": 3,
            "last_played_at": 1763000000
        }
    }
}
```

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `playlist` | str | — | 歌单 uid，与文件名一致；只用于排查 |
| `songs` | object | `{}` | 键是歌曲 md5；不是字符串的键被忽略 |
| `songs[].records` | str | `""` | 只保留 `0` / `1`，其它字符被丢弃；`1` = 阈值内被跳过，`0` = 未跳过；从左到右由旧到新 |
| `songs[].auto_skipped` | int | `0` | 自动跳过次数，只用于展示，不参与判定 |
| `songs[].last_played_at` | int | `0` | 秒 |

- 新记录追加在末尾；长度超过该歌单的 `window` 时从头部截断。
- 一个歌单一份文件：写入量小、互不阻塞、损坏只影响一个歌单。
- 歌单关闭自适应时**一个字节都不写**。
- 换源时键从旧 md5 搬到新 md5；新键已存在则按时间先后合并后截断。

## 5. `<数据目录>/player.json`

```json
{
    "version": 1,
    "window": { "width": 960, "height": 620 },
    "queue_visible": true
}
```

| 字段 | 类型 | 默认 | 取值与行为 |
|---|---|---|---|
| `window.width` | int | `960` | 小于 760 夹到 760；大于屏幕宽时创建窗口时再夹一次 |
| `window.height` | int | `620` | 小于 480 夹到 480；同上 |
| `queue_visible` | bool | `true` | 非布尔回退 `true` |

只放「manager 不该看到、也不该覆盖」的界面状态。文件损坏时整份忽略，用默认值。

## 6. 校验时机

| 时机 | 检查什么 | 失败怎么办 |
|---|---|---|
| 启动读设置 | JSON 结构、分节类型、数值范围 | 夹取或整节回退，记 warning，继续运行 |
| 启动读库 | 顶层必须是对象；逐条归一化 + 校验 | 顶层不是对象 → `ConfigError` 退出；单条不合法 → 跳过该条并记 warning |
| 启动读歌单 | 同上，另外校验 `default_uid` 指向内置歌单 | 同上；没有可用默认歌单就新建一条并落盘 |
| 保存库 / 歌单 | 写入前 `normalize()` + `validate()` | 抛 `DataError`，调用方转成界面提示，不写盘 |
| 导入 / 换源 | 后缀白名单、MD5、冲突 | 单条失败记入错误清单，继续下一条 |
| 读统计 | 文件是对象、`songs` 是对象 | 结构错 → `ConfigError`，该歌单按「无记录」处理 |

## 7. 语言包

| 项 | 规定 |
|---|---|
| 位置 | `app/locales/{语言代码}.json`，文件名就是语言代码（BCP-47） |
| 现有语言 | `zh-CN`、`en-US` |
| 首键 | 必须是 `language.name`，值用该语言自己的文字写自己的名字 |
| 键命名 | 点分小写：`<域>.<对象>_<属性>`，如 `settings.theme_hint` |
| 占位符 | 统一 `{name}`，不允许中文占位符 |
| 列举分隔符 | 从 `list.separator` 取（中文 `、`，英文 `, `），不在代码里写死 |
| 缺键回退 | 当前语言 → `zh-CN` → 键名本身，绝不抛异常 |
| 一致性 | 两份包的键集合与每个键的占位符集合必须完全相等（由 `tests/test_i18n.py` 守卫） |

新增一种语言：把 `{代码}.json` 放进目录即可，设置页的语言选项由目录扫描得出，**按文件名排序、不对中文特判**，不需要改代码。缺键回退 `en-US`。

## 8. 日志

| 项 | 规定 |
|---|---|
| 位置 | `%LOCALAPPDATA%\six-coin\music-player\logs\` |
| 文件名 | `{manager\|player\|simple}_{YYYY-MM-DD_HH-MM-SS}.log`，每次启动一个 |
| 轮转 | 单文件 5 MB |
| 保留 | 14 天 |
| 级别 | `DEBUG` 起 |
| 格式 | `[{level}] [{time:YYYY-MM-DD HH:mm:ss}] {message}` |
| `diagnose` | 关闭：不把局部变量写进日志，避免泄露密钥 |
| 写入 | `enqueue=True`，多线程安全；致命错误先 `logger.complete()` 再退出 |

日志内容写「发生了什么 + 关键参数」，不写「进入函数」这类噪音。三个程序共用同一个目录，靠文件名前缀区分。

## 9. `assets/`

| 目录 | 内容 | 删了会怎样 |
|---|---|---|
| `<数据目录>/music/` | 入库音频，文件名 `{md5}.{ext}` | 对应歌曲变成「文件缺失」，库记录还在 |
| `assets/temp/` | 清洗中间产物，导入结束即删 | 无影响；残留文件可以手动删 |

`assets/` 不进版本库，也不参与完整性检查的「孤儿文件」以外的判断。孤儿文件指「文件在、库里没有记录」，修复时会送进回收站。
