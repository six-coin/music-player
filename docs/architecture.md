# 架构

本项目遵循 Python 桌面项目执行标准（下称 `reference.md`；它与其它本地工具共用一份，放在工具箱目录里，不随本仓库分发）。本文写「为什么这样分层、数据怎么流、哪些约定不能破」；操作步骤见 [readme/zh-CN.md](readme/zh-CN.md)，字段级的配置说明见 [configuration.md](configuration.md)。

## 1. 目标与约束

一句话：三个进程共用一个 JSON 音乐库，管理器写、播放器只读，界面全部是静态 HTML + 无框架 JS。

| 约束 | 原因 | 谁在守 |
|---|---|---|
| `core` 不导入任何界面库 | 队列与自适应要能被纯 pytest 覆盖，也要能被三个入口共用 | `test_source_hygiene.py::test_core_has_no_ui_imports` |
| `system` 不导入界面库 | 系统能力是基础设施，不该知道谁在调用 | `test_source_hygiene.py::test_system_has_no_ui_imports` |
| 全项目不调用 `os.chdir` | 工作目录是进程级全局状态，被所有线程共享 | `test_source_hygiene.py::test_no_working_directory_changes` |
| 入口文件 < 30 行 | 装配集中在一处 | `test_source_hygiene.py::test_manager_entry_stays_thin`、`::test_player_entry_stays_thin` |
| player 不写 `library.json` / `playlists.json` | 播放器不是编辑器；两个进程同时改库必然丢数据 | `test_player_api.py::test_player_leaves_library_untouched` |
| 队列永远是完整歌单 | 队列是承诺，不是装饰 | `test_player_session.py::test_queue_shows_the_whole_playlist_with_states` |
| 两份 `styles.css` 的设计令牌一致 | 两个窗口必须看起来是同一个程序 | `test_player_api.py::test_ui_tokens_match` |
| 非法参数不抛异常 | 网页收到 Python traceback 是最难排查的一类故障 | `test_player_api.py::test_invalid_arguments_do_not_raise`、`test_api.py::test_invalid_section_is_ignored` |
| 两份语言包同键同占位符 | 缺键会在界面上露出键名 | `test_i18n.py::test_every_locale_has_the_same_keys`、`::test_placeholders_match_the_default_language` |

## 2. 目录结构

```
Music Player/
├─ manager.pyw / player.pyw / simple.py     入口薄壳：塞 sys.path、延迟导入、调 main()
├─ app/
│  ├─ paths.py                              全部绝对路径的唯一来源
│  ├─ errors.py                             异常类型（AppError 基类 + 4 个子类）
│  ├─ models.py                             数据结构、归一化、字段校验
│  ├─ settings.py                           设置读写、夹取、原子写、跨进程读改写
│  ├─ i18n.py                               语言包扫描、查表、占位符
│  ├─ logging_setup.py                      loguru 配置、致命错误弹窗
│  ├─ core/
│  │  ├─ library.py                         作者 / 标签组 / 歌曲的读写与查询
│  │  ├─ playlists.py                       歌单读写、条件解析（带环检测）
│  │  ├─ adaptation.py                      跳过概率与记录串的纯函数
│  │  ├─ stats.py                           每个歌单一份统计，锁内读改写
│  │  ├─ importer.py                        导入流水线：准备（重活）+ 提交（轻活）
│  │  ├─ source.py                          换源与删除，失败回滚
│  │  ├─ integrity.py                       完整性检查与按类别修复
│  │  ├─ queue.py                           一轮的播放顺序（洗牌与接缝）
│  │  ├─ player_session.py                  player 的状态机：当前曲、轮次、pin、命令
│  │  └─ naming.py                          文件名清洗与「歌名 - 作者」解析
│  ├─ version.py                           从 pyproject.toml 读版本
│  ├─ bootstrap.py                         迁移、首次运行、重启、提示框
│  ├─ system/
│  │  ├─ atomic.py                          JSON 原子读写
│  │  ├─ filelock.py                        跨进程文件锁
│  │  ├─ ffmpeg.py                          ffmpeg / ffprobe 调用
│  │  ├─ recycle.py                         Windows 回收站
│  │  ├─ single_instance.py                 命名互斥量
│  │  ├─ theme.py                           系统主题读取
│  │  ├─ launcher.py                        用正确的解释器拉起另一个入口
│  │  ├─ media_server.py                    带 Range 的本地媒体服务
│  │  └─ vlc.py                             simple 的播放器适配器
│  ├─ cli/                                  simple 的界面：console 输入、render 绘制、simple 编排
│  ├─ ui/manager/                           api.py（JS 桥）+ app.py（窗口）+ index.html + styles.css + js/
│  ├─ ui/player/                            同上，多一个 player.json 的读写
│  └─ locales/                              zh-CN.json / en-US.json
├─ assets/                                  随程序分发的示例音频
└─ tests/                                   test_*.py
```

