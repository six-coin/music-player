# player 架构与实施计划

> 本项目遵循 `reference.md`。偏离标准的地方集中在 §16。
> 本文把 `plan_player.md`（要什么）落成「由哪些文件、按什么顺序做」；不写具体代码，但给出可以直接照着写的类型、字段与方法名。
> 只覆盖 player。manager 与 simple 见各自的计划文档。

---

## 1. 目标与边界

### 1.1 一句话

一个只负责播放的桌面窗口：读 manager 配好的歌单与设置，写播放位置与自适应记录，别的都不碰。

### 1.2 硬约束

| 约束 | 原因 | 谁在守 |
|---|---|---|
| 不写 `library.json` / `playlists.json` | 播放器不是编辑器；两个进程同时改库必然丢数据 | `test_player_api.py::test_player_leaves_library_untouched` |
| 只写 `settings.player` 下的五个键 | `plan_player` §5「只写播放位置与自适应记录」，音量与模式是 §4 明确要求记住的 | §6.1 写入表 + 代码评审 |
| `core` 不导入界面库 | 状态机要能被纯 pytest 覆盖 | `test_source_hygiene.py::test_core_has_no_ui_imports`（已有） |
| 入口 < 30 行 | 装配集中在一处 | `test_source_hygiene.py::test_player_entry_stays_thin`（新增） |
| 队列顺序 = 实际播放顺序 | 队列是承诺，不是装饰 | `test_player_session.py::test_queue_follows_the_round` |
| 队列永远是完整歌单 | 本轮修订；替代 `plan_player` §4.3 的「跳过即移除」 | `test_player_session.py::test_queue_shows_the_whole_playlist_with_states` |

### 1.3 做什么

| 能力 | 说明 |
|---|---|
| 歌单 | 左栏列出全部歌单与歌曲数，当前高亮，底部显示当前模式 |
| 播放 | 点歌单从第一首开始；播放/暂停、上一首/下一首、拖进度、拖音量 |
| 模式 | 随机 / 列表循环 / 单曲循环，三者都是无尽的 |
| 队列 | 右栏显示接下来会播什么，点即跳转，可收起 |
| 自适应 | 按歌单配置在切歌前判定，命中就静默跳过；队列里这首变成已播（灰） |
| 记忆 | 歌单、曲目、位置、音量、模式、窗口尺寸、队列开合 |
| 异常 | 空歌单、文件缺失、播放失败都有对应界面，不弹窗、不中断队列 |
| 快捷键 | 只在窗口前台生效的六个键 |

### 1.4 不做什么

- 不做封面、歌词、频谱（`plan_player` §6）。
- 不做媒体键与全局热键（`plan_player` §4.6）。
- 不做播放历史、拖拽调序、删除单曲（`plan_player` §8）。
- **不做任何设置入口**：没有设置页、没有主题开关、没有偏好弹窗。所有设置都在 manager 里改，player 只读。
- **不做运行期热加载**：播放中 manager 改了歌单，player 不跟着变。理由见 §9.9。

### 1.5 与另外两个程序的关系

| 关系 | 说明 | 落在哪 |
|---|---|---|
| 与 manager | 只读它配置的歌单与设置，不回写音乐库 | `Library` / `PlaylistStore` 只调 `load` 与 `resolve`，不调 `save` |
| 与 simple | 互不干扰，可以同时开，两边各按自己的规则播放与记账 | 统计走 `StatsStore` 的文件锁；设置走 §6.4 的读改写 |
| 数据一致性 | 只写播放位置与自适应记录 | §6.1 与 §6.3 的写入表 |
| 进程关系 | player 不是 manager 的子窗口，关掉 manager 后照常工作；**player 只允许开一个** | 两个独立入口，`launcher.spawn` 拉起后不等待；player 启动时先取命名互斥量 |

---

## 2. 技术选型

### 2.1 界面：pywebview

与 manager 同一套 HTML/CSS/JS 与同一份设计令牌，改样式刷新即可见；player 的界面是「文字 + 控件 + 留白」，没有表单密集或需要原生窗口特效的地方，Qt 的优势用不上。

代价是启动比进程内窗口慢 300–800ms。播放器是「打开就一直开着」的窗口，不是热键唤起的浮窗，这个代价可以接受。

### 2.2 播放：`<audio>` + 本地媒体服务，不用 python-vlc

| 维度 | `<audio>` + `media_server` | python-vlc |
|---|---|---|
| 复用 | `app/system/media_server.py` 已支持 Range，manager 试听在用 | 需新建一套播放封装 |
| 进度/音量/播完 | 浏览器原生能力，`currentTime` / `volume` / `ended` | 自己轮询 `get_time()`，自己判结束 |
| 依赖 | 无（WebView2 自带解码） | 用户必须装 VLC |
| 拖动进度 | 直接赋值，立即生效 | 需要 `set_time()` + 状态机兜底 |
| 失败可见性 | `error` 事件带 `MediaError.code` | 返回值只有 0/-1 |

结论：**用 `<audio>`**。`simple` 继续用 VLC（控制台轮询模型更适合它），两条播放路径互不影响，`python-vlc` 依赖不为 player 服务。

代价与应对：

- 播放状态在网页里，Python 拿不到「精确的播放秒数」→ 由网页上报，Python 只做判定（§8.4）。
- WebView2 的自动播放策略：首播必然来自点击（点歌单 / 点播放），后续自动续播继承同一次用户激活。若 `play()` 仍被拒绝，网页把状态退回暂停并显示「点一下继续播放」，不静默失败。

### 2.3 一句话结论

**播哪首由 Python 决定，怎么播由网页执行。** 这条线划清了，后面所有契约都是它的推论。

---

## 3. 运行形态与文件结构

### 3.1 新增与改动

```
Music Player/
├─ player.pyw                      新增：入口薄壳（照 reference 2.4）
├─ player.bat                      新增：pythonw 启动（照 1.7）
├─ app/
│  ├─ paths.py                     +UI_PLAYER_DIR +PLAYER_STATE_PATH
│  ├─ settings.py                  +patch_player()；update() 改为先读盘再合并
│  ├─ core/
│  │  ├─ queue.py                  新增：play_order / build_round（从 cli/simple 提上来）
│  │  └─ player_session.py         新增：纯状态机
│  ├─ system/
│  │  └─ launcher.py               新增：用正确的解释器拉起另一个入口
│  └─ ui/player/
│     ├─ __init__.py
│     ├─ app.py                    窗口装配
│     ├─ api.py                    JS 桥
│     ├─ index.html
│     ├─ styles.css
│     └─ app.js
├─ config/player.json              新增：player 私有 UI 状态（不进版本库）
└─ tests/
   ├─ test_queue.py                由 test_simple_queue.py 改名并改导入
   ├─ test_player_session.py
   ├─ test_player_restore.py
   └─ test_player_api.py
```