运行期文件不在仓库里：数据目录、本地目录、临时目录都由 `paths.py` 指向系统位置，见 2.5。

界面没有构建步骤。两个页面各拆成多个普通 `<script>`，共享全局作用域，加载顺序写在 `index.html` 里：

| 目录 | 文件 | 职责 |
|---|---|---|
| `ui/manager/js` | `core.js` | 全局状态、DOM 选择器、JS 桥、文案、格式化、主题、Toast |
| | `navigation.js` | 分区跳转与「当前选中项」 |
| | `ui-widgets.js` | 自绘下拉框、右键菜单、弹窗 |
| | `render-*.js` | 五个分区与设置页的渲染，`apply()` 是总入口 |
| | `stats.js` / `integrity.js` / `import.js` | 统计抽屉、完整性报告、导入与批量向导 |
| | `actions-*.js` | 用户动作：编辑、删除、换源、批量、试听 |
| | `events-*.js` | 四组事件绑定，`main.js` 里的 `bindEvents()` 汇总 |
| `ui/player/js` | `core.js` / `render.js` / `playback.js` / `picker.js` / `events.js` / `main.js` | 基础设施、渲染、播放执行、选歌弹窗、事件、启动 |

## 2.5 路径、版本与首次运行

| 位置 | 内容 | 默认 |
|---|---|---|
| 程序目录 | 代码与示例音频 | 仓库根目录 |
| 数据目录 | 音乐库、歌单、统计、设置、播放器状态、`music/` | `%PROGRAMDATA%\six-coin\music-player` |
| 本地目录 | `logs/`、`locks/`、`data-dir.txt` | `%LOCALAPPDATA%\six-coin\music-player` |
| 临时目录 | 清洗音频、换源的中间文件 | `%TEMP%\six-coin\music-player` |

- 数据目录可改：设置页写 `data-dir.txt`，**重启后生效**；`paths.resolve_user_path()` 的相对路径以数据目录为基准。
- 旧版本留在程序目录里的 `config/`、`assets/music/`、`logs/` 由 `paths.migrate_legacy()` 在启动最前面搬走（`assets/temp/` 直接删）。
- 统计与设置的锁文件放本地目录（`paths.lock_for()`），不跟数据混在一起。
- 版本号只有 `pyproject.toml` 一处，`app/version.py` 读它。
- 首次运行：`bootstrap.is_first_run()` 看数据目录里有没有 `settings.json`；player / simple 首次启动会拉起管理器（带 `--redirected-from`），管理器依次弹语言、使用说明，最后解释「你打开的不是这个程序」。
- 三个入口各持一个 `Local\MusicPlayer*` 互斥量；重启按钮走「释放锁 → 拉新进程」。

## 3. 分层与依赖方向

```
manager.pyw   player.pyw   simple.py          入口
      │            │           │
      ▼            ▼           ▼
 ui/manager    ui/player     cli/simple        界面层
      │            │           │
      └────────────┴─────┬─────┘
                         ▼
                       core                   纯逻辑
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
  models / settings / errors / i18n / paths   system
```

只朝下，没有反向依赖。判断一个函数放哪层，问一句：**它需要知道「用户看到什么」吗？** 需要就是 ui，不需要就是 core；要跟操作系统打交道就是 system。

`core` 里的例外只有一处：`player_session` 通过注入的 `Hooks` 询问「文件在不在」「要不要跳过」，自己不认识文件系统与统计。

## 4. 数据模型

三份数据 + 一份设置 + 每歌单一价统计，字段级说明见 [configuration.md](configuration.md)。

| 文件 | 内容 | 谁写 |
|---|---|---|
| `<数据目录>/library.json` | 作者、标签组、歌曲（实体） | manager |
| `<数据目录>/playlists.json` | 歌单（引用）与默认歌单 | manager |
| `<数据目录>/stats/<uid>.json` | 每个歌单的自适应记录 | manager、player、simple |
| `<数据目录>/settings.json` | 设置，四个分节 | manager 写全部，player 只写 `player` 节 |
| `<数据目录>/player.json` | 窗口尺寸、队列开合 | player |