`paths.py` 里 `PLAYER_ENTRY` 已经指向 `player.pyw`，只差文件本身。

### 3.2 入口

`player.pyw` 与 `manager.pyw` 同构：把项目根放进 `sys.path`、延迟导入 `app.ui.player.app`、调用 `main()`，不读配置、不建窗口。

`app.py` 的 `main()` 在创建窗口之前先取命名互斥量 `Local\MusicPlayerPlayer`；已有实例在跑就弹一句「播放器已经在运行」并退出。用 `SingleInstance`，与 manager / simple 同一套。

`player.bat` 照 `manager.bat`：`@echo off` / `chcp 65001 >nul` / `setlocal` / `cd /d "%~dp0"` / 检查 `.venv\Scripts\pythonw.exe` / `start "" ".venv\Scripts\pythonw.exe" "player.pyw"`。

### 3.3 依赖

不新增。`pywebview`、`loguru` 已有；媒体服务是标准库；`python-vlc` 仍只服务 simple。

---

## 4. 分层与模块职责

### 4.1 依赖方向

```
player.pyw
   └─ ui/player/app.py            窗口、尺寸、主题落地、关闭握手
        └─ ui/player/api.py       快照、i18n、持久化、媒体服务
             ├─ core/player_session.py    队列与模式的状态机（纯）
             │    └─ core/queue.py        一轮的顺序
             ├─ core/library.py           只读
             ├─ core/playlists.py         只读（resolve）
             ├─ core/stats.py             写（锁内）
             └─ system/{media_server, launcher, atomic, filelock}
```

只朝下，没有反向依赖。

### 4.2 模块职责

| 模块 | 只做 | 不做 |
|---|---|---|
| `core/queue.py` | 把歌单解析结果排成一轮：手动保序、条件按名、随机洗牌与接缝处理 | 不知道「当前播到哪」 |
| `core/player_session.py` | 当前歌单、轮次、索引、模式、pin、自适应钩子、命令生成 | 不读文件、不碰 i18n、不碰界面 |
| `ui/player/api.py` | 加载库/歌单/设置/统计；把网页调用翻译成 session 操作；组装快照；按 §6 写盘 | 不实现队列规则 |
| `ui/player/app.py` | 建窗口、算尺寸、解析主题、关闭保存 | 不碰业务 |
| `ui/player/app.js` | 渲染快照、驱动 `<audio>`、上报事件 | 不决定播哪首 |
| `system/launcher.py` | 用正确的解释器与工作目录拉起另一个入口，失败返回 False | 不判断该不该拉 |

判断一个函数放哪，问一句：**它需要知道「现在该播哪首」吗？** 需要 → session；需要知道「用户看到什么」→ ui；都不需要 → queue。

### 4.3 与 simple 共用队列规则

`build_queue` / `play_order` 现在住在 `app/cli/simple.py`。player 需要一模一样的洗牌与接缝规则，复制一份必然漂移：

```
app/cli/simple.py 的 build_queue / play_order
        ↓ 原样搬
app/core/queue.py（build_queue 改名 build_round，与「待播队列」区分）
        ↓
simple 与 player 都 import 它
```

行为不变，`tests/test_simple_queue.py` 改名 `test_queue.py` 并改导入。这是本次唯一触碰 simple 的改动。

---

## 5. 状态模型

### 5.1 `PlayerSession` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `mode` | `shuffle` / `list_loop` / `repeat_one` | 来自 `settings.player.order` |
| `playlist_uid` | `str \| None` | 当前歌单；None 表示未选 |
| `order` | `list[str]` | 当前这一轮的顺序（md5），永远是整张歌单 |
| `index` | `int` | 当前曲在 `order` 里的位置；-1 表示没有，`len(order)` 表示整轮已过 |
| `pin` | `Pin \| None` | 单曲循环选歌（见 5.4） |
| `playing` | `bool` | 由网页事件镜像，不用于判定 |
| `position_ms` | `int` | 网页最后上报的位置，只用于恢复与落盘 |
| `seq` | `int` | 命令序号，每次 Load/Stop +1 |
| `last_command` | `Load \| Stop \| None` | 快照里重复下发，网页按 `seq` 去重 |
| `notice` | `Notice \| None` | 结构化提示，文案由 api 层翻译 |

### 5.2 三种模式

| 模式 | 一轮的顺序 | 一轮结束 | 上一首 | 下一首 | 队列显示 |
|---|---|---|---|---|---|
| `shuffle` | 洗牌；当前曲固定在第 1 位；新一轮首曲避开上一轮末曲 | 生成新一轮 | 本轮内前一曲，到头禁用 | 本轮内后一曲，到头开新一轮 | 整张歌单：已播灰 / 当前高亮 / 待播正常 |
| `list_loop` | 歌单顺序 | 回到第 1 首 | 同上，到头禁用 | 同上，到头回第 1 首 | 同上 |
| `repeat_one` | 歌单顺序 | 重播当前曲 | 前一曲，到头禁用 | 后一曲，到头回第 1 首 | 整张歌单，只有当前高亮（没有「已播」） |

- 模式切换即时生效，不重载歌单：以**当前曲**为锚重建 `order`。
- 随机模式把当前曲放在新一轮第 1 位，是为了让「上一首」在切换后立刻有确定含义（禁用），而不是回到一个用户没见过的位置。

### 5.3 队列的推导

```
queue = order                                   # 整张歌单，不截断、不预生成下一轮
state = played (i < index) / current (i == index) / upcoming (i > index)
```

- **永远显示完整歌单**：队列不是「接下来几首」，而是这一轮的全貌。已播的灰、正在播的高亮、待播的正常。
- **下一轮只在播完之后生成**：最后一首播完（或按下一首）才 `_next_round()` 重建 `order`；在生成之前，队列里没有「下一轮」的影子。
- **不保留上一轮**：进入新一轮后 `index = 0`，「上一首」禁用，回不到上一轮的队列。
- 队列里除当前曲外都可以点，包括已播的——点回去就从那首重新开始，它后面的又变回待播。
- `repeat_one` 且无 pin：整张歌单，只有当前高亮（单曲循环没有「已播」的概念）。
- `repeat_one` 且有 pin：只显示「单曲循环：<歌名>」，不列其它曲。

### 5.4 单曲循环的 pin

只有当选中的歌**不在当前歌单**时才建立 pin：

| 字段 | 说明 |
|---|---|
| `md5` | 被循环的歌 |
| `origin_index` | 建立 pin 时 `order` 里的位置 |
| `origin_position_ms` | 建立 pin 时的播放位置 |
| `playlist_uid` | 原歌单，用于校验中途是否被切走 |

规则：

- 选中的歌就在当前歌单里 → 只是跳过去 + 切到 `repeat_one`，不建 pin。
- 退出 `repeat_one`（切到另两个模式）→ 恢复原歌单、原曲、原位置，播放/暂停状态保持不变。
- pin 状态下点上一首/下一首 → 清 pin，从 `origin_index` 前后走一首。
- 切歌单 → 清 pin。

### 5.5 命令

```python
@dataclass(frozen=True, slots=True)
class Load:
    seq: int
    md5: str
    position_ms: int
    autoplay: bool


@dataclass(frozen=True, slots=True)
class Stop:
    seq: int
```

- `seq` 单调递增；每份快照都带 `last_command`，网页只在 `seq` 变化时执行。
- 这样「拉一次状态」与「点一次下一首」走同一条路：网页只认 `seq`，不认调用来源，重放安全。

### 5.6 判定钩子

```python
@dataclass(frozen=True)
class Hooks:
    available: Callable[[str], bool]       # 文件在不在
    should_skip: Callable[[str], bool]     # 自适应判定
    on_auto_skip: Callable[[str], None]    # 记 auto_skipped
```

session 不认识文件系统与统计，三个钩子由 api 注入；测试里换成计数器与固定返回值。

---

## 6. 配置与数据

### 6.1 `settings.json`：只写 player 节

| 键 | 类型 | 读写 | 写入时机 |
|---|---|---|---|
| `player.volume` | 0–1 float | 读写 | 拖动结束、↑/↓ |
| `player.order` | 三选一 | 读写 | 切模式 |
| `player.remember_progress` | bool | 只读 | 启动 |
| `player.last_playlist` | uid / null | 读写 | 切歌单、切曲、关闭 |
| `player.last_md5` | md5 / null | 读写 | 同上 |
| `player.last_position_ms` | int | 读写 | 每 10 秒 + 暂停/跳转/切曲/关闭 |

`common.theme` / `common.language` / `common.adaptation.*` 只读。

`remember_progress=false` 时 `last_position_ms` 恒写 `0`：关掉的是「记住进度」，不是「记住歌单」，把旧位置留在文件里，等用户重新打开开关时会跳到一个莫名其妙的位置。

**与 `plan_manager.md` §3.4 的差异**：那里写「player 只回写 `last_*` 三个字段」，但 `plan_player.md` §4.1 与 §4.5 要求音量与模式也被记住。以 `plan_player.md` 为准：player 回写 `player` 节下的五个键，`remember_progress` 只读。为避免两个进程互相覆盖，写入必须走 §6.4。

### 6.2 `config/player.json`：player 私有

```json
{
    "version": 1,
    "window": { "width": 960, "height": 620 },
    "queue_visible": true
}
```

- 只放「manager 不该看到、也不该覆盖」的界面状态。
- 读时夹取：宽 ≥ 760、高 ≥ 480、不超过屏幕；`queue_visible` 非 bool 就按 `true`。
- 关闭时写一次；队列开合立即写（频率低，不必防抖）。

### 6.3 统计

- 只在歌单 `adaptation.enabled` 为真时写。关掉自适应的歌单，一个字节都不写。
- 一次播放结束写一次：

| 情形 | 记录 |
|---|---|
| 自然播完（含单曲循环重播） | `0` |
| **下一首按钮 / `Ctrl+C`**，`played_ms < skip_seconds × 1000` | `1` |
| **下一首按钮 / `Ctrl+C`**，已过阈值 | `0` |
| 上一首、点队列、切歌单、选循环曲 | 不记录 |
| 自适应跳过 | 不记录，只 `auto_skipped += 1` |
| 关闭程序、崩溃 | 不记录 |

**只有「跳过当前歌」这一个动作会检测实际播放时长并记账**：按钮与 `Ctrl+C` 走同一条 `next_track`。上一首、点队列、切歌单都不碰自适应数据，避免用户在队列里来回点就把统计搅乱。

- 复用 `StatsStore`（已有文件锁），player 不新增写入路径。

### 6.4 写入协议

`settings.json` 有两个进程会写（manager 改设置、player 记进度），必须收口：

```
patch_player(patch)
  → 取 settings.json.lock
  → 重新读盘（不信任内存）
  → clamp
  → 只改 player 节里指定的键
  → 原子替换
```

同时把 `SettingsStore.update()` 也改成「先读盘再合并 patch」。现在 manager 内存里的 `last_*` 是启动时的旧值，整份写回会把 player 刚记的进度洗掉——这是现存的跨进程缺陷，改动不到十行，顺手修掉。

### 6.5 不碰的东西

- 不写 `library.json`、`playlists.json`。
- 不写 `assets/`。
- 不改 `common.*`（主题与语言在 manager 里改，见 §17）。

---

## 7. 界面

### 7.1 骨架

```
┌──────────────┬────────────────────────────────┬──────────────┐
│ 歌单 200px    │ 正在播放 minmax(0, 1fr)          │ 待播 264px    │
│              │                                │              │
│ 默认歌单   37 │   Experience                   │ 1  Yellow    │
│ 深夜       12 │   Ludovico Einaudi             │ 2  Aware     │
│ 通勤       28 │                                │ 3  Eternity  │
│              │   00:42 ─────●──────── 05:44    │ 4  Rapture   │
│              │                                │              │
│              │      ⏮    ▶    ⏭   🔀 🔁 🔂     │              │
│              │                                │              │
│              │   🔊 ───────●────  80%          │              │
│              │                                │              │
│ 模式：随机     │                                │              │
└──────────────┴────────────────────────────────┴──────────────┘
```