**为什么必须分开存：**

1. **库与歌单分开**：歌单是引用，库是实体。换源时只动库里的 `md5` 与歌单里的引用，两边职责清楚。
2. **统计单独成文件**：player 与 simple 会高频写统计，写 `library.json` 会把整个库置于并发风险中；一个歌单一份文件还能让损坏只影响一个歌单。
3. **设置单独一份**：三端都读，谁都不该为了读一个音量值去解析整个音乐库。
4. **`player.json` 独立**：窗口尺寸是 player 私有的界面状态，不该进三端共享的 `settings.json`。

**路径不存进数据。** 文件位置恒为 `<数据目录>/music/{md5}.{ext}`，由 `paths.music_path()` 推导。这样移动程序目录、改盘符都不会让记录失效。

**歌曲身份是内容的 MD5**，不是文件名。清洗开启时算的是清洗产物的 MD5，所以同一首歌的不同标签版本会得到同一个身份。

## 5. 模块职责

| 模块 | 只做 | 不做 |
|---|---|---|
| `paths` | 由 `__file__` 推导绝对路径、解析配置里的相对路径 | 不判断文件是否存在、不建目录 |
| `settings` | 读盘、夹取、合并、原子写 | 不缓存界面状态 |
| `models` | 结构、归一化、校验、`to_dict` 只输出约定键 | 不读写文件 |
| `i18n` | 扫目录、查表、填占位符 | 不关心调用者是谁 |
| `library` | 实体读写与查询、引用统计 | 不解析歌单、不判约束是否阻断 |
| `playlists` | 歌单读写、条件求值、环检测 | 不写统计、不碰界面 |
| `adaptation` | 概率公式、记录串的追加与截断 | 不读文件 |
| `stats` | 一歌单一文件，锁内读改写 | 不算概率 |
| `importer` | 准备（清洗、MD5、时长）与提交（落盘、写库）两段 | 不弹窗、不报进度 |
| `source` | 换源与删除的多文件事务，失败回滚 | 不判断该不该做 |
| `integrity` | 检查与按类别修复 | 不做二次确认 |
| `queue` | 一轮怎么排（洗牌、接缝、按名排序） | 不知道「播到哪」 |
| `player_session` | 当前歌单、轮次、索引、模式、pin、命令 | 不读文件、不碰文案与界面 |
| `ui/*/api.py` | 快照组装、调用翻译、写盘 | 不实现队列规则、不做业务校验 |
| `ui/*/app.py` | 建窗口、算尺寸、主题落地、关闭保存 | 不碰业务 |
| `js/render-*` | 把快照画成 DOM | 不决定播哪首、不改业务数据 |
| `js/playback` | 执行 `command`、统计真实播放秒数 | 不决定播哪首 |

## 6. 关键流程

### 6.1 导入

```
选文件 → 校验后缀 → [清洗] → 算 MD5 → 读时长      ← 准备（锁外，秒级）
                    ↓
            落盘 <数据目录>/music → 写内存库 → 存盘   ← 提交（锁内，毫秒级）
```

分两段是为了并发：管理器用一个后台线程导入，界面线程同时还要出快照。准备阶段不持锁，提交阶段持锁——既不长时间挡住界面，也不会让别的线程撞上「字典在迭代时被改变」。`importer.prepare_import()` / `commit_import()` 是两个入口，`import_file()` 把两者串起来给测试与单文件场景用。

### 6.2 换源

```
选新文件 → 算新 MD5 → 冲突检查 → 落盘新文件 → 迁移引用 → 删旧文件 → 出报告
```

迁移顺序固定：库记录的 `md5/ext/size/duration_ms` → 手动歌单的 `entries` → 条件歌单的 `values` → 每个歌单的统计键 → 旧文件改名送回收站。任何一步失败都按内存备份回滚（`library.to_payload()` / `playlists.to_payload()`），并删掉刚写进去的新文件。

统计迁移失败只记日志：统计是附加物，不该拦住换源。

### 6.3 删除

库、歌单引用、统计三处一起摘；音频先改名成歌名再送回收站，这样在回收站里看到的是「歌名」而不是 MD5。作者与标签组被引用时先阻止并列出引用方，`force` 才连引用一起删。