- `grid-template-columns: 200px minmax(0, 1fr) 264px`。`minmax(0, 1fr)` 不能写成 `1fr`，否则长歌名会把中栏撑出横向滚动条。
- 最小窗口 760px 时中栏剩 296px：三个 36px 的传输键 + 三个 28px 的模式键放得下，音量单独一行。
- 收起队列时切到 `200px minmax(0, 1fr)` 并隐藏右栏，**不做宽度动画**（reference 3.8 只允许动 opacity/transform）。
- 三栏各自 `min-height: 0` + `overflow-y: auto`，滚动互不影响。

### 7.2 三栏

| 区域 | 内容 | 交互 |
|---|---|---|
| 左栏 | 歌单名 + 歌曲数；当前歌单高亮；底部一行「模式：随机」 | 点歌单 → 载入并从第一首播放 |
| 中栏 | 顶部一个 28px 的队列开关；曲名 21px、作者 12.5px；进度条 + 两个时间；传输键 + 模式键；音量条 + 百分比 | 见 §7.5；`repeat_one` 时曲名右侧多一个「选一首循环」ghost 按钮 |
| 右栏 | **整张歌单**：序号 + 曲名；已播 `--muted`、当前 `--blue-soft` 高亮、待播正常；缺失的曲目带「· 文件缺失」 | 除当前曲外单击跳转；换曲时自动把当前曲滚进视野；头部一个 28px 收起按钮 |

- 队列行只放序号与曲名（264px 放不下两行），完整信息走 `title` 属性。
- 当前歌单高亮用 `--blue-soft` 底 + `--blue-text` 字；不要只靠左侧色条。
- 播放键是 44px 圆形图标键，不套 `.btn.primary`——一屏里没有第二个主操作，不需要抢焦点。

### 7.3 空状态

三种，文案与按钮都不同：

| `empty` | 触发 | 中栏 |
|---|---|---|
| `no_playlist` | 一个歌单都没有（默认歌单被删的极端情况） | 「还没有歌单，先去管理器建一个」+ 「打开管理器」主按钮 |
| `no_selection` | 有歌单但没选（含「上次的歌单已被删除」） | 「选个歌单开始」+ 一句说明，无按钮 |
| `empty_playlist` | 选中的歌单解析出 0 首 | 「这个歌单还没有歌曲」+ 「打开管理器」主按钮，不自动播放 |

空状态按 reference 3.6.4：96px 线性图标 + 标题 + 说明 + 主按钮，图标手写 SVG。

### 7.4 提示条

中栏顶部一行，12.5px，`--amber-soft` 底 + `--amber-text` 字，4 秒后淡出；不遮挡控件、不弹窗、不打断队列。

只用于三类事：文件缺失、播放失败、歌单循环引用。校验类错误不存在（player 没有输入框，除了选歌搜索）。

### 7.5 快捷键

只响应窗口在前台时的按键，不做媒体键、不做全局热键。

| 按键 | 行为 | 备注 |
|---|---|---|
| `Space` | 播放/暂停 | 输入框内不接管 |
| `←` / `→` | 快退/快进 5 秒 | 时长未知时忽略 |
| `Ctrl+←` / `Ctrl+→` | 上一首/下一首 | 到头时按 §5.2 处理 |
| `Ctrl+C` | 跳过当前歌，等价于「下一首」 | 只在这里与按钮上记账；输入框内仍是复制 |
| `↑` / `↓` | 音量 ±5% | 夹到 0–100%，四舍五入到 1% |
| `Esc` | 收起队列 | 有弹窗时先关弹窗 |

守卫：

- `event.target` 是 `input` / `textarea` 时不接管（选歌搜索框要能正常输入）。
- 弹窗打开时只处理 `Esc`，其余交给弹窗自己。
- `Space` 全局接管并 `preventDefault()`；按钮用 `Enter` 激活。理由：媒体播放器里 Space 的含义比「激活当前焦点按钮」更约定俗成，而 Enter 激活按钮本来就是原生行为。

### 7.6 组件与尺寸

- 只用 reference 3.5 的令牌与十档字号，不新增颜色。
- 进度条与音量条自绘 `input[type="range"]`：`appearance: none`，轨道 4px、`--surface-muted` 底、`--blue` 填充（`linear-gradient` + `--fill` 变量），滑块 12px 圆点，`:focus-visible` 用 `outline`（不用 `box-shadow`，会被容器裁掉）。
- 时间用 `font-variant-numeric: tabular-nums`，避免秒数跳动时整行抖动。
- 弹窗（选歌）照 reference 3.7.6 三段式，`max-height: 82vh`，打开时给背景 `inert`。
- 令牌块从 manager 的 `styles.css` 原样复制。**两份必须一致**：`test_player_api.py::test_ui_tokens_match` 比较两个文件 `:root` 里的变量名集合，少一个就报错（只比名字不比值，容忍排版差异）。
- 主题：`theme_source === "system"` 时监听 `matchMedia("(prefers-color-scheme: dark)")` 的 `change` 事件实时跟随；设成 `light`/`dark` 时不跟随。首帧由 `<head>` 内联脚本读 `localStorage` 兜底，避免深色下先白一下。

---

## 8. 前后端契约

### 8.1 快照

每个改变状态的方法都返回完整快照，网页整体重绘；网页只保留视图状态（队列滚动位置、弹窗开合、搜索词）。

```json
{
    "ok": true,
    "language": "zh-CN",
    "theme": "dark",
    "theme_source": "system",
    "mode": "shuffle",
    "playlist_uid": "77aa…",
    "playlists": [
        { "uid": "d0d0…", "title": "默认歌单", "count": 37, "active": false },
        { "uid": "77aa…", "title": "深夜", "count": 12, "active": true }
    ],
    "track": {
        "md5": "a1b2…",
        "title": "Experience",
        "authors": "Ludovico Einaudi",
        "duration_ms": 344000,
        "position_ms": 42000,
        "missing": false
    },
    "transport": { "playing": false, "can_prev": false, "can_next": true },
    "queue": {
        "visible": true,
        "items": [
            { "md5": "a1b2…", "title": "Experience", "missing": false, "state": "current" },
            { "md5": "b2c3…", "title": "Yellow", "missing": false, "state": "upcoming" }
        ],
        "current_md5": "a1b2…",
        "pinned": null
    },
    "volume": 0.8,
    "empty": null,
    "notice": null,
    "warnings": [],
    "command": {
        "seq": 7,
        "kind": "load",
        "md5": "a1b2…",
        "url": "http://127.0.0.1:53421/media/tok/a1b2….mp3",
        "position_ms": 42000,
        "autoplay": false
    }
}
```