### 6.4 歌单解析

```
manual → 按 entries 顺序，去重保序
filter → 空集合起步，逐条求值：include 并集，exclude 差集
         目标 all / music / playlist（递归，带访问栈） / tag / author
```

解析是纯函数：输入歌单与库，输出标识集合，不写文件。条件歌单引用另一个条件歌单时递归解析，访问栈里重复出现就抛 `PlaylistCycleError`，界面只把那一行标红，不影响其它条件。

### 6.5 自适应

```
n = 记录条数，s = 其中跳过的条数
n <= min_plays → 概率 0
否则          → 概率 = min(base, 0.99) × s / n
```

判定只在「自动前进」时发生：点歌单、点队列、选循环曲都不判定——用户明确点的歌被后台吞掉，会像按钮坏了。记录只在「下一首 / `Ctrl+C`」与自然播完时写一次，上一首、点队列、切歌单都不碰统计。

### 6.6 player 的切歌

```
next / ended / failed
   → _advance(+1)
        → 从 index 往后扫：文件不在就记 missing 跳过；自适应命中就记 auto_skipped 跳过
        → 扫完一轮 → _next_round() 重建 order → 再扫
        → 两轮都扫不到 → Stop + notice（不再无限生成新轮）
```

`_advance` 是唯一决定「下一首是谁」的地方。`Load` / `Stop` 命令带单调递增的 `seq`，网页只认 `seq`，所以「拉一次状态」与「点一次下一首」走同一条路，重放安全。

## 7. 前后端契约

每个改变状态的方法都返回完整快照，前端整体重绘；前端只保留视图状态（搜索词、多选集合、抽屉开合、概览页签）。

```json
{
  "ok": true,
  "message": "",
  "section": "songs",
  "selection": { "kind": "music", "uid": "a1b2…" },
  "language": "zh-CN",
  "languages": [{ "code": "zh-CN", "name": "简体中文 (中国)" }],
  "theme": "light",
  "library": { "authors": [], "tag_groups": [], "musics": [] },
  "playlists": [],
  "settings": {},
  "status": {},
  "counts": {},
  "overview": {},
  "warnings": [],
  "errors": []
}
```

| 类别 | 方法 | 返回 |
|---|---|---|
| 读取 | `get_strings` / `get_state` / `get_playlist_songs` / `get_playlist_stats` / `get_music_stats` | 数据 |
| 导航 | `select_section` / `select_item` / `clear_selection` | 快照 |
| 歌曲 | `update_music_name` / `set_music_authors` / `toggle_music_tag` / `add_alias` / `remove_alias` / `move_alias` | `{"ok"}` 或快照 |
| 批量 | `batch_add_tags` / `batch_add_to_playlist` / `delete_musics` | 快照 |
| 歌单 | `create_playlist` / `update_playlist_name` / `set_playlist_entries` / `add_playlist_songs` / `remove_playlist_song` / `add_filter` / `update_filter` / `move_filter` / `remove_filter` / `delete_playlist` | 快照 |
| 自适应 | `update_adaptation` / `reset_stats` | 快照 |
| 标签作者 | `create_tag_group` / `update_tag_group` / `add_tag` / `rename_tag` / `remove_tag` / `delete_tag_group` / `create_author` / `update_author` / `move_author` / `reorder_authors` / `delete_author` / `delete_empty_authors` | 快照 |
| 设置 | `update_settings` / `set_theme` / `set_language` / `clear_all_stats` / `refresh_status` / `browse_folder` | 快照 / 值 |
| 系统 | `browse_import` / `browse_audio` / `open_data_dir` / `open_log_dir` / `run_integrity` / `start_integrity` / `fix_issues` / `launch_player` / `launch_simple` | 值或快照 |
| 试听 | `audition_url` | `{ok, url, title, duration_ms}` |
| 任务 | `start_import` / `start_replace_source` / `poll_task` / `cancel_task` | `{task_id}` / `{state, done, total, current, errors, result}` |
| player | `select_playlist` / `next_track` / `prev_track` / `jump_to` / `track_ended` / `track_failed` / `set_mode` / `pick_loop_song` / `set_playing` / `report_position` / `set_volume` / `set_queue_visible` / `list_songs` / `open_manager` | 快照或 `{"ok"}` |

规则：