| 字段 | 说明 |
|---|---|
| `theme` / `theme_source` | 已落地的 `light`/`dark`，与设置里的 `system`/`light`/`dark` |
| `playlists[].count` | 解析后的歌曲数，启动时算一次并缓存 |
| `track.position_ms` | 最后上报值（≤2 秒旧），只用于恢复与首次渲染 |
| `queue.items[].state` | `played` / `current` / `upcoming`；整张歌单，不截断 |
| `queue.current_md5` | 当前曲；队列里除它以外都可以点 |
| `empty` | `null` / `no_playlist` / `no_selection` / `empty_playlist` |
| `notice` | `{"kind": "missing", "title": "…", "count": 1}` 这类结构化数据，文案在网页侧用 `T()` 拼 |
| `command` | `null`，或一个带 `kind`（`load` / `stop`）、`seq` 的对象；`load` 时另带 `md5` / `url` / `position_ms` / `autoplay` |

### 8.2 方法

| 类别 | 方法 | 返回 |
|---|---|---|
| 读取 | `get_strings()` / `get_state()` | 文案表 / 快照 |
| 歌单 | `select_playlist(uid)` | 快照；uid 与当前相同则原样返回，不重置 |
| 传输 | `set_playing(on)` | `{"ok": bool}` |
| 队列 | `next_track(md5, played_ms)` / `prev_track(md5)` / `jump_to(md5)` | 快照；只有 `next_track` 记账 |
| 播放事件 | `track_ended(md5, played_ms)` / `track_failed(md5, reason)` | 快照 |
| 模式 | `set_mode(mode)` | 快照 |
| 单曲循环 | `pick_loop_song(md5)` | 快照 |
| 位置 | `report_position(ms)` | `{"ok": bool}` |
| 音量 | `set_volume(value)` | `{"ok": bool}` |
| 外观 | `set_queue_visible(on)` | 快照 |
| 选择器 | `list_songs(query)` | `{"items": [...]}`，最多 200 条 |
| 系统 | `open_manager()` | `{"ok": bool}` |

规则：

- 越界或非法参数不抛异常，原样返回当前快照。网页收到 Python traceback 是最难排查的一类故障。
- 带 `md5` 的调用一律校验「这个 md5 是不是当前曲」：不是就当作过期事件忽略。这样 `ended` 与随后的点击不会重复记两次账。
- `report_position` / `set_volume` / `set_playing` 是高频或逐帧触发的，返回 `{"ok"}`，不返回快照（reference 3.3.1 的例外）。

### 8.3 事件时序

```
点歌单  select_playlist ──► 快照(seq=1, load) ──► audio.src / currentTime / play()
                                                   └─ play 事件 ──► set_playing(true)

播完    ended ──► track_ended(md5, played_ms) ──► 快照(seq=2, load) ──► 载入下一首

拖进度  input ──► 只更新时间文本
        change ──► audio.currentTime = ms/1000 ──► report_position(ms)

拖音量  input ──► 只更新百分比
        change ──► audio.volume = v ──► set_volume(v)

模式    set_mode ──► 快照（可能带 load，例如退出 pin）──► 按 seq 执行
```

### 8.4 播放秒数怎么算

`<audio>` 的 `currentTime` 在拖动时会跳变，不能用它做差。网页维护一个 250ms 的计时器：

```
tick: 若 !audio.paused → playedMs += min(now - lastTick, 500)
      换曲 → playedMs = 0
```

- 暂停与拖动**不清零**：`played_ms` 是「这一首累计听了多久」，暂停前后、来回拖进度都属于同一首的收听。
- 每 8 次 tick（约 2 秒）调一次 `report_position`。
- `ended` / `next` / `prev` / `jump` 时把 `playedMs` 一起上报，Python 用它判定 `1` 还是 `0`。
- 缓冲停顿会被算进播放时长。本地文件、停顿以毫秒计，这个近似可以接受；换成 `currentTime` 做差反而会把拖动算成听了很久。

### 8.5 前端封装

照 manager 的写法：`bridge()` 判空、`call()` 统一 catch 并 toast、`apply(data)` 整体重绘、`data-i18n*` 替换静态文案、重建列表前记 `data-focus-id`。

不新建 `app/ui/shared/`：player 只复用 Python 侧的 `media_server`，前端格式化函数（`formatDuration` / `esc` / `T`）各自一份，合计不到 40 行，抽共享层的成本高于收益。

---

## 9. 关键流程

### 9.1 启动与恢复

```
logging_setup.setup("player")
  → SingleInstance("MusicPlayerPlayer").acquire() → 失败则提示并退出
  → SettingsStore.load（损坏则备份后继续，见 §11）
  → i18n.set_language(common.language)
  → theme.resolve(common.theme)
  → PlayerApi()：library.load / playlists.load / stats / player.json
  → session.restore(last_playlist, last_md5, last_position_ms)
  → create_window(width, height, min_size=(760, 480), background_color=主题色)
  → attach(window) / closing += api.close
  → webview.start()
  → 网页 get_strings → get_state → 按 command.seq 载入，autoplay=false
```

恢复的六个分支：

| 情况 | 结果 |
|---|---|
| `last_playlist` 为 null | `empty = no_selection` |
| `last_playlist` 已不存在 | `empty = no_selection`，并把该键清空 |
| 歌单解析为 0 首 | `empty = empty_playlist`，不播 |
| `last_md5` 不在歌单 | 停在该歌单第一首，暂停 |
| `last_md5` 在歌单 | 停在该曲，位置 = `last_position_ms`（`remember_progress=false` 时为 0） |
| 该曲文件缺失 | 向后找第一首可用的，暂停，提示条说明 |

**永远以暂停状态打开**（`plan_player` §4.5）。「点歌单」才自动播。

### 9.2 点歌单

```
select_playlist(uid)
  → uid == 当前歌单且当前有曲目 → 原样返回（不重置、不重新从第一首开始）
  → playlists.resolve(uid, library)        # PlaylistCycleError → 提示条，保持原状
  → queue.play_order(content, library)
  → queue.build_round(songs, mode, rng)
  → order / index=0 / pin 清空
  → Load(seq+1, md5, 0, autoplay=True)
```

### 9.3 自然播完

```
ended → track_ended(md5, played_ms)
  → 记 0（自适应开启时）
  → repeat_one ? 同曲重载（position=0，autoplay=True）
               : _advance(+1)
```

### 9.4 下一首 / 上一首 / 点队列