- **越界或非法参数不抛异常**，原样返回当前快照。
- 逐字符触发的写入（名称、简介）返回 `{"ok": bool}`，前端做 420 ms 防抖；结构性操作前先 `flushNameSave()` / `flushPlaylistName()`。
- 耗时操作（导入、深检、换源）必须走任务通道，`js_api` 里不阻塞。
- 带 `md5` 的播放事件一律校验「这个 md5 是不是当前曲」，不是就当作过期事件忽略，避免 `ended` 与随后的点击重复记账。

## 8. 线程模型

| 线程 | 归属 | 做什么 | 禁止 |
|---|---|---|---|
| UI 线程 | pywebview | 窗口、`closing`、尺寸读写 | 阻塞、在 `closing` 里 `evaluate_js` |
| `js_api` 线程 | pywebview，每次调用一个 | 读写 JSON、算队列、组装快照（毫秒级） | 长任务、`sleep`、等网络 |
| 任务线程 | `threading.Thread(daemon=True)` | 导入、换源、深检 | 直接调 `evaluate_js`、长时间持锁 |
| 媒体服务 | `ThreadingHTTPServer` | Range 响应 | 碰业务数据 |
| 音频解码 | WebView2 渲染进程 | 解码与播放 | 与 Python 共享状态 |

规则：

- 库写入用「读-改-写 + 原子替换」，管理器内一把 `RLock`；统计写入用「一歌单一锁」（`filelock.exclusive`）。
- 任务线程只在提交阶段持锁；准备阶段（FFmpeg、MD5）在锁外。
- 深检在库的**副本**上跑（`Library.clone()`），拿到一致的时间点，也不会撞上导入线程正在加歌。
- 跨线程只传数据。任务线程只更新任务表，前端自己轮询。
- 网页是音频状态的唯一真相；Python 的 `playing` / `position_ms` 是镜像，只用于恢复与落盘。

## 9. 错误处理

| 场景 | 策略 |
|---|---|
| `library.json` / `playlists.json` 结构损坏 | `ConfigError` → 记日志 → 弹窗给日志路径 → 退出，不静默重建 |
| `settings.json` 缺字段、越界、分节被写成标量 | 读时夹取、整节回退默认值，记 warning，继续运行 |
| 单条记录字段非法 | 跳过该条，记 warning，其余照常 |
| 导入单个文件失败 | 记入批次错误清单，继续处理下一个 |
| 播放失败 / 文件缺失 | 跳过 + 队列标灰 + 一行提示，不中断整个队列 |
| 写盘失败 | Toast + 日志，界面保持原值，不假装成功 |
| 未捕获异常 | `sys.excepthook` 记录 → `logger.complete()` → 原生 `MessageBoxW` → `os._exit(1)` |

原则：**能降级的降级，不能降级的必须留下可读的原因。任何静默失败都算缺陷。**

## 10. 配置与本地化

- 配置归属规则：**一个配置项只要被三个程序中两个或以上读取，就必须放进 `common`，界面上出现在「通用」页。** 只有单一程序使用的才允许放在自己的节里。
- `settings.update()` 与 `patch_player()` 都先读盘再合并，避免两个进程互相覆盖；写盘走「临时文件 + `os.replace`」。
- 语言包放 `app/locales/{语言代码}.json`，文件名即语言代码；启动时扫目录，放进去什么语言就支持什么语言。
- 查表顺序：当前语言 → 默认语言（`zh-CN`）→ 键名本身，绝不抛异常。
- 占位符统一 `{name}`；列举分隔符从语言包取（`list.separator`），不写死。
- 管理器切语言立刻生效（文案、窗口标题、`<html lang>` 一起换）；player 与 simple 在启动时读一次。
- 字段级说明见 [configuration.md](configuration.md)。

## 11. 测试

```
tests/
├─ conftest.py              固定语言、隔离 assets、歌曲工厂、simple 的假依赖
├─ test_paths.py            路径解析
├─ test_settings.py         夹取、默认值、未知键保留、分节损坏
├─ test_models.py           归一化、校验、to_dict 只输出约定键
├─ test_library.py          实体读写与查询
├─ test_playlists.py        手动保序、条件集合、环检测、默认歌单落盘
├─ test_adaptation.py       环形缓冲、阈值、概率
├─ test_adaptation_record.py simple 的记录规则
├─ test_importer.py         MD5、重复、后缀白名单（假 ffmpeg）
├─ test_source.py           换源与删除的每个分支
├─ test_integrity.py        六类问题与三类修复
├─ test_queue.py            洗牌覆盖、接缝、列表循环、按名排序
├─ test_player_session.py   模式、轮次、队列、pin、跳过、缺失
├─ test_player_restore.py   启动恢复的六个分支
├─ test_player_api.py       快照结构、非法参数、不写库、令牌一致
├─ test_api*.py             管理器的快照与编辑接口
├─ test_console_keys.py     绑定表到动作的映射
├─ test_simple_loop.py / test_simple_render.py   播放循环与方框对齐
├─ test_vlc.py              VLC 适配器
├─ test_i18n.py             文案完整性
└─ test_source_hygiene.py   静态守卫
```

约定：

- 涉及文件系统一律用 `tmp_path`；`conftest.py` 的 `isolated_media` 把 `assets` 指到临时目录，测试绝不碰真实音频。
- 系统能力注入假实现（假播放器、假时钟、假按键、假屏幕），测试里不起真实进程、不 sleep。
- 断言文案时用中文，`fixed_language` fixture 把语言钉在 `zh-CN`。
- 界面不做自动化，按 `reference.md` 3.13 的清单手工过一遍。

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 12. 不能破的约定

1. `core` 与 `system` 不导入界面库；界面库只在 `ui/` 里出现。
2. 入口文件不超过 30 行，只做「把 app 叫起来」。
3. 全项目不调用 `os.chdir`；内部路径一律来自 `paths.py`。
4. 写 JSON 一律原子替换，读 JSON 一律先夹取再使用。
5. 结构损坏要报错，不要静默重建——静默重建会把用户数据洗掉。
6. player 与 simple 不写库与歌单，只写统计与自己的界面状态。
7. 一个配置项被两个以上程序读取，就必须进 `common`（通用页）。
8. 队列永远是整张歌单；自适应命中只把那一首标成已播，不从队列里删。
9. 只有「下一首 / `Ctrl+C`」与自然播完写统计；上一首、点队列、切歌单不写。
10. `js_api` 方法不阻塞；耗时操作走任务通道。
11. 非法参数返回当前快照，不抛异常。
12. 两份 `styles.css` 的 `:root` 变量名集合必须相等。
13. 两份语言包的键集合与占位符集合必须相等。
14. 界面文案不写死：HTML 里是兜底，运行时由 `data-i18n*` 与 `T()` 覆盖。

## 13. 偏离标准

| 标准条目 | 偏离 | 原因 |
|---|---|---|
| 3.1 选型 | 播放器也用 pywebview，不用 Qt | 与管理器共用同一套 HTML/CSS 与设计令牌，改样式刷新即可见；播放器没有需要原生窗口的场景，引入 Qt 等于多一套界面技术栈和 150 MB 依赖 |
| 3.2 窗口尺寸 | 播放器固定 960×620、最小 760×480，不按屏幕 85% | 播放器是常驻小窗，铺满屏幕反而难用；尺寸记在 `player.json` 里 |
| 1.6 目录 | 多一个 `<数据目录>/player.json` | 窗口尺寸与队列开合是 player 私有的界面状态，不该进三端共享的 `settings.json` |
| 3.x 界面 | 轻量音乐播放器没有 `ui/`，界面由 `cli/` 承担 | 命令行没有 DOM，按「输入 / 渲染 / 编排」切分更合适；启动速度是这类工具的核心体验 |
| 2.10 本地化 | 轻量音乐播放器的控制台输出不走 i18n，固定中文 | 输出只给本机用户看，切换语言没有意义；它的文案不进语言包 |
| 3.10 键盘 | 不做硬件媒体键与全局热键 | 只服务单机听歌，窗口内按键够用，也避免抢别的程序的键 |
| 3.10.2 快捷键 | 不设 `Ctrl+S` | 全自动保存，每次改动都已落盘 |
| 3.3.4 关闭握手 | 关闭时不等网页回话，直接用内存里最多 2 秒旧的播放位置 | 在 `closing` 里等网页回话会死锁；用 2 秒的陈旧值换掉一次死锁风险 |
| 2.11 线程 | 音频状态由网页持有，Python 只持镜像 | `<audio>` 是唯一真相；Python 轮询会引入延迟与两套状态 |
| 4.1 文档 | 使用手册出中英两份，维护者文档只出中文 | 与标准一致；`docs/old/` 里是重构前的实施计划，只作历史参考，不参与维护 |