```
next_track(md5, played_ms)          # 按钮与 Ctrl+C 都走这里
  → md5 不是当前曲 → 忽略（过期事件）
  → 记账：played_ms < skip_seconds×1000 ? 1 : 0
  → 有 pin → 清 pin，从 origin_index 前进
  → _advance(+1)
```

`_advance` 是唯一决定「下一首是谁」的地方：

```
从 index 向后找候选
  → hooks.available 为假 → 记入 missing，跳过
  → hooks.should_skip 为真 → on_auto_skip，跳过
  → 找到 → index=候选，返回 Load
本轮扫完 → _next_round()：重新洗牌 / 回到第一首，index=-1，再扫一遍
新一轮仍无候选 → Stop + notice=all_skipped
```

两轮都扫不到就停，不再无限生成新轮——「所有歌都被跳过」是一种要显示出来的状态，不是要死循环的状态。

点队列里的歌走 `jump_to`：在整张 `order` 里找，找到就 `index=它`。已播的也可以点，点回去之后它后面的又变回待播。上一首、点队列都不记账。

### 9.5 自适应

- 判定只在 `_advance` 里发生，点歌单、点队列、选循环曲都不判定——用户明确点的歌被后台吞掉，会像按钮坏了。
- 判定命中不弹提示、不闪警告，队列里这首直接变成已播（灰），用户只会发现这首没播。
- `should_skip` 的实现：`adaptation.should_skip(records, params, rng)`，`records` 来自 `stats.load(playlist_uid)`；`params` 是「歌单覆盖值 + 全局默认值」的合并结果（`adaptation.effective`）。
- 统计在切歌时读一次、判定后更新内存，不每次 stat 文件。

### 9.6 文件缺失与播放失败

```
候选不可用 → missing.add(md5) → 继续找下一个
一次前进里有多首缺失 → 只发一条提示，报第一首的名字
播放中 error / 5 秒未出声 → track_failed → missing.add + 前进 + 提示
```

队列里缺失的曲目**留在原位标灰**（`plan_player` §7 明确要求），与自适应跳过的「变成已播」在视觉上一致，但原因不同：一个文件不在，一个是被判定跳过。

### 9.7 模式切换与单曲循环

```
set_mode(m)
  → m == repeat_one 且当前曲已在歌单里：只切模式，队列改成整张歌单
  → 从 repeat_one 退出且有 pin：Load(原曲, 原位置, autoplay=当前 playing)
  → 其它：以当前曲为锚重建 order，index 指向当前曲
  → patch_player({"order": m})
```

```
pick_loop_song(md5)
  → md5 在当前 order 里：index=它，mode=repeat_one，pin=None
  → 不在：pin = Pin(md5, index, position_ms, playlist_uid)，mode=repeat_one，
          Load(md5, 0, autoplay=True)
```

### 9.8 关闭

```
closing（UI 线程）
  → 不调用 evaluate_js（会死锁，reference 3.3.4）
  → 用内存里的 position_ms（最多 2 秒旧）
  → patch_player(last_playlist / last_md5 / last_position_ms)
  → 写 player.json（window.width / window.height / queue_visible）
  → media_server.stop()
  → return True
```

关闭时最多丢 2 秒进度。用 2 秒的陈旧值换掉一次死锁风险，这笔交易划算；真要做到零丢失，就得在 `closing` 里起线程等网页回话，而那正是 reference 反复警告的坑。

### 9.9 为什么不热加载

播放中重建队列，用户眼前的「接下来」会跳变；而 manager 的改动（导入、改歌单）本来就要重启才能听到。加文件监听只会得到「歌单变了但当前轮还是旧的」这种半更新状态，比不更新更难解释。

结论：启动读一次，重启生效。这条写进「已知限制」，不写成待办。

---

## 10. 线程与并发

| 线程 | 归属 | 做什么 | 禁止 |
|---|---|---|---|
| UI 线程 | pywebview | 窗口、`closing`、尺寸读写 | 阻塞、在 `closing` 里 `evaluate_js` |
| `js_api` 线程 | pywebview，每次调用一个 | 读写 JSON、算队列（毫秒级） | 长任务、`sleep`、等网络 |
| 媒体服务 | `ThreadingHTTPServer` | Range 响应 | 碰业务数据 |
| 音频解码 | WebView2 渲染进程 | 解码与播放 | 与 Python 共享状态 |

规则：

- `PlayerSession` 只在 `api._lock` 内改；快照在同一把锁内组装，不会出现「标题是新的、队列是旧的」。
- 网页是音频状态的唯一真相；Python 的 `playing` / `position_ms` 是镜像，只用于恢复与落盘。两边不一致时以网页为准。
- 跨线程只传数据。媒体服务不知道谁在播，也不该知道。

---

## 11. 错误处理

| 场景 | 策略 |
|---|---|
| `settings.json` 损坏 | 原文件改名备份为 `settings.json.bad`（重名加时间戳）→ 用默认值继续 → 提示条说明「设置已重置，原文件已备份」 |
| `library.json` / `playlists.json` 结构错误 | `ConfigError` → 记日志 → 原生 `MessageBoxW` 给日志路径 → 退出（没有数据就没有可播的东西） |
| 统计文件损坏 | 该歌单按「无记录」处理，记 warning，继续播 |
| 歌单循环引用 | 该歌单不可选，提示条说明，其它歌单照常 |
| 文件缺失 | 跳过 + 队列标灰 + 一行提示 |
| 播放失败（解码错误 / 5 秒未出声） | 同上，不中断整个队列 |
| 写设置失败 | 记日志 + 提示条，界面保持新值（下次事件再试），不假装成功 |
| 媒体服务起不来 | 提示「无法启动本地播放服务」+ 日志；窗口仍打开，歌单可看 |
| 已有实例在运行 | 原生 `MessageBoxW` 提示后退出，不再开第二个窗口 |
| 未捕获异常 | `sys.excepthook` 记录 → `logger.complete()` → `MessageBoxW` → `os._exit(1)` |

原则与 reference 一致：**能降级的降级，不能降级的必须留下可读的原因。** player 的降级底线是「窗口能打开、歌单能看见、能关掉」。

---

## 12. 本地化

只出 `zh-CN`（与 manager 一致，见 §16）。全部文案走 `app/locales/zh-CN.json`，HTML 里写中文兜底。

| 键 | 用途 |
|---|---|
| `player.title` | 窗口标题 |
| `player.already_running` | `播放器已经在运行了。` |
| `player.mode.shuffle` / `.list_loop` / `.repeat_one` | 模式名 |
| `player.queue.title` / `.empty` | 待播队列标题、空队列 |
| `player.queue.pinned` | `单曲循环：{title}` |
| `player.missing` | `文件缺失` |
| `player.notice.missing` | `{title} 的文件缺失，已跳过` |
| `player.notice.failed` | `{title} 播放失败，已跳过` |
| `player.notice.cycle` | `这个歌单存在循环引用，无法播放` |
| `player.notice.all_skipped` | `这个歌单的曲目都被跳过了` |
| `player.notice.settings_reset` | `设置文件已重置，原文件已备份` |
| `player.notice.autoplay_blocked` | `浏览器拦下了自动播放，点一下继续` |
| `player.empty.no_playlist.title` / `.body` | 还没有歌单 |
| `player.empty.no_selection.title` / `.body` | 选个歌单开始 |
| `player.empty.empty_playlist.title` / `.body` | 这个歌单还没有歌曲 |
| `player.action.open_manager` | 打开管理器 |
| `player.action.queue_show` / `.queue_hide` | 展开/收起队列 |
| `player.action.pick_loop` | 选一首循环 |
| `player.pick.title` / `.search` / `.empty` | 选歌弹窗 |
| `player.volume` | 音量 |
| `player.time_unknown` | `--:--` |
| `list.separator` | `、`（作者分隔符，出英文包时改 `, `） |

规则：

- 默认歌单的名字复用 manager 已有的 `overview.default_playlist`，不新造一个键——同一个东西两个名字，迟早不一致。
- 键名点分小写；占位符一律 `{name}`；列举分隔符从语言包取，不写死。
- `test_i18n.py` 已有的守卫继续跑；player 新增的键必须同时出现在 `zh-CN.json` 里，缺键会在界面上露出键名。

---

## 13. 测试

```
tests/
├─ test_queue.py              洗牌覆盖、接缝、列表循环、条件歌单按名排序（原 test_simple_queue.py）
├─ test_player_session.py     模式、轮次、队列、pin、跳过、缺失
├─ test_player_restore.py     启动恢复的六个分支
├─ test_player_api.py         快照结构、非法参数、不写库、令牌一致
└─ test_source_hygiene.py     +player 入口 < 30 行
```

必测的边界：

| 用例 | 断言 |
|---|---|
| `test_shuffle_round_covers_every_song_once` | 一轮内不重不漏 |
| `test_shuffle_seam_avoids_the_previous_last` | 新一轮首曲 ≠ 上轮末曲 |
| `test_queue_shows_the_whole_playlist_with_states` | 整张歌单，已播/当前/待播三态正确 |
| `test_last_track_keeps_the_full_queue` | 最后一首时整张歌单仍在，前两首已播 |
| `test_new_round_starts_at_zero_and_cannot_go_back` | 播完才开新一轮；index=0，上一首禁用 |
| `test_repeat_one_replays_the_same_track` | `on_ended` 返回同一个 md5、position=0 |
| `test_repeat_one_queue_has_no_played_state` | 单曲循环只有当前与待播，没有已播 |
| `test_next_clears_the_pin_and_moves_from_the_origin` | pin 状态下 next → 从 origin 前进，pin 为 None |
| `test_exit_repeat_one_restores_the_origin` | 切模式 → 回到原曲原位置 |
| `test_auto_skip_marks_the_song_as_played` | 命中后那首变成已播，`on_auto_skip` 计数 +1 |
| `test_all_skipped_stops_without_looping` | 全轮跳过 → Stop + notice，不无限循环 |
| `test_missing_track_is_skipped_but_stays_in_the_queue` | 缺失曲仍在队列且 `missing=true` |
| `test_restore_deleted_playlist_falls_back_to_empty` | `empty=no_selection`，不抛异常 |
| `test_restore_track_not_in_playlist_stops_at_the_first` | 落在第一首、暂停 |
| `test_selecting_the_same_playlist_is_a_noop` | 重复点同一歌单，曲目与命令序号都不变 |
| `test_previous_does_not_record` | 上一首不写统计 |
| `test_jump_does_not_record` | 点队列不写统计 |
| `test_queue_snapshot_has_three_states` | 快照里的 `state` 依次是 current/upcoming/played |
| `test_remember_progress_false_writes_zero` | 关掉「记住进度」时位置写 0 |
| `test_player_leaves_library_untouched` | 跑一遍全部 API 后 `library.json` / `playlists.json` 字节不变 |
| `test_invalid_arguments_do_not_raise` | 越界 uid、非法 mode、非法位置都不抛异常 |
| `test_ui_tokens_match` | 两个 `styles.css` 的 `:root` 变量名集合相等 |

界面不做自动化，按 §15 与 reference 3.13 的清单手工过。

---

## 14. 实施阶段

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| P0 骨架 | `player.pyw` / `player.bat`、`paths` 两行、空窗口、文案键、卫生测试 | 双击 `player.bat` 起一个空窗口；`uv run pytest` 全绿 |
| P1 队列核心 | `core/queue.py` 提取、`core/player_session.py`、三个测试文件 | 不建窗口，纯测试覆盖三种模式、pin、跳过、恢复 |
| P2 界面骨架 | 三栏、歌单列表、空状态、主题、令牌 | 用假快照能看出布局；760×480 下不挤压 |
| P3 播放打通 | 媒体服务、`<audio>`、`seq` 命令、进度、音量、seek | 点歌单能出声，拖进度能跳，播完能自动下一首 |
| P4 队列与模式 | 队列渲染、跳转、折叠、三模式、上下首、pin | 队列与实际播放始终一致 |
| P5 自适应 | 钩子、记录、自动跳过移除、缺失与失败 | 手动造 100 条记录，跳过概率与公式一致 |
| P6 记忆与收尾 | `player.json`、`patch_player`、恢复、快捷键、提示条 | §15 全过 |

**P1 必须先于 P2。** 状态机是唯一有分支风险的部分，窗口起来之后再调它，排查成本翻倍；而且 P1 的测试不需要 pywebview，跑得最快。

P3 之前不要碰队列渲染：没有真实播放，「接下来会播什么」没法验证。

---

## 15. 验收清单

- [ ] `setup.bat` 在干净目录一次装好；`player.bat` 双击能起，无控制台黑框
- [ ] 已经开着一个 player 时再双击，弹出「播放器已经在运行了」，不出现第二个窗口
- [ ] 首次启动（无 `player.json`）落在「选个歌单开始」，不报错
- [ ] 点歌单立刻出声，左栏高亮，队列显示整张歌单
- [ ] 再点一次当前歌单：不重置、不回到第一首、进度不动
- [ ] 播完一首自动下一首；最后一首之后按模式回到开头或开新一轮，不会停
- [ ] 随机模式一轮内不重复；新一轮第一首不是上一轮最后一首
- [ ] 列表循环播完最后一首回到第一首
- [ ] 单曲循环重复当前曲；点下一首才换，换完仍是单曲循环
- [ ] 「选一首循环」能选歌单外的歌；队列显示「单曲循环：<歌名>」；切回随机/列表循环回到原位
- [ ] 队列始终是整张歌单：已播灰、当前高亮、待播正常
- [ ] 除当前曲外，点队列任意一首（含已播）立刻切过去，进度从 0 开始
- [ ] 最后一首播完才生成下一轮；进入新一轮后「上一首」禁用
- [ ] `Ctrl+C` 跳过当前歌，效果与「下一首」一致
- [ ] 自适应命中时队列里那首变成已播，无提示、无闪烁
- [ ] 只有「下一首 / Ctrl+C」与自然播完写统计；上一首、点队列、切歌单不写
- [ ] 歌单关闭自适应时，`config/stats/` 下不产生新写入
- [ ] 关掉窗口再打开：歌单、曲目、位置都在，处于暂停；按播放继续
- [ ] 音量、模式、窗口尺寸、队列开合都记住
- [ ] 把某首歌的文件移走：它标灰并显示「文件缺失」，播放继续
- [ ] 把上次记住的歌单删掉：回到「选个歌单开始」，不报错
- [ ] 空歌单不自动播放，显示空状态与「打开管理器」
- [ ] 全部快捷键都生效；输入框里按 Space / Ctrl+C 不触发播放与跳过
- [ ] 浅色/深色各过一遍，无白底白字；系统切主题后重启跟随
- [ ] 1920×1080 与 760×480 两档都不溢出、无横向滚动条
- [ ] 100 首以上的歌单：队列滚动流畅，换曲时当前曲自动滚进视野
- [ ] 60 字符以上的歌名正确省略，不撑破三栏
- [ ] Tab 能走完整个界面；选歌弹窗打开时 Tab 出不去、Esc 能关
- [ ] 播放中打开 manager 改主题，player 不崩（重启后生效）
- [ ] 同时开 player 与 simple，两边都能播，统计不互相覆盖

---

## 16. 偏离标准

| 条目 | 偏离 | 原因 |
|---|---|---|
| 3.2 窗口尺寸 | 固定 960×620、最小 760×480，不按屏幕 85% | `plan_player` §8 已确认；播放器是常驻小窗，铺满屏幕反而难用 |
| 3.1 选型 | player 用 pywebview，不用 Qt | 与 manager 同一套 UI 与令牌；Qt 会引入第二套界面技术栈与 150MB 依赖，而 player 没有需要原生窗口的场景 |
| 2.11 线程 | 音频状态由网页持有，Python 只持镜像 | `<audio>` 是唯一真相；Python 轮询会引入延迟与两套状态 |
| 3.8 动效 | 队列折叠不做宽度动画 | reference 只允许动 `opacity`/`transform`；宽度动画触发布局重排 |
| 3.10 键盘 | `Space` 全局接管（输入框除外） | 媒体播放器的通行做法；按钮用 `Enter` 激活，原生行为不受影响 |
| 1.6 目录 | 新增 `config/player.json` | player 私有界面状态，不该进三端共享的 `settings.json` |
| 2.10 本地化 | 只出 `zh-CN.json` | 与 manager 一致，补英文只需加一个文件 |

---

## 17. 已确认的判断与已知限制

### 17.1 本文做出的判断

| 事项 | 决定 | 依据 |
|---|---|---|
| 队列单击还是双击 | 单击跳转 | `plan_player` §4.1「点队列里的歌 → 立刻切到那首」；§4.3 的「双击」按笔误处理 |
| 自适应作用于哪些切歌 | 自动前进、上一首/下一首走判定；点歌单、点队列、选循环曲不走 | 用户明确点的歌被后台吞掉，会像按钮坏了 |
| 退出单曲循环 | 立即回到原歌单原位置，保持播放/暂停状态 | `plan_player` §4.2 |
| 单曲循环播完是否记账 | 记 `0`（按「自然播完」处理） | `plan_player` §4.5 的记录表 |
| 主题切换入口 | player 内不放，主题由 `common.theme` 决定 | `plan_player` §5 限定 player 只写播放位置与自适应记录；两个地方各放一个主题开关正是 `plan_manager.md` §3.6 要避免的 |
| 启动即播 | 否，恢复后暂停 | `plan_player` §4.5 |
| 队列最后一首 | 播完才生成下一轮，不预生成 | 本轮修订：队列只呈现当前这一轮 |
| 队列形态 | 整张歌单，三态区分已播/当前/待播 | 本轮修订：替代 `plan_player` §4.3 的「跳过即移除」 |
| 重复点当前歌单 | 无操作 | 本轮修订：之前会从第一首重置 |
| 记账入口 | 只有下一首（按钮 / `Ctrl+C`）与自然播完 | 本轮修订：上一首、点队列、切歌单都不记 |
| `Ctrl+C` | 跳过当前歌，等价于下一首 | 本轮新增 |

### 17.2 本轮确认

| 事项 | 决定 |
|---|---|
| 设置入口 | player 内一个都没有：没有设置页、没有主题开关。主题、语言、音量默认值、播放模式默认值都在 manager 里改，player 只读 |
| 运行期刷新 | 不做。启动读一次库与歌单，重启生效 |
| 单实例 | 做。命名互斥量 `Local\MusicPlayerPlayer`，第二次启动弹一句提示后退出 |

### 17.3 已知限制

| 限制 | 后果 | 为什么接受 |
|---|---|---|
| 运行期不热加载库与歌单 | manager 里新导入的歌要重启 player 才出现 | 播放中重建队列会让「接下来」跳变，比看不到新歌更难受（§9.9） |
| 主题与语言只在启动时读 | manager 改了要重启才生效 | 两个进程各持一份设置，做实时同步要引入文件监听与推送，收益不抵复杂度 |
| 关闭时最多丢 2 秒进度 | 极端情况下重开会回退两秒 | 换掉 `closing` 里等网页回话的死锁风险（§9.8） |
